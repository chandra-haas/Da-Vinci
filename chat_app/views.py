import json
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import render

from .intent_classifier import classify_intent
from .web_search import brave_web_search, format_search_results_for_gpt

# OpenAI client
import openai
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

@csrf_exempt
def chat_api(request):
    print(f"[DEBUG] [chat_api] Incoming request: {request.method}")
    if request.method != 'POST':
        return JsonResponse({'response': 'Invalid request method.'}, status=405)
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        print(f"[DEBUG] [chat_api] user_message: {user_message}")

        intent = classify_intent(user_message)
        print(f"[DEBUG] [chat_api] Detected intent: {intent}")

        now = datetime.now()
        if intent == "date":
            response = f"Today's date is {now.strftime('%B %d, %Y')}"
            print(f"[DEBUG] [chat_api] Date response: {response}")
            return JsonResponse({'response': response})
        elif intent == "time":
            response = f"The current time is {now.strftime('%I:%M %p')}"
            print(f"[DEBUG] [chat_api] Time response: {response}")
            return JsonResponse({'response': response})
        elif intent == "day":
            response = f"Today is {now.strftime('%A')}"
            print(f"[DEBUG] [chat_api] Day response: {response}")
            return JsonResponse({'response': response})
        elif intent == "web_search":
            search_results = brave_web_search(user_message)
            print(f"[DEBUG] [chat_api] Search results: {search_results}")
            if not search_results:
                reply = "Sorry, no relevant web results found."
                print(f"[DEBUG] [chat_api] No search results reply: {reply}")
                return JsonResponse({"response": reply})
            context = format_search_results_for_gpt(search_results)
            gpt_prompt = (
                f"Answer the following user query based on these web results:\n"
                f"User query: {user_message}\n\nWeb results:\n{context}"
            )
            print(f"[DEBUG] [chat_api] GPT prompt: {gpt_prompt}")
            messages = [{"role": "user", "content": gpt_prompt}]
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )
            reply = response.choices[0].message.content.strip()
            print(f"[DEBUG] [chat_api] GPT reply: {reply}")
            return JsonResponse({'response': reply})

        # Default: AI response
        print(f"[DEBUG] [chat_api] Defaulting to AI response")
        messages = [{"role": "user", "content": user_message}]
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()
        print(f"[DEBUG] [chat_api] Final AI reply: {reply}")
        return JsonResponse({'response': reply})

    except Exception as e:
        print(f"[DEBUG] [chat_api] Exception: {e}")
        return JsonResponse({'response': f"Error: {str(e)}"}, status=500)

def chat_view(request):
    return render(request, 'chat_window.html')
