import openai
import json
from django.conf import settings

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

def gpt_param_extractor(user_input, fields):
    prompt = (
        f"Extract the following fields from the user's message. "
        f"Respond ONLY in raw JSON (no code block, no explanation). "
        f"Fields: {', '.join(fields)}.\n\n"
        f"User input: \"{user_input}\""
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=150,
            temperature=0
        )
        raw = response.choices[0].message.content.strip()

        # 🧼 Remove triple backticks or formatting
        if raw.startswith("```json"):
            raw = raw[7:].strip()
        elif raw.startswith("```"):
            raw = raw[3:].strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()

        return json.loads(raw)

    except Exception as e:
        print(f"[DEBUG] GPT extraction failed: {e}")
        return {}


def follow_up_handler(session, required_fields, user_input, extract_func, action_func, creds=None):
    data = session.get('pending_data', {}) or {}
    missing_fields = [f for f in required_fields if not data.get(f)]

    if missing_fields:
        extracted = extract_func(user_input, missing_fields)
        print(f"[DEBUG] Extracted from GPT: {extracted}")

        # 🧭 Remap fields if GPT returns aliases
        FIELD_ALIASES = {
            "to": "to_email",
            "recipient": "to_email",
        }

        for real_field in missing_fields:
            # Try exact match
            if real_field in extracted:
                data[real_field] = extracted[real_field]
            else:
                # Try alias mapping
                for gpt_key, target_field in FIELD_ALIASES.items():
                    if target_field == real_field and gpt_key in extracted:
                        data[real_field] = extracted[gpt_key]
                        break

        session['pending_data'] = data
        session.modified = True

        still_missing = [f for f in required_fields if not data.get(f)]
        if still_missing:
            return f"What is the {still_missing[0]}?"

        # ✅ All fields filled → Run action
                # ✅ All fields filled → Run action
        print(f"[DEBUG] Calling action_func with: {data}")

        # ✂️ Filter only expected keys
        clean_data = {k: data[k] for k in required_fields}

        result = action_func(creds, **clean_data)
        session.pop('pending_intent', None)
        session.pop('pending_data', None)
        session.modified = True
        return "✅ Email sent successfully."


    return "I'm not sure what you're asking me to do."
