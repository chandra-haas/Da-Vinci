import json
from django.conf import settings
from openai import OpenAI
from chat_app.app_services.google.google_services import get_all_tasks

# Conversational, context-aware Google Tasks reading assistant

def handle(user_input, **kwargs):
    """
    Conversational handler for 'google_tasks.read'.
    Lists pending (not completed) tasks with details. Congratulates user if none.
    """
    session = kwargs.get('session', {})
    creds = kwargs.get('creds')
    tasks = get_all_tasks(creds, max_results=20)
    pending = [t for t in tasks if t.get('status', '').lower() != 'completed']
    if not pending:
        return "🎉 You have no pending tasks. Congratulations on completing everything!"
    msg = f"You have {len(pending)} pending tasks:\n"
    for i, t in enumerate(pending, 1):
        title = t.get('title', '(no title)')
        due = t.get('due', None)
        notes = t.get('notes', '').strip()
        if due:
            due = due.split('T')[0]
            msg += f"{i}. {title} (Due: {due})\n"
        else:
            msg += f"{i}. {title}\n"
        if notes:
            msg += f"   - Details: {notes}\n"
    msg += "\nKeep up the good work!"
    return msg
