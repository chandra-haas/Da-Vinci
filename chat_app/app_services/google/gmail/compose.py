import re

REQUIRED_FIELDS = ["to", "subject", "body"]

# Simple regex for email extraction (not fully RFC compliant)
EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

from django.conf import settings
from openai import OpenAI
import json

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def legacy_regex_parse_fields(user_input):
    fields = {}
    email_match = re.search(EMAIL_REGEX, user_input)
    if email_match:
        fields["to"] = email_match.group(0)
    subj_match = re.search(r"subject[:\-]?\s*(.+?)(?:$| body[:\-])", user_input, re.IGNORECASE)
    if subj_match:
        fields["subject"] = subj_match.group(1).strip()
    body_match = re.search(r"body[:\-]?\s*(.+)", user_input, re.IGNORECASE)
    if body_match:
        fields["body"] = body_match.group(1).strip()
    return fields

def parse_fields(user_input):
    """
    Use LLM to extract 'to', 'subject', and 'body' from user input.
    Returns a dict with any found fields.
    """
    prompt = (
        "Extract the recipient email address, subject, and body for an email from the following message.\n"
        "If the message contains only a generic trigger phrase (like 'send a gmail', 'compose email', 'write an email', etc.), "
        "do NOT use it as the body or subject. Only extract actual content the user wants to send.\n"
        "If the user provides all fields in one message, extract them all.\n"
        "If any field is missing, return it as an empty string.\n"
        "Respond in JSON with keys: to, subject, body.\n\n"
        f"Message: {user_input}\n\n"
        "Example 1:\n"
        "Message: send a gmail\n"
        "Output: {\"to\": \"\", \"subject\": \"\", \"body\": \"\"}\n"
        "Example 2:\n"
        "Message: send a gmail to alice@example.com saying meet me in 5\n"
        "Output: {\"to\": \"alice@example.com\", \"subject\": \"\", \"body\": \"meet me in 5\"}\n"
        "Example 3:\n"
        "Message: urgent: meet me in 5 (to alice@example.com)\n"
        "Output: {\"to\": \"alice@example.com\", \"subject\": \"urgent\", \"body\": \"meet me in 5\"}\n"
        "Example 4:\n"
        "Message: compose email\n"
        "Output: {\"to\": \"\", \"subject\": \"\", \"body\": \"\"}\n"
        "Example 5:\n"
        "Message: send a gmail to bob@example.com about project status update: The project is on track.\n"
        "Output: {\"to\": \"bob@example.com\", \"subject\": \"project status update\", \"body\": \"The project is on track.\"}\n"
    )
    try:
        result = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0
        )
        content = result.choices[0].message.content.strip()
        fields = json.loads(content)
        # Clean up any whitespace
        return {k: v.strip() for k, v in fields.items() if v}
    except Exception as e:
        print(f"[DEBUG] LLM extraction failed: {e}")
        # Fallback to regex if LLM fails
        return legacy_regex_parse_fields(user_input)

def handle(user_input, **kwargs):
    """
    Stateful handler for 'gmail.compose'.
    Collects 'to', 'subject', 'body' over multiple turns.
    Uses kwargs['session'] (dict) to persist state.
    """
    session = kwargs.get('session', {})
    if 'compose_state' not in session:
        session['compose_state'] = {}
    state = session['compose_state']

    # Parse every message (including the first) for all possible fields
    parsed = parse_fields(user_input)
    state.update(parsed)

    # Check for missing fields
    missing = [f for f in REQUIRED_FIELDS if f not in state or not state[f].strip()]

    if missing:
        # Prompt for the first missing field
        prompts = {
            "to": "Who do you want to send the email to? Please provide the recipient's email address.",
            "subject": "What is the subject of your email?",
            "body": "What would you like to say in the email?"
        }
        next_field = missing[0]
        session['compose_state'] = state
        session['compose_active'] = True
        return prompts[next_field]
    else:
        # All fields present, send the email using google_services
        creds = kwargs.get('creds')
        from chat_app.app_services.google.google_services import send_gmail_message
        try:
            send_result = send_gmail_message(
                creds,
                state['to'],
                state['subject'],
                state['body']
            )
            result = (
                f"Sending email to: {state['to']}\n"
                f"Subject: {state['subject']}\n"
                f"Body: {state['body']}\n"
                f"✅ Email sent successfully! Gmail API response: {send_result}"
            )
        except Exception as e:
            result = (
                f"Failed to send email to: {state['to']}\n"
                f"Subject: {state['subject']}\n"
                f"Body: {state['body']}\n"
                f"❌ Error: {e}"
            )
        # Clear compose state
        session.pop('compose_state', None)
        session['compose_active'] = False
        return result
