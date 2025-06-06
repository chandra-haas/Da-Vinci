import json
from datetime import datetime

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
from .models import ChatSession, Message  # memory models

import openai
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

# Format helpers

def format_task_list(creds):
    tasks = get_all_tasks(creds)
    if not tasks:
        return "✅ You have no tasks at the moment."
    lines = [f"- {task['title']}" for task in tasks if 'title' in task]
    return "📝 Here are your tasks:\n" + "\n".join(lines)

def format_gmail_list(creds):
    messages = get_gmail_messages(creds).get('messages', [])
    if not messages:
        return "📭 No recent emails found."
    return f"📨 You have {len(messages)} recent email(s)."

def format_drive_files(creds):
    files = get_drive_files(creds).get('files', [])
    if not files:
        return "📁 Your Drive has no recent files."
    file_lines = [f"- {file['name']}" for file in files if 'name' in file]
    return "📂 Here are your recent files:\n" + "\n".join(file_lines)

# Mapping service+action to the corresponding function and required params
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

def get_or_create_chat_session(request):
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key
    chat_session, _ = ChatSession.objects.get_or_create(session_id=session_id)
    return chat_session

def is_direct_date_or_time_question(message):
    msg = message.strip().lower()
    # Direct questions that should yield date/time
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
    # Remove punctuation for robustness
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

        # --- MEMORY FEATURE: Save user message ---
        chat_session = get_or_create_chat_session(request)
        Message.objects.create(
            chat_session=chat_session,
            sender='user',
            content=user_message
        )

        # --- SEMANTIC MEMORY: Fact extraction and recall ---
        # Save any facts from this message
        facts = extract_facts(user_message)
        if facts:
            save_facts(chat_session, facts)

        # Respond to fact-based questions before anything else
        fact_response = recall_fact(chat_session, user_message)
        if fact_response:
            Message.objects.create(chat_session=chat_session, sender='assistant', content=fact_response)
            return JsonResponse({'response': fact_response})

        # Check for ongoing follow-up for any Google service
        pending_intent = request.session.get('pending_intent')
        pending_data = request.session.get('pending_data', {})
        if pending_intent and pending_intent in GOOGLE_ACTIONS:
            creds = get_user_credentials(request.session)
            action_spec = GOOGLE_ACTIONS[pending_intent]
            reply = follow_up_handler(
                session=request.session,
                required_fields=action_spec["params"],
                user_input=user_message,
                extract_func=gpt_param_extractor,
                action_func=action_spec["fn"],
                creds=creds
            )
            Message.objects.create(chat_session=chat_session, sender='assistant', content=reply)
            return JsonResponse({'response': reply})

        # Classify intent as usual
        intent = classify_intent(user_message)
        print(f"[DEBUG] Detected intent: {intent}")
        now = datetime.now()

        # --- IMPROVED: Only answer with date/time/day for direct questions ---
        is_date_q, is_time_q, is_day_q = is_direct_date_or_time_question(user_message)
        if (intent == "date" and is_date_q):
            bot_response = f"Today's date is {now.strftime('%B %d, %Y')}"
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})
        elif (intent == "time" and is_time_q):
            bot_response = f"The current time is {now.strftime('%I:%M %p')}"
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})
        elif (intent == "day" and is_day_q):
            bot_response = f"Today is {now.strftime('%A')}"
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})
        # --- For all other 'when...' or time-related questions, let the LLM answer! ---

        if intent == "web_search":
            search_results = brave_web_search(user_message)
            if not search_results:
                bot_response = 'Sorry, no relevant web results found.'
                Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                return JsonResponse({'response': bot_response})
            context = format_search_results_for_gpt(search_results)
            # Add chat history for context if desired
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
            Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
            return JsonResponse({'response': bot_response})

        if intent in GOOGLE_ACTIONS:
            service_action = GOOGLE_ACTIONS[intent]
            creds = None
            try:
                creds = get_user_credentials(request.session)
            except MissingCredentials:
                bot_response = 'Authorization required. Please log in with Google.'
                Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
                return JsonResponse(
                    {'response': bot_response, 'auth_required': True},
                    status=401
                )
            request.session['pending_intent'] = intent
            request.session['pending_data'] = {}
            request.session.modified = True
            if service_action["params"]:
                first_param = service_action["params"][0]
                prompt = f"What is the {first_param.replace('_', ' ')}?"
                Message.objects.create(chat_session=chat_session, sender='assistant', content=prompt)
                return JsonResponse({'response': prompt})
            else:
                # No params needed: execute directly
                result = service_action["fn"](creds)
                Message.objects.create(chat_session=chat_session, sender='assistant', content=result)
                return JsonResponse({'response': result})

        # --- DEFAULT: Chat with LLM using chat history as context ---
        # Add chat history for context
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
        Message.objects.create(chat_session=chat_session, sender='assistant', content=bot_response)
        return JsonResponse({'response': bot_response})

    except Exception as e:
        print(f"[DEBUG] Exception occurred: {e}")
        return JsonResponse({'response': f"Error: {str(e)}"}, status=500)

def chat_view(request):
    return render(request, 'chat_window.html')