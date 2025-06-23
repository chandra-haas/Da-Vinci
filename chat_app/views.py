import json
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import render

from .intent_classifier import classify_intent
from .web_search import brave_web_search, format_search_results_for_gpt
from .google_services import (
    get_gmail_messages,
    send_gmail_message,
    get_drive_files,
    get_all_tasks,
    add_google_task,
    get_calendar_events,
    create_calendar_event,
    get_user_credentials,
    MissingCredentials,
)

from .assistant_utils import (
    follow_up_handler,
    gpt_param_extractor,
    extract_facts,
    save_facts,
    recall_fact,
)
from .models import MainMemory, ChatSession, SubMemory, SessionMemory, CacheMemory, Message

import openai
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

def sanitize_markdown(text):
    import re
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return text

def get_or_create_main_memory(request):
    main_memory, _ = MainMemory.objects.get_or_create(
        user=request.user if hasattr(request, "user") and request.user.is_authenticated else None
    )
    return main_memory

def get_or_create_chat_session(request):
    main_memory = get_or_create_main_memory(request)
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key
    chat_session, created = ChatSession.objects.get_or_create(
        main_memory=main_memory,
        session_name=session_id
    )
    # Create memory blocks if new session
    if created:
        SubMemory.objects.create(chat_session=chat_session)
        SessionMemory.objects.create(chat_session=chat_session)
        CacheMemory.objects.create(chat_session=chat_session)
    return chat_session

def format_task_list(creds):
    tasks = get_all_tasks(creds)
    if not tasks:
        return "✅ You have no tasks at the moment."
    lines = [f"- **{task['title']}**" for task in tasks if 'title' in task]
    return "📝 Here are your tasks:\n" + "\n".join(lines)

def format_gmail_list(creds):
    messages = get_gmail_messages(creds).get('messages', [])
    if not messages:
        return "📭 No recent emails found."
    return f"📨 You have **{len(messages)}** recent email(s)."

def format_drive_files(creds):
    files = get_drive_files(creds).get('files', [])
    if not files:
        return "📁 Your Drive has no recent files."
    file_lines = [f"- **{file['name']}**" for file in files if 'name' in file]
    return "📂 Here are your recent files:\n" + "\n".join(file_lines)

def is_valid_email_param(value, param_type):
    if not value:
        return False
    value = value.strip().lower()
    generic_subjects = {"send an email", "email", "subject", "test subject"}
    generic_bodies = {"send an email", "email body", "body", "test body", "content"}
    if param_type == "subject" and value in generic_subjects:
        return False
    if param_type == "body" and value in generic_bodies:
        return False
    if param_type == "to_email" and ("@" not in value or "." not in value):
        return False
    return True

GOOGLE_ACTIONS = {
    "gmail.compose": {
        "fn": send_gmail_message,
        "params": ["to_email", "subject", "body"]
    },
    "gmail.read": {
        "fn": format_gmail_list,
        "params": []
    },
    "google_tasks.add": {
        "fn": add_google_task,
        "params": ["task_title", "task_notes", "due_date"]
    },
    "google_tasks.read": {
        "fn": format_task_list,
        "params": []
    },
    "google_drive.search": {
        "fn": format_drive_files,
        "params": []
    },
    "calendar.events": {
        "fn": create_calendar_event,
        "params": ["summary", "start_time", "end_time", "description", "location", "add_meet"]
    },
}

def is_direct_date_or_time_question(message):
    msg = message.strip().lower()
    date_triggers = {
        "what is the date", "what's the date", "today's date", "date?",
        "what date is it", "current date", "give me the date", "show date"
    }
    time_triggers = {
        "what is the time", "what's the time", "current time", "time?",
        "what time is it", "give me the time", "show time"
    }
    day_triggers = {
        "what day is it", "which day is it", "today's day", "day?", "day"
    }
    import re
    msg_no_punct = re.sub(r'[^\w\s]', '', msg)
    return (
        msg in date_triggers or msg_no_punct in date_triggers,
        msg in time_triggers or msg_no_punct in time_triggers,
        msg in day_triggers or msg_no_punct in day_triggers
    )

@csrf_exempt
def chat_api(request):
    print("[DEBUG] --- chat_api endpoint hit ---")
    if request.method != 'POST':
        return JsonResponse({'response': 'Invalid request method.'}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        print(f"[DEBUG] user_message: {user_message}")

        chat_session = get_or_create_chat_session(request)
        Message.objects.create(
            chat_session=chat_session,
            sender='user',
            content=user_message
        )

        facts = extract_facts(user_message)
        if facts:
            save_facts(chat_session, facts)

        fact_response = recall_fact(chat_session, user_message)
        if fact_response:
            fact_response = sanitize_markdown(fact_response)
            Message.objects.create(chat_session=chat_session, sender='assistant', content=fact_response)
            return JsonResponse({'response': fact_response})

        # ---- FOLLOW-UP LOGIC ----
        pending_intent = chat_session.pending_intent
        pending_data = chat_session.pending_data or {}
        if pending_intent and pending_intent in GOOGLE_ACTIONS:
            creds = get_user_credentials(request.session)
            action_spec = GOOGLE_ACTIONS[pending_intent]
            params_needed = action_spec["params"]
            param_values = pending_data.copy() if pending_data else {}

            for p in params_needed:
                if not param_values.get(p):
                    attempt = gpt_param_extractor(user_message, [p])
                    value = attempt.get(p)
                    if is_valid_email_param(value, p):
                        param_values[p] = value
                    break

            missing = [p for p in params_needed if not is_valid_email_param(param_values.get(p), p)]

            if not missing:
                try:
                    result = action_spec["fn"](creds, **{k: param_values[k] for k in params_needed})
                    bot_response = "✅ Email sent!" if pending_intent == "gmail.compose" else "✅ Done!"
                    bot_response = sanitize_markdown(bot_response)
                    Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                except Exception as e:
                    bot_response = f"❌ Error sending email: {e}"
                    bot_response = sanitize_markdown(bot_response)
                    Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                # Always reset state
                chat_session.pending_intent = None
                chat_session.pending_data = {}
                chat_session.save()
                return JsonResponse({'response': bot_response})
            else:
                chat_session.pending_data = param_values
                chat_session.save()
                prompt_map = {
                    "to_email": "What is the recipient's email address?",
                    "subject": "What is the email subject?",
                    "body": "What is the email content?"
                }
                prompt = prompt_map[missing[0]]
                prompt = sanitize_markdown(prompt)
                Message.objects.create(chat_session=chat_session, sender='assistant', content=prompt)
                return JsonResponse({'response': prompt})

        intent = classify_intent(user_message)
        print(f"[DEBUG] Detected intent: {intent}")
        now = timezone.now()

        is_date_q, is_time_q, is_day_q = is_direct_date_or_time_question(user_message)
        if (intent == "date" and is_date_q):
            bot_response = f"Today's date is **{now.strftime('%B %d, %Y')}**"
            bot_response = sanitize_markdown(bot_response)
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})
        elif (intent == "time" and is_time_q):
            bot_response = f"The current time is **{now.strftime('%I:%M %p')}**"
            bot_response = sanitize_markdown(bot_response)
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})
        elif (intent == "day" and is_day_q):
            bot_response = f"Today is **{now.strftime('%A')}**"
            bot_response = sanitize_markdown(bot_response)
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})

        if intent == "web_search":
            search_results = brave_web_search(user_message)
            if not search_results:
                bot_response = 'Sorry, no relevant web results found.'
                bot_response = sanitize_markdown(bot_response)
                Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                return JsonResponse({'response': bot_response})
            context = format_search_results_for_gpt(search_results)
            history = Message.objects.filter(chat_session=chat_session).order_by('timestamp')
            history_text = "\n".join(f"{msg.sender}: {msg.content}" for msg in history)
            gpt_prompt = (
                f"Answer the following user query based on these web results:\n"
                f"User query: {user_message}\n\nWeb results:\n{context}\n\nChat history:\n{history_text}"
            )
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that remembers the conversation."},
                    {"role": "user", "content": gpt_prompt}
                ],
                max_tokens=500,
                temperature=0.7,
            )
            bot_response = response.choices[0].message.content.strip()
            bot_response = sanitize_markdown(bot_response)
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})

        if intent in GOOGLE_ACTIONS:
            service_action = GOOGLE_ACTIONS[intent]
            creds = None
            try:
                creds = get_user_credentials(request.session)
            except MissingCredentials:
                bot_response = 'Authorization required. Please log in with Google.'
                bot_response = sanitize_markdown(bot_response)
                Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                return JsonResponse(
                    {'response': bot_response, 'auth_required': True},
                    status=401
                )
            # Always clear any old data at the start of a new intent!
            chat_session.pending_intent = intent
            chat_session.pending_data = {}
            chat_session.save()
            params_needed = service_action["params"]
            initial_extracted = gpt_param_extractor(user_message, params_needed)
            missing = []
            for p in params_needed:
                if not is_valid_email_param(initial_extracted.get(p), p):
                    initial_extracted.pop(p, None)
                    missing.append(p)
            if not missing:
                try:
                    result = service_action["fn"](creds, **{k: initial_extracted[k] for k in params_needed})
                    bot_response = "✅ Email sent!" if intent == "gmail.compose" else "✅ Done!"
                    bot_response = sanitize_markdown(bot_response)
                    Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                except Exception as e:
                    bot_response = f"❌ Error sending email: {e}"
                    bot_response = sanitize_markdown(bot_response)
                    Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                chat_session.pending_intent = None
                chat_session.pending_data = {}
                chat_session.save()
                return JsonResponse({'response': bot_response})
            elif params_needed:
                first_missing = missing[0]
                prompt_map = {
                    "to_email": "What is the recipient's email address?",
                    "subject": "What is the email subject?",
                    "body": "What is the email content?"
                }
                prompt = prompt_map[first_missing]
                prompt = sanitize_markdown(prompt)
                chat_session.pending_data = initial_extracted
                chat_session.save()
                Message.objects.create(chat_session=chat_session, sender='assistant', content=prompt)
                return JsonResponse({'response': prompt})
            else:
                result = service_action["fn"](creds)
                result = sanitize_markdown(result)
                Message.objects.create(chat_session=chat_session, sender='assistant', content=result)
                return JsonResponse({'response': result})

        history = Message.objects.filter(chat_session=chat_session).order_by('timestamp')
        history_text = "\n".join(f"{msg.sender}: {msg.content}" for msg in history)
        gpt_prompt = (
            f"User message: {user_message}\n\nChat history:\n{history_text}"
        )
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that remembers and uses the conversation history for context."},
                {"role": "user", "content": gpt_prompt}
            ],
            max_tokens=500,
            temperature=0.7,
        )
        bot_response = response.choices[0].message.content.strip()
        bot_response = sanitize_markdown(bot_response)
        Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
        return JsonResponse({'response': bot_response})

    except Exception as e:
        chat_session = None
        try:
            chat_session = get_or_create_chat_session(request)
        except Exception:
            pass
        if chat_session:
            chat_session.pending_intent = None
            chat_session.pending_data = {}
            chat_session.save()
        print(f"[DEBUG] Exception occurred: {e}")
        bot_response = f"Error: {str(e)}"
        bot_response = sanitize_markdown(bot_response)
        return JsonResponse({'response': bot_response}, status=500)

def chat_view(request):
    return render(request, 'chat_window.html')