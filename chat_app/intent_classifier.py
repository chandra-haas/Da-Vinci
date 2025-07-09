import openai
from django.conf import settings

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

ALLOWED_INTENTS = {
    "date", "time", "day", "web_search", "calculator", "ai",
    "gmail.compose", "gmail.read",
    "google_meet.schedule",
    "google_tasks.add", "google_tasks.read",
    "google_drive.upload", "google_drive.search",
    "outlook_mail.compose", "outlook_mail.read",
    "microsoft_teams.schedule",
    "microsoft_todo.add", "microsoft_todo.read",
    "one_drive.upload", "one_drive.search",
    "notepad.open"
}

def classify_intent(message):
    print(f"[DEBUG] [intent_classifier] Input message: {message}")

    # FALLBACK: Recognize mail/email/gmail for send intent
    lowered = message.lower()
    if any(w in lowered for w in ["send mail", "send an email", "send email", "mail to", "email to"]) and "outlook" not in lowered:
        return "gmail.compose"

    check_message = [
        {
            "role": "system",
            "content": (
                "You are a strict classifier for an assistant. "
                "Classify the user query into ONLY ONE of the following categories:\n\n"
                + ", ".join(sorted(ALLOWED_INTENTS)) +
                "\n\nReturn only one label in this format: service.action (e.g., gmail.compose). "
                "Do not explain. Do not return multiple. Do not make up labels."
            )
        },
        {"role": "user", "content": message}
    ]
    
    try:
        result = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=check_message,
            max_tokens=10,
            temperature=0
        )
        intent = result.choices[0].message.content.strip().lower()
        if intent not in ALLOWED_INTENTS:
            print(f"[DEBUG] [intent_classifier] Invalid intent: '{intent}', falling back to 'ai'")
            return "ai"
        print(f"[DEBUG] [intent_classifier] Classified intent: {intent}")
        return intent
    except Exception as e:
        print(f"[DEBUG] [intent_classifier] Error: {e}")
        return "ai"
