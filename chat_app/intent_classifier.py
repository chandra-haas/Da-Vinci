import openai
from django.conf import settings

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

def classify_intent(message):
    print(f"[DEBUG] [intent_classifier] Input message: {message}")
    check_message = [
        {"role": "system", "content": (
            "You are a classifier. "
            "Classify the user query into one of: date, time, day, web_search, calculator, ai. "
            "Reply with only one class."
        )},
        {"role": "user", "content": message}
    ]
    try:
        result = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=check_message,
            max_tokens=5,
            temperature=0
        )
        intent = result.choices[0].message.content.strip().lower()
        print(f"[DEBUG] [intent_classifier] Classified intent: {intent}")
        return intent
    except Exception as e:
        print(f"[DEBUG] [intent_classifier] Error: {e}")
        return "ai"