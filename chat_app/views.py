import json
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import render

from .intent_classifier import classify_intent
from .app_services.brave.web_search import brave_web_search, format_search_results_for_gpt
from .app_services.google.google_services import (
    get_user_credentials,
    MissingCredentials,
)

from .assistant_utils import handle_intent

import openai
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

# Format helpers

from .app_services.google.google_services import get_all_tasks, get_gmail_messages, get_drive_files

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


@csrf_exempt
def chat_api(request):
    print("[DEBUG] --- chat_api endpoint hit ---")
    if request.method != 'POST':
        return JsonResponse({'response': 'Invalid request method.'}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        print(f"[DEBUG] user_message: {user_message}")

        # Intent locking: check for pending multi-turn intent
        pending_intent = request.session.get('pending_intent')
        multi_turn_active = request.session.get('multi_turn_active', False)
        now = datetime.now()

        if multi_turn_active and pending_intent:
            print(f"[DEBUG] Multi-turn lock active: {pending_intent}")
            intent = pending_intent
        else:
            # Classify intent as usual
            intent = classify_intent(user_message)
            print(f"[DEBUG] Detected intent: {intent}")
            # If this is a multi-turn intent, set lock
            multi_turn_intents = [
                "gmail.compose",
                "gmail.read",
                "google_tasks.add",
                "google_tasks.read",
                "google_drive.upload",
                "google_drive.search",
                "outlook_mail.compose",
                "outlook_mail.read",
                "microsoft_teams.schedule",
                "microsoft_todo.add",
                "microsoft_todo.read",
                "one_drive.upload",
                "one_drive.search",
                "notepad.open"]  # Add more as needed
            if intent in multi_turn_intents:
                request.session['pending_intent'] = intent
                request.session['multi_turn_active'] = True
            else:
                request.session['pending_intent'] = None
                request.session['multi_turn_active'] = False

        # Directly handle 'ai' intent by sending to ChatGPT
        if intent == "ai":
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": user_message}],
                max_tokens=500,
                temperature=0.7,
            )
            return JsonResponse({'response': response.choices[0].message.content.strip()})

        if intent == "date":
            return JsonResponse({'response': f"Today's date is {now.strftime('%B %d, %Y')}"})
        elif intent == "time":
            return JsonResponse({'response': f"The current time is {now.strftime('%I:%M %p')}"})
        elif intent == "day":
            return JsonResponse({'response': f"Today is {now.strftime('%A')}"})

        if intent == "web_search":
            search_results = brave_web_search(user_message)
            if not search_results:
                return JsonResponse({'response': 'Sorry, no relevant web results found.'})
            context = format_search_results_for_gpt(search_results)
            gpt_prompt = (
                f"Answer the following user query based on these web results:\n"
                f"User query: {user_message}\n\nWeb results:\n{context}"
            )
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": gpt_prompt}],
                max_tokens=500,
                temperature=0.7,
            )
            return JsonResponse({'response': response.choices[0].message.content.strip()})

        # Microsoft intent handling (must come before Google intent handling)
        MICROSOFT_FEATURES = [
            "outlook_mail", "microsoft_todo", "microsoft_teams", "one_drive"
        ]
        def is_microsoft_intent(intent):
            parts = intent.split('.')
            if len(parts) == 2:
                feature, _ = parts
                return feature in MICROSOFT_FEATURES
            elif len(parts) == 3:
                service, feature, _ = parts
                return service == "microsoft"
            return False

        if is_microsoft_intent(intent):
            print("[DEBUG] Microsoft intent block entered")
            tokens = request.session.get("microsoft_tokens")
            if not tokens or "access_token" not in tokens:
                print("[DEBUG] Microsoft tokens missing, prompting login")
                return JsonResponse(
                    {'response': 'Authorization required. Please log in with Microsoft.', 'auth_required': True, 'login_url': '/auth/microsoft/login/'},
                    status=401
                )
            result = handle_intent(intent, user_message, tokens=tokens, session=request.session)
            if isinstance(result, dict):
                return JsonResponse(result)
            else:
                return JsonResponse({'response': result})

        # Google intent handling (as before)
        google_intents = [
            'gmail.compose', 'gmail.read', 'google_tasks.add', 'google_tasks.read',
            'google_drive.search', 'calendar.events'
        ]
        if intent in google_intents:
            print("[DEBUG] Google intent block entered")
            try:
                creds = get_user_credentials(request.session)
            except MissingCredentials:
                print("[DEBUG] Google credentials missing, prompting login")
                return JsonResponse(
                    {'response': 'Authorization required. Please log in with Google.', 'auth_required': True, 'login_url': '/auth/google/login/'},
                    status=401
                )
            result = handle_intent(intent, user_message, creds=creds, session=request.session)
            # If the handler signals the intent is complete, clear lock
            if not request.session.get('task_active', True) and not request.session.get('compose_active', True):
                request.session['pending_intent'] = None
                request.session['multi_turn_active'] = False
            if isinstance(result, dict):
                return JsonResponse(result)
            else:
                return JsonResponse({'response': result})

        # Handle all modular intents via handler (all parameter prompting is delegated)
        result = handle_intent(intent, user_message, session=request.session)
        # If the handler signals the intent is complete, clear lock
        if not request.session.get('compose_active', True):
            request.session['pending_intent'] = None
            request.session['pending_intent_active'] = False
        if isinstance(result, dict):
            return JsonResponse(result)
        else:
            return JsonResponse({'response': result})

        # Fallback: if handle_intent does not handle, use GPT
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": user_message}],
            max_tokens=500,
            temperature=0.7,
        )
        return JsonResponse({'response': response.choices[0].message.content.strip()})

    except Exception as e:
        print(f"[DEBUG] Exception occurred: {e}")
        return JsonResponse({'response': f"Error: {str(e)}"}, status=500)

def chat_view(request):
    return render(request, 'chat_window.html')
