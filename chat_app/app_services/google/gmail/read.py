import json
from django.conf import settings
from openai import OpenAI
from chat_app.app_services.google.google_services import get_gmail_messages

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Helper to fetch and hydrate emails with metadata
from googleapiclient.discovery import build

def fetch_full_emails(creds, max_results=10):
    service = build('gmail', 'v1', credentials=creds)
    base = get_gmail_messages(creds, max_results=max_results)
    ids = [msg['id'] for msg in base.get('messages', [])]
    emails = []
    for mid in ids:
        msg = service.users().messages().get(userId='me', id=mid, format='full').execute()
        emails.append(msg)
    return emails

def gpt_classify_and_summarize(emails, user_context=None):
    """
    Use GPT to classify, summarize, and suggest actions for emails.
    Returns a list of dicts: [{summary, category, priority, actions, ...}]
    """
    # Prepare a prompt with all emails as JSON
    prompt = (
        "You are an intelligent email assistant. Given the following emails (as JSON), classify each as one of: Work, Personal, Promotions, Newsletter, Calendar, Other. "
        "Also, assign a priority (High, Normal, Low) based on sender, content, and recent user context.\n"
        "Summarize each email in 1-2 sentences.\n"
        "For emails with calendar invites, tasks, or attachments, suggest smart actions.\n"
        "Respond as a JSON list, each item with keys: subject, from, summary, category, priority, actions (list of suggestions), id.\n"
    )
    # Extract minimal info for the LLM
    email_objs = []
    for em in emails:
        headers = {h['name'].lower(): h['value'] for h in em['payload']['headers']}
        email_objs.append({
            'id': em['id'],
            'from': headers.get('from', ''),
            'subject': headers.get('subject', ''),
            'snippet': em.get('snippet', ''),
            'labels': em.get('labelIds', []),
        })
    llm_input = json.dumps(email_objs)
    if user_context:
        prompt += f"\nUser context: {user_context}"
    prompt += f"\nEmails: {llm_input}"
    try:
        result = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0
        )
        content = result.choices[0].message.content.strip()
        return json.loads(content)
    except Exception as e:
        print(f"[DEBUG] GPT email classify/summarize failed: {e}")
        # Fallback: just return basic summaries
        return [{
            'id': em['id'],
            'from': em['payload']['headers'][0]['value'],
            'subject': em['payload']['headers'][1]['value'],
            'summary': em.get('snippet', ''),
            'category': 'Other',
            'priority': 'Normal',
            'actions': [],
        } for em in emails]

def handle(user_input, **kwargs):
    """
    Conversational, context-aware Gmail reading assistant.
    """
    session = kwargs.get('session', {})
    creds = kwargs.get('creds')
    # Step 1: Clarify context if needed
    if not session.get('gmail_read_context_clarified'):
        session['gmail_read_context_clarified'] = True
        return (
            "Do you want to hear only important unread emails, or all new emails from today? "
            "Should I include promotional or social updates too?"
        )
    # Step 2: Fetch and classify emails
    emails = fetch_full_emails(creds, max_results=10)
    summaries = gpt_classify_and_summarize(emails, user_context=user_input)
    # Step 3: Store summaries in session for navigation
    session['gmail_email_summaries'] = summaries
    session['gmail_read_index'] = 0
    # Step 4: Present first summary
    if not summaries:
        return "📭 No recent emails found."
    first = summaries[0]
    msg = (
        f"You have {len(summaries)} recent emails.\n"
        f"The first one is from {first['from']} about '{first['subject']}'.\n"
        f"Summary: {first['summary']}\n"
        f"Category: {first['category']}, Priority: {first['priority']}\n"
    )
    if first['actions']:
        msg += "Suggested actions: " + ", ".join(first['actions']) + "\n"
    msg += "Say 'next', 'read full', or ask for a smart action."
    session['gmail_read_context_clarified'] = True
    return msg
