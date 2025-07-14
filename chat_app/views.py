import json
from django.utils import timezone
from django.utils.timezone import localtime
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
from .is_valid_email_param import is_valid_email_param

from .assistant_utils import (
    follow_up_handler,
    gpt_param_extractor,
    extract_facts,
    save_facts,
    recall_fact,
)
from .models import ChatSession, Message, MemoryFact

import openai
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)


def sanitize_markdown(text):
    import re
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return text


def get_or_create_main_memory(request):
    return None


def get_or_create_chat_session(request):
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key
    chat_session, _ = ChatSession.objects.get_or_create(session_id=session_id)
    return chat_session


GOOGLE_ACTIONS = {
    "gmail.compose": {
        "fn": send_gmail_message,
        "params": ["to_email", "subject", "body"]
    },
    "gmail.read": {
        "fn": lambda creds: format_gmail_list(creds),
        "params": []
    },
    "google_tasks.add": {
        "fn": add_google_task,
        "params": ["task_title", "task_notes", "due_date"]
    },
    "google_tasks.read": {
        "fn": lambda creds: format_task_list(creds),
        "params": []
    },
    "google_drive.search": {
        "fn": lambda creds: format_drive_files(creds),
        "params": []
    },
    "calendar.events": {
        "fn": create_calendar_event,
        "params": ["summary", "start_time", "end_time", "description", "location", "add_meet"]
    },
}


def format_gmail_list(creds):
    from .google_services import get_gmail_messages
    messages = get_gmail_messages(creds, max_results=5)
    items = messages.get('messages', [])
    if not items:
        return 'No recent emails found.'
    return f"Recent emails: {[m['id'] for m in items]}"


def format_task_list(creds):
    from .google_services import get_all_tasks
    tasks = get_all_tasks(creds, max_results=5)
    if not tasks:
        return 'No tasks found.'
    return f"Tasks: {[t['title'] for t in tasks if 'title' in t]}"


def format_drive_files(creds):
    from .google_services import get_drive_files
    files = get_drive_files(creds, page_size=5)
    items = files.get('files', [])
    if not items:
        return 'No files found.'
    return f"Files: {[f['name'] for f in items if 'name' in f]}"


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

        pending_intent = getattr(chat_session, 'pending_intent', None)
        pending_data = getattr(chat_session, 'pending_data', {}) or {}

        if pending_intent and pending_intent == "gmail.compose":
            creds = get_user_credentials(request.session)
            action_spec = GOOGLE_ACTIONS[pending_intent]
            params_needed = action_spec["params"]
            param_values = pending_data.copy() if pending_data else {}

            # Extract all params from the user message, but do not overwrite existing values
            extracted_params = {}
            used_texts = set()
            for p in params_needed:
                if not param_values.get(p):
                    attempt = gpt_param_extractor(user_message, [p])
                    value = attempt.get(p)
                    if is_valid_email_param(value, p):
                        extracted_params[p] = value
                        param_values[p] = value
                        if value:
                            used_texts.add(value.strip().lower())

            # Special: If user says 'body is ...' or 'content is ...', always use that as body
            import re
            body_match = re.search(r"(?:body|content)\s*(is|:)\s*(.+)", user_message, re.I)
            if body_match:
                param_values["body"] = body_match.group(2).strip()

            # Remove extracted subject/to_email from body if present, and avoid overlap
            if param_values.get("body"):
                body = param_values["body"]
                subj = param_values.get("subject", "")
                addr = param_values.get("to_email", "")
                # Remove explicit subject or address lines from body
                if subj:
                    body = re.sub(r"subject\s*is\s*['\"]?" + re.escape(subj) + r"['\"]?", "", body, flags=re.I)
                    body = re.sub(r"subject:\s*['\"]?" + re.escape(subj) + r"['\"]?", "", body, flags=re.I)
                if addr:
                    body = re.sub(r"to\s*['\"]?" + re.escape(addr) + r"['\"]?", "", body, flags=re.I)
                    body = re.sub(r"recipient\s*is\s*['\"]?" + re.escape(addr) + r"['\"]?", "", body, flags=re.I)
                # Remove any lines like 'subject is ...' or 'to ...' if they match extracted params
                body = re.sub(r"^(subject|to|recipient)\s*(:|is)\s*.*$", "", body, flags=re.I | re.MULTILINE)
                for used in used_texts:
                    if used and used in body.lower():
                        body = re.sub(re.escape(used), "", body, flags=re.I)
                param_values["body"] = body.strip()

            missing = [p for p in params_needed if not is_valid_email_param(param_values.get(p), p)]

            # Only generate body if it is missing after all extraction attempts
            if not missing and not param_values.get("body"):
                subject = param_values.get("subject", "(no subject)")
                to_email = param_values.get("to_email", "")
                gpt_prompt = f"Draft a polite, professional email to {to_email} with the subject '{subject}'. Make up a reasonable body based on the subject."
                response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[
                        {"role": "system", "content": "You are an AI that writes professional emails."},
                        {"role": "user", "content": gpt_prompt}
                    ],
                    max_tokens=300,
                    temperature=0.7,
                )
                param_values["body"] = response.choices[0].message.content.strip()

            missing = [p for p in params_needed if not is_valid_email_param(param_values.get(p), p)]

            if not missing:
                try:
                    result = action_spec["fn"](creds, **{k: param_values[k] for k in params_needed})
                    bot_response = "✅ Email sent!"
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
            else:
                chat_session.pending_data = param_values
                chat_session.save()
                prompt_map = {
                    "to_email": "What is the recipient's email address?",
                    "subject": "What is the email subject?",
                    "body": "What is the email content?"
                }
                prompt = prompt_map.get(missing[0], "Please provide the required information.")
                prompt = sanitize_markdown(prompt)
                Message.objects.create(chat_session=chat_session, sender='assistant', content=prompt)
                return JsonResponse({'response': prompt})

        intent = classify_intent(user_message)
        print(f"[DEBUG] Detected intent: {intent}")

        now_local = localtime(timezone.now())

        if intent == "date":
            bot_response = f"Today's date is **{now_local.strftime('%B %d, %Y')}**"
            bot_response = sanitize_markdown(bot_response)
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})
        elif intent == "time":
            bot_response = f"The current time is **{now_local.strftime('%I:%M %p')}**"
            bot_response = sanitize_markdown(bot_response)
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})
        elif intent == "day":
            bot_response = f"Today is **{now_local.strftime('%A')}**"
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

            try:
                creds = get_user_credentials(request.session)
            except MissingCredentials:
                bot_response = 'Authorization required. Please log in with Google.'
                bot_response = sanitize_markdown(bot_response)
                Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                return JsonResponse({'response': bot_response, 'auth_required': True}, status=401)

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
                prompt = prompt_map.get(first_missing, "Please provide the required information.")
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
        gpt_prompt = f"User message: {user_message}\n\nChat history:\n{history_text}"

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
