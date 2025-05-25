import json
import requests
import openai
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import render

# OpenAI client
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)


# Check if the query is about date/time/day
def get_datetime_response_if_needed(message):
    """Uses GPT to detect if the query is a datetime intent, and answers if yes."""
    check_message = [
        {
            "role": "system",
            "content": "You are a classifier. Determine if the following query is ONLY asking for current date, time, or day. "
                       "Reply with 'date', 'time', 'day', or 'no' accordingly."
        },
        {"role": "user", "content": message}
    ]

    try:
        result = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=check_message,
            max_tokens=5,
            temperature=0
        )
        decision = result.choices[0].message.content.strip().lower()
        now = datetime.now()

        if decision == "date":
            return f"Today's date is {now.strftime('%B %d, %Y')}."
        elif decision == "time":
            return f"The current time is {now.strftime('%I:%M %p')}."
        elif decision == "day":
            return f"Today is {now.strftime('%A')}."
        return None

    except Exception as e:
        print(f"[Datetime Intent Error] {e}")
        return None


# Smart Brave search result processor
def search_brave(query):
    print(f"[Brave Search] Query: {query}")
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": 3,
    }
    url = "https://api.search.brave.com/res/v1/web/search"
    try:
        response = requests.get(url, headers=headers, params=params)
        print(f"[Brave Search] HTTP {response.status_code}")
        print(f"[Brave Search] Response Body:\n{response.text}")
        response.raise_for_status()

        data = response.json()
        results = data.get("web", {}).get("results", [])
        snippets = [res.get("description", "") for res in results if res.get("description")]

        for snippet in snippets:
            if any(kw in snippet.lower() for kw in ["is", "are", "was", "has", "will be"]):
                return snippet

        return "\n".join(f"- {s}" for s in snippets) if snippets else "No relevant search results found."

    except requests.exceptions.RequestException as e:
        print(f"[Brave Search] RequestException: {e}")
        return "Search failed: unable to retrieve information from Brave."


# Chat API
@csrf_exempt
def chat_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()
            print(f"[User] Message: {user_message}")

            # Step 1: Check if it's a date/time/day query
            quick_answer = get_datetime_response_if_needed(user_message)
            if quick_answer:
                print("[System] Answered directly using datetime intent.")
                return JsonResponse({'response': quick_answer})

            # Step 2: Ask GPT whether web search is needed
            search_check_messages = [
                {
                    "role": "system",
                    "content": "You are an assistant deciding if a user query needs a real-time web search. "
                               "Respond ONLY with 'yes' or 'no'."
                },
                {"role": "user", "content": f"Does this query need a web search to answer accurately?\n\n{user_message}"}
            ]

            search_check_response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=search_check_messages,
                max_tokens=5,
                temperature=0,
            )

            search_decision = search_check_response.choices[0].message.content.strip().lower()
            needs_search = "yes" in search_decision
            print(f"[System] Web search needed: {needs_search}")

            search_info = ""
            if needs_search:
                search_info = search_brave(user_message)
                print(f"[System] Processed Brave Search info:\n{search_info}")

            # Step 3: GPT final response (with web info if available)
            combined_message = user_message
            if search_info:
                combined_message += f"\n\n[Relevant Web Info Retrieved]:\n{search_info}"

            messages = [{"role": "user", "content": combined_message}]

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )
            reply = response.choices[0].message.content.strip()
            print(f"[GPT] Reply: {reply}")

            return JsonResponse({'response': reply})
        except Exception as e:
            print(f"[Error] Exception: {e}")
            return JsonResponse({'response': f"Error: {str(e)}"}, status=500)


# Render chat UI
def chat_view(request):
    return render(request, 'chat_window.html')
