from django.conf import settings
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Scopes required for Google services
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/calendar',
]

# -------------------------------
# AUTHENTICATION UTILITIES
# -------------------------------

class MissingCredentials(Exception):
    pass

def get_auth_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )

def build_credentials_from_code(code):
    flow = get_auth_flow()
    flow.fetch_token(code=code)
    return flow.credentials

def build_credentials_from_session(session):
    creds_data = session.get('google_credentials')
    if not creds_data:
        raise MissingCredentials("No credentials found in session.")
    return Credentials(**creds_data)

def get_user_credentials(session):
    try:
        return build_credentials_from_session(session)
    except MissingCredentials as e:
        raise e

# -------------------------------
# GMAIL
# -------------------------------

def get_gmail_messages(creds, max_results=5):
    service = build('gmail', 'v1', credentials=creds)
    return service.users().messages().list(userId='me', maxResults=max_results).execute()

def send_gmail_message(creds, to_email, subject, body):
    footer = '<br><br><span style="color: #999999; font-size: 7pt;">Sent from <strong>Da_Vinci</strong></span>'
    full_body = body.replace('\n', '<br>') + footer

    message = MIMEMultipart('alternative')
    message['to'] = ', '.join(to_email) if isinstance(to_email, list) else to_email
    message['subject'] = subject

    html_part = MIMEText(full_body, 'html')
    message.attach(html_part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service = build('gmail', 'v1', credentials=creds)
    return service.users().messages().send(userId='me', body={'raw': raw}).execute()

# -------------------------------
# GOOGLE DRIVE
# -------------------------------

def get_drive_files(creds, page_size=10):
    service = build('drive', 'v3', credentials=creds)
    return service.files().list(pageSize=page_size).execute()

# -------------------------------
# GOOGLE TASKS
# -------------------------------

def get_tasks(creds, max_results=10):
    service = build('tasks', 'v1', credentials=creds)
    return service.tasklists().list(maxResults=max_results).execute()

def get_all_tasks(creds, max_results=10):
    service = build('tasks', 'v1', credentials=creds)
    tasklists = service.tasklists().list(maxResults=1).execute()
    if not tasklists.get('items'):
        return []

    tasklist_id = tasklists['items'][0]['id']
    tasks = service.tasks().list(tasklist=tasklist_id, maxResults=max_results).execute()
    return tasks.get('items', [])

def add_google_task(creds, task_title, task_notes=None, due_date=None, tasklist_id=None):
    service = build('tasks', 'v1', credentials=creds)
    if not tasklist_id:
        tasklists = service.tasklists().list(maxResults=1).execute()
        if not tasklists.get('items'):
            raise Exception("No Google Task lists found for this user.")
        tasklist_id = tasklists['items'][0]['id']

    task_body = {'title': task_title}
    if task_notes:
        task_body['notes'] = task_notes
    if due_date:
        task_body['due'] = due_date  # RFC 3339 format required

    return service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()

# -------------------------------
# GOOGLE CALENDAR
# -------------------------------

def get_calendar_events(creds, max_results=10):
    service = build('calendar', 'v3', credentials=creds)
    return service.events().list(calendarId='primary', maxResults=max_results).execute()

def create_calendar_event(
    creds,
    summary,
    start_time,
    end_time,
    description=None,
    location=None,
    add_meet=False
):
    service = build('calendar', 'v3', credentials=creds)

    event = {
        'summary': summary,
        'start': {'dateTime': start_time, 'timeZone': 'UTC'},
        'end': {'dateTime': end_time, 'timeZone': 'UTC'},
    }
    if description:
        event['description'] = description
    if location:
        event['location'] = location
    if add_meet:
        event['conferenceData'] = {
            'createRequest': {
                'requestId': 'meet-' + summary.lower().replace(' ', '-'),
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        }

    return service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1 if add_meet else 0
    ).execute()