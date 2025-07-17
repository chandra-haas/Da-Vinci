import re
from datetime import datetime

from datetime import datetime, timedelta
import re
import json
from django.conf import settings
from openai import OpenAI

# Enhanced: robust natural language due date parsing
try:
    import dateparser
except ImportError:
    dateparser = None

# Helper: parse natural language due dates
def parse_due_date(text):
    text = text.strip().lower()
    today = datetime.today()
    def to_rfc3339(dt):
        return dt.strftime('%Y-%m-%dT00:00:00.000Z')
    if text in {'skip', 'none', 'no', ''}:
        return ''
    # Try using dateparser if available
    if dateparser:
        dt = dateparser.parse(text, settings={"PREFER_DATES_FROM": "future", "RELATIVE_BASE": today})
        if dt:
            return to_rfc3339(dt)
    # Fallback to manual logic for some common phrases
    if text in {'today'}:
        return to_rfc3339(today)
    if text in {'tonight', 'this evening'}:
        # If after 6pm, treat as today, else today
        if today.hour >= 18:
            return to_rfc3339(today + timedelta(days=1))
        else:
            return to_rfc3339(today)
    if text in {'tomorrow'}:
        return to_rfc3339(today + timedelta(days=1))
    if text in {'next week', 'a week', 'in a week'}:
        return to_rfc3339(today + timedelta(days=7))
    # e.g. 'next monday', 'next friday', etc.
    weekdays = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    for i, wd in enumerate(weekdays):
        if text == f'next {wd}':
            days_ahead = (i - today.weekday() + 7) % 7
            days_ahead = days_ahead or 7
            return to_rfc3339(today + timedelta(days=days_ahead))
    # e.g. 'in 3 days', 'in 2 weeks'
    m = re.match(r'in (\d+) days?', text)
    if m:
        return to_rfc3339(today + timedelta(days=int(m.group(1))))
    m = re.match(r'in (\d+) weeks?', text)
    if m:
        return to_rfc3339(today + timedelta(weeks=int(m.group(1))))
    # e.g. '26 dec', 'dec 26', '26 december', 'december 26'
    try:
        for fmt in [
            '%d %b', '%d %B', '%b %d', '%B %d',
            '%d-%m', '%d/%m', '%m-%d', '%m/%d',
            '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d'
        ]:
            try:
                dt = datetime.strptime(text, fmt)
                # If year not provided, assume this year or next if already passed
                if '%Y' not in fmt:
                    dt = dt.replace(year=today.year)
                    if dt < today:
                        dt = dt.replace(year=today.year + 1)
                return to_rfc3339(dt)
            except ValueError:
                continue
    except Exception:
        pass
    # If user enters a valid YYYY-MM-DD, convert to RFC3339
    try:
        dt = datetime.strptime(text, '%Y-%m-%d')
        return to_rfc3339(dt)
    except Exception:
        pass
    return ''  # fallback: return empty if not parseable

# GPT-powered extraction
def gpt_extract_task_fields(user_input):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = (
        "Extract the title, details, and due date for a Google Task from the following message. "
        "Respond in JSON with keys: title, details, due_date. "
        "If a field is missing, return it as an empty string. "
        "Interpret due dates like 'today', 'tomorrow', 'next week', or specific dates (e.g., '26 dec').\n"
        f"Message: {user_input}\n"
        "Example output: {\"title\": \"call Alice\", \"details\": \"about the project\", \"due_date\": \"tomorrow\"}"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"title": "", "details": "", "due_date": ""}

# GPT-powered smart description generator
def gpt_generate_task_description(title, user_input):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = (
        f"Write a helpful, concise description for a Google Task.\n"
        f"Title: {title}\n"
        f"User input: {user_input}\n"
        f"Description: "
    )
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""


def handle(user_input, **kwargs):
    """
    Robust, GPT-powered handler for 'google_tasks.add'.
    Uses GPT for initial extraction, then stepwise fallback for missing fields.
    Accepts natural language due dates.
    """
    session = kwargs.get('session', {})
    field_order = ['title', 'details', 'due_date']
    optional_fields = ['details', 'due_date']
    skip_words = {'skip', 'none', 'no'}
    prompts = {
        'title': "What is the title of your task?",
        'details': "Any details or description for this task? (You can say 'skip' if none)",
        'due_date': "When is this task due? (e.g. today, tomorrow, 26 dec, YYYY-MM-DD, or say 'skip')"
    }
    trigger_phrases = [
        'add', 'add a task', 'create task', 'add task', 'new task',
        'create a task', 'add google task', 'create google task',
        'add to tasks', 'google task', 'task', 'make a task', 'add reminder',
        'add todo', 'create todo', 'add to todo', 'todo', 'add an item',
        'create an item', 'add something', 'create something'
    ]

    # Start a new flow if session is empty or user triggers a new add
    if kwargs.get('new_intent') or ('task_state' not in session):
        session['task_state'] = {}
        # Use GPT to extract as much as possible
        gpt_fields = gpt_extract_task_fields(user_input)
        # Always parse due_date to RFC3339
        gpt_fields['due_date'] = parse_due_date(gpt_fields.get('due_date', ''))
        # Don't allow skip/trigger for title
        if gpt_fields['title'].strip().lower() in skip_words or gpt_fields['title'].strip().lower() in trigger_phrases or not gpt_fields['title'].strip():
            gpt_fields['title'] = ''
        # If details is empty, generic, or just repeats the title, generate a smart description
        details = gpt_fields.get('details', '').strip()
        if not details or details.lower() == gpt_fields['title'].strip().lower() or details.lower().startswith('add a task') or details == user_input.strip():
            gpt_fields['details'] = gpt_generate_task_description(gpt_fields['title'], user_input)
        session['task_state'].update(gpt_fields)
    state = session['task_state']

    # Find which field is missing
    for field in field_order:
        if field not in state or not state[field].strip():
            current_field = field
            break
    else:
        current_field = None

    user_val = user_input.strip()

    # Step: process only the current field
    if current_field == 'title':
        # Don't accept skip/none/no or trigger phrases for title
        if user_val.lower() in skip_words or user_val.lower() in trigger_phrases or not user_val:
            session['task_state'] = state
            session['task_active'] = True
            return "A task must have a title. Please provide a title for your task."
        state['title'] = user_val
        session['task_state'] = state
        session['task_active'] = True
        return prompts['details']
    elif current_field == 'details':
        if user_val.lower() in skip_words:
            state['details'] = ''
        else:
            state['details'] = user_val
        session['task_state'] = state
        session['task_active'] = True
        return prompts['due_date']
    elif current_field == 'due_date':
        if user_val.lower() in skip_words:
            state['due_date'] = ''
        else:
            state['due_date'] = parse_due_date(user_val)
        # All fields collected, proceed to create task
        creds = kwargs.get('creds')
        from chat_app.app_services.google.google_services import add_google_task
        try:
            result = add_google_task(
                creds,
                state['title'],
                task_notes=state.get('details'),
                due_date=state.get('due_date')
            )
            response = (
                f"Task created: {state['title']}\n"
                f"Details: {state.get('details', '')}\n"
                f"Due date: {state.get('due_date', '')}\n"
                f"✅ Google Tasks API response: {result}"
            )
        except Exception as e:
            response = (
                f"Failed to create task: {state['title']}\n"
                f"Details: {state.get('details', '')}\n"
                f"Due date: {state.get('due_date', '')}\n"
                f"❌ Error: {e}"
            )
        # Clear state
        session.pop('task_state', None)
        session['task_active'] = False
        return response
    else:
        # Defensive fallback: start from title
        session['task_state'] = {}
        session['task_active'] = True
        return prompts['title']
