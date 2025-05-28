import re
from datetime import datetime
import dateparser

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

def follow_up_handler(session, required_fields, user_input, extract_func, action_func, creds):
    data = session.get('pending_data', {}) or {}
    missing_fields = [f for f in required_fields if not data.get(f)]

    if missing_fields:
        extracted = extract_func(user_input, missing_fields)
        print(f"[DEBUG] Extracted: {extracted}")

        FIELD_ALIASES = {
            "to": "to_email", "recipient": "to_email",
            "title": "task_title", "name": "summary"
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
            "subject": "What is the subject?",
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
