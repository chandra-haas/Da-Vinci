import requests
from django.conf import settings

class MicrosoftTokenError(Exception):
    pass

def exchange_code_for_token(code):
    token_url = f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "scope": "User.Read Mail.Read Mail.Send Files.ReadWrite.All offline_access",
        "code": code,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "grant_type": "authorization_code",
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
    }
    response = requests.post(token_url, data=data)
    if not response.ok:
        raise MicrosoftTokenError(f"Failed to exchange code for token: {response.status_code} {response.text}")
    return response.json()

def refresh_access_token(refresh_token):
    token_url = f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "scope": "User.Read Mail.Read Mail.Send Files.ReadWrite.All offline_access",
        "refresh_token": refresh_token,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "grant_type": "refresh_token",
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
    }
    response = requests.post(token_url, data=data)
    if not response.ok:
        raise MicrosoftTokenError(f"Failed to refresh access token: {response.status_code} {response.text}")
    return response.json()
