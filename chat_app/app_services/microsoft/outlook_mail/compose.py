from django.conf import settings
from ..microsoft_graph_service import send_outlook_mail, MicrosoftGraphAPIError

def handle(user_input, **kwargs):
    """
    Handles the 'outlook_mail.compose' intent.
    Args:
        user_input (str): The original user input (e.g., "Send an email to John with subject Hello")
        **kwargs: Should include 'session' (Django session) and optionally parsed fields
    Returns:
        str: Result message
    """
    session = kwargs.get("session")
    tokens = session.get("microsoft_tokens")
    print("[DEBUG] microsoft_tokens in session:", session.get("microsoft_tokens"))
    print("[DEBUG] Inside compose.py handler")
    print("[DEBUG] Session microsoft_tokens:", session.get("microsoft_tokens"))
    if not tokens or "access_token" not in tokens:
        return {
            "response": "❌ Microsoft authentication required. Please log in with Microsoft.",
            "auth_required": True,
            "login_url": "/auth/microsoft/login/"
        }

    # TODO: Parse user_input to extract recipient, subject, and body.
    # For now, we'll use placeholder values.
    to_email = "akshithreddy542@outlook.com"
    subject = "Hello from Da_Vinci"
    body = "This is a test email sent via Microsoft Graph API."

    try:
        result = send_outlook_mail(session, to_email, subject, body)
        print("[DEBUG] send_outlook_mail result:", result)
        return result
    except MicrosoftGraphAPIError as e:
        return {
            "response": f"❌ Failed to send email. {str(e)}",
            "status": 500
        }