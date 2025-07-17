import requests
from django.conf import settings

class MicrosoftGraphAPIError(Exception):
    pass

# Define the scopes required for Microsoft Graph
SCOPES = [
    "User.Read",
    "Mail.Read",
    "Mail.Send",
    "Files.ReadWrite.All",
    "offline_access",
]

def get_access_token_from_session(session):
    tokens = session.get("microsoft_tokens")
    if not tokens or "access_token" not in tokens:
        raise MicrosoftGraphAPIError("Microsoft authentication required. Please log in with Microsoft.")
    return tokens["access_token"]

# -------------------------------
# GENERIC GRAPH REQUEST
# -------------------------------
import time

def graph_request(method, endpoint, session, payload=None, params=None):
    access_token = get_access_token_from_session(session)
    url = f"https://graph.microsoft.com/v1.0/{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    for attempt in range(2):  # Try twice: initial + retry after delay
        response = requests.request(method, url, headers=headers, json=payload, params=params)
        if response.ok:
            print(f"[DEBUG] Graph API Success {method} {url} → {response.status_code}")
            return response
        elif response.status_code == 401 and attempt == 0:
            print(f"[DEBUG] 401 Unauthorized. Retrying after short delay...")
            time.sleep(3)  # Delay before retry
        else:
            print(f"[DEBUG] Graph API Error {method} {url} → {response.status_code}: {response.text}")
            raise MicrosoftGraphAPIError(f"Graph API {method} {url} failed: {response.status_code} {response.text}")

# -------------------------------
# OUTLOOK MAIL
# -------------------------------
def send_outlook_mail(session, to_email, subject, body):
    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email
                    }
                }
            ]
        },
        "saveToSentItems": "true"
    }
    # This endpoint returns 202 Accepted on success
    graph_request("POST", "me/sendMail", session, payload=payload)
    return "✅ Email sent successfully via Outlook!"

# You can add more functions here for calendar, files, etc. following the same pattern.
