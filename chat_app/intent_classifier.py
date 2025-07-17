from openai import OpenAI
from django.conf import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

ALLOWED_INTENTS = {
    "date", "time", "day", "web_search", "ai",
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

# Enhanced prompt with examples and context consideration
def classify_intent(message, session=None):
    print(f"[DEBUG] [intent_classifier] Input message: {message}")
    user_context = session.get('user_context', '') if session else ''
    check_message = [
        {
            "role": "system",
            "content": (
                "You are a strict classifier for an assistant. "
                "Classify the user query into ONLY ONE of the following categories: "
                "based on the context and examples provided.\n\n"
                + ", ".join(sorted(ALLOWED_INTENTS)) +
                "\n\nReturn only one label in this format: service.action (e.g., gmail.compose). "
                "Do not explain. Do not return multiple. Do not make up labels.\n"
                "Context: {user_context}\n"
                "Examples: "
                "'Send an email' -> 'gmail.compose', "
                "'What is the date today?' -> 'date', "
                "'Add a task to buy groceries' -> 'google_tasks.add', "
                "'Do I have any pending tasks?' -> 'google_tasks.read'"
            ).format(user_context=user_context)
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
