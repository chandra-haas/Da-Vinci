import re
<<<<<<< HEAD
import dateparser

from .models import SubMemory, SessionMemory, CacheMemory, ChatSession
=======
from datetime import datetime
import dateparser

from .models import MemoryFact, ChatSession  # Import MemoryFact for semantic memory
>>>>>>> c88ac103dbcd299eccaf81ac54a241438167ebfc

def gpt_param_extractor(user_input, required_fields):
    extracted = {}
    for field in required_fields:
        if field in ["to_email", "email"]:
            match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", user_input)
            if match:
                extracted[field] = match.group(0)

        elif field in ["subject", "summary", "task_title"]:
            match = re.search(r'"([^"]+)"', user_input)
            if match:
                extracted[field] = match.group(1)
            elif len(user_input.split()) <= 6:
                extracted[field] = user_input

        elif field in ["body", "task_notes", "description"]:
            match = re.search(r"(body|notes|description):(.+)", user_input, re.I)
            if match:
                extracted[field] = match.group(2).strip()
            else:
                if len(user_input.strip().split()) <= 15:
                    extracted[field] = user_input.strip()

        elif field in ["due_date", "start_time", "end_time"]:
            match = re.search(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?Z?)?", user_input)
            if match:
                date_str = match.group(0)
                if 'T' not in date_str:
                    date_str += "T00:00:00.000Z"
                elif 'Z' not in date_str:
                    date_str += "Z"
                extracted[field] = date_str
            else:
                parsed_date = dateparser.parse(user_input)
                if parsed_date:
                    extracted[field] = parsed_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        elif field == "location":
            match = re.search(r"(location:|at )(.+)", user_input, re.I)
            if match:
                extracted[field] = match.group(2).strip()

        elif field == "add_meet":
            if "meet" in user_input.lower() or "yes" in user_input.lower():
                extracted[field] = True
            elif "no" in user_input.lower():
                extracted[field] = False

    return extracted

def extract_facts(user_message):
    """
    Extracts simple facts from the user message for semantic memory.
    Expand this with more patterns as needed.
    """
    patterns = [
        (r"\bmy name is ([\w\s]+)", "name"),
        (r"\bi live in ([\w\s]+)", "location"),
        (r"\bmy favourite color is ([\w\s]+)", "favorite_color"),
        (r"\bmy favorite color is ([\w\s]+)", "favorite_color"),
        (r"\bmy birthday is ([\w\d\s,]+)", "birthday"),
        (r"\bmy age is (\d+)", "age"),
        # Add more patterns as needed
    ]
    facts = []
    for pattern, key in patterns:
        match = re.search(pattern, user_message, re.IGNORECASE)
        if match:
            facts.append((key, match.group(1).strip()))
    return facts

def save_facts(chat_session, facts):
    """
<<<<<<< HEAD
    Save extracted facts to the SessionMemory model, updating if the key exists.
    """
    session_memory = SessionMemory.objects.get(chat_session=chat_session)
    for key, value in facts:
        session_memory.facts[key] = value
    session_memory.save()

def recall_fact(chat_session, user_message):
    """
    Check if the user is asking about a stored fact and retrieve it from session memory.
    """
    session_memory = SessionMemory.objects.get(chat_session=chat_session)
=======
    Save extracted facts to the MemoryFact model, updating if the key exists.
    """
    for key, value in facts:
        MemoryFact.objects.update_or_create(
            chat_session=chat_session,
            key=key,
            defaults={'value': value}
        )

def recall_fact(chat_session, user_message):
    """
    Check if the user is asking about a stored fact and retrieve it from memory.
    """
>>>>>>> c88ac103dbcd299eccaf81ac54a241438167ebfc
    key_map = {
        "what is my name": "name",
        "who am i": "name",
        "where do i live": "location",
        "what is my favorite color": "favorite_color",
        "what is my favourite color": "favorite_color",
        "when is my birthday": "birthday",
        "how old am i": "age",
        # Add more Q&A mappings as needed
    }
    for question, key in key_map.items():
        if question in user_message.lower():
<<<<<<< HEAD
            value = session_memory.facts.get(key)
            if value:
                return f"Your {key.replace('_', ' ')} is {value}."
=======
            fact = MemoryFact.objects.filter(chat_session=chat_session, key=key).first()
            if fact:
                return f"Your {key.replace('_', ' ')} is {fact.value}."
>>>>>>> c88ac103dbcd299eccaf81ac54a241438167ebfc
            else:
                return f"I don't know your {key.replace('_', ' ')} yet."
    return None

<<<<<<< HEAD
def save_preferences(chat_session, preferences):
    """
    Save user preferences to SubMemory.
    """
    sub_memory = SubMemory.objects.get(chat_session=chat_session)
    for key, value in preferences.items():
        sub_memory.preferences[key] = value
    sub_memory.save()

def get_preferences(chat_session):
    sub_memory = SubMemory.objects.get(chat_session=chat_session)
    return sub_memory.preferences

def save_cache(chat_session, cache_data):
    cache_memory = CacheMemory.objects.get(chat_session=chat_session)
    cache_memory.cache = cache_data
    cache_memory.save()

def get_cache(chat_session):
    cache_memory = CacheMemory.objects.get(chat_session=chat_session)
    return cache_memory.cache

=======
>>>>>>> c88ac103dbcd299eccaf81ac54a241438167ebfc
def follow_up_handler(session, required_fields, user_input, extract_func, action_func, creds):
    data = session.get('pending_data', {}) or {}
    missing_fields = [f for f in required_fields if not data.get(f)]

    if missing_fields:
        extracted = extract_func(user_input, missing_fields)
        print(f"[DEBUG] Extracted: {extracted}")

        FIELD_ALIASES = {
            "to": "to_email", "recipient": "to_email",
<<<<<<< HEAD
            "title": "subject",  # FIXED for email subject
            "subject": "subject",
            "body": "body",
            "name": "summary"
=======
            "title": "task_title", "name": "summary"
>>>>>>> c88ac103dbcd299eccaf81ac54a241438167ebfc
        }

        for real_field in missing_fields:
            if real_field in extracted:
                data[real_field] = extracted[real_field]
            else:
                for gpt_key, target_field in FIELD_ALIASES.items():
                    if target_field == real_field and gpt_key in extracted:
                        data[real_field] = extracted[gpt_key]
                        break

        session['pending_data'] = data
        session.modified = True

    still_missing = [f for f in required_fields if not data.get(f)]
    if still_missing:
        next_field = still_missing[0]
        prompts = {
            "to_email": "Who should I send it to? (Please provide an email address)",
<<<<<<< HEAD
            "subject": "What is the subject of the email?",
=======
            "subject": "What is the subject?",
>>>>>>> c88ac103dbcd299eccaf81ac54a241438167ebfc
            "body": "What should the body/message say?",
            "task_title": "What is the task title?",
            "task_notes": "Any notes for the task?",
            "due_date": "When is it due? (e.g., 2025-06-01 or 2025-06-01T10:00:00Z)",
            "summary": "What is the event summary?",
            "start_time": "When does it start? (YYYY-MM-DDTHH:MM:SSZ)",
            "end_time": "When does it end? (YYYY-MM-DDTHH:MM:SSZ)",
            "description": "Any description for the event?",
            "location": "Where is the event?",
            "add_meet": "Should I add a Google Meet link? (yes/no)"
        }
        prompt = prompts.get(next_field, f"Please provide {next_field.replace('_', ' ')}.")
        return prompt

    try:
        params = {k: data.get(k) for k in required_fields if data.get(k) is not None}
        result = action_func(creds, **params)
        session['pending_intent'] = None
        session['pending_data'] = {}
        session.modified = True

        if isinstance(result, dict):
            if "id" in result and "title" in result:
                return f"✅ '{result['title']}' created (ID: {result['id']})"
            elif "summary" in result and "id" in result:
                return f"✅ Event '{result['summary']}' created (ID: {result['id']})"
            elif "htmlLink" in result:
                return f"Done! Here is the link: {result['htmlLink']}"
            else:
                import json
                return f"Done! Response: {json.dumps(result, indent=2)}"
        elif isinstance(result, str):
            return result
        else:
            return "Done!"
    except Exception as e:
        session['pending_intent'] = None
        session['pending_data'] = {}
        session.modified = True
        return f"Error: {str(e)}"