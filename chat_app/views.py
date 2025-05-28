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
    get_tasks,
    add_google_task,
    get_calendar_events,
    create_calendar_event,
    get_user_credentials,
    MissingCredentials,
)

from .assistant_utils import follow_up_handler, gpt_param_extractor

import openai
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)


@csrf_exempt
def chat_api(request):
    print("[DEBUG] --- chat_api endpoint hit ---")
    if request.method != 'POST':
        return JsonResponse({'response': 'Invalid request method.'}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        print(f"[DEBUG] user_message: {user_message}")

        # 1. Check for ongoing follow-up
        pending_intent = request.session.get('pending_intent')
        if pending_intent == "gmail.compose":
            creds = get_user_credentials(request.session)
            reply = follow_up_handler(
                session=request.session,
                required_fields=["to_email", "subject", "body"],
                user_input=user_message,
                extract_func=gpt_param_extractor,
                action_func=send_gmail_message,
                creds=creds
            )
            return JsonResponse({'response': reply})

        # 2. Classify intent
        intent = classify_intent(user_message)
        print(f"[DEBUG] Detected intent: {intent}")

        now = datetime.now()

        # --- Date/Time/Day Intents ---
        if intent == "date":
            return JsonResponse({'response': f"Today's date is {now.strftime('%B %d, %Y')}"})
        elif intent == "time":
            return JsonResponse({'response': f"The current time is {now.strftime('%I:%M %p')}"})
        elif intent == "day":
            return JsonResponse({'response': f"Today is {now.strftime('%A')}"})

        # --- Web Search Intent ---
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

        # --- Google Services ---
        if "." in intent:
            service, action = intent.split(".")
            print(f"[DEBUG] Parsed service: {service}, action: {action}")

            creds = None
            if service in ["gmail", "drive", "calendar", "google_meet", "google_tasks"]:
                try:
                    creds = get_user_credentials(request.session)
                except MissingCredentials:
                    return JsonResponse(
                        {'response': 'Authorization required. Please log in with Google.', 'auth_required': True},
                        status=401
                    )

            # Gmail
            if service == "gmail":
                if action == "compose":
                    request.session['pending_intent'] = "gmail.compose"
                    request.session['pending_data'] = {}
                    return JsonResponse({'response': "Who do you want to send the email to?"})
                elif action == "read":
                    messages = get_gmail_messages(creds)
                    service_obj = send_gmail_message.__globals__['build']('gmail', 'v1', credentials=creds)
                    summaries = []
                    for msg in messages.get('messages', []):
                        msg_detail = service_obj.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['Subject', 'From']).execute()
                        headers = msg_detail.get('payload', {}).get('headers', [])
                        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
                        snippet = msg_detail.get('snippet', '')
                        summaries.append(f"📧 From: {sender}\nSubject: {subject}\nSnippet: {snippet}")
                    return JsonResponse({'response': "\n\n".join(summaries) if summaries else "You have no recent emails."})

            # Google Meet via Calendar
            elif service == "google_meet" and action == "schedule":
                return JsonResponse({'response': create_calendar_event(
                    creds,
                    summary="Team Meeting",
                    start_time="2025-05-29T10:00:00Z",
                    end_time="2025-05-29T11:00:00Z",
                    add_meet=True
                )})

            # Google Tasks
            elif service == "google_tasks" and action == "add":
                return JsonResponse({'response': add_google_task(
                    creds,
                    task_title="Complete DAVINCI demo"
                )})

            return JsonResponse({'response': 'Sorry, I couldn’t recognize that action.'})

        # --- Default Fallback to GPT ---
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
