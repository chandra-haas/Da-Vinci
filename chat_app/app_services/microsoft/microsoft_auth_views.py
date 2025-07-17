import json
from django.shortcuts import redirect
from django.conf import settings
from django.http import JsonResponse
import urllib.parse
from .microsoft_token_service import exchange_code_for_token, MicrosoftTokenError

def microsoft_login(request):
    print("[DEBUG] Redirecting to Microsoft login...")
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "response_mode": "query",
        "scope": "User.Read Mail.Read Mail.Send Files.ReadWrite.All offline_access",
        "state": "random_state_string",
    }
    url = (
        f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize?"
        + urllib.parse.urlencode(params)
    )
    return redirect(url)

def microsoft_auth_callback(request):
    print("[DEBUG] Microsoft auth callback hit...")
    try:
        code = request.GET.get("code")
        if not code:
            return JsonResponse({'error': 'Missing authorization code'}, status=400)

        try:
            tokens = exchange_code_for_token(code)
            print("[DEBUG] Scopes in token:", tokens.get('scope'))
        except MicrosoftTokenError as e:
            print("[DEBUG] Microsoft token exchange error:", str(e))
            return JsonResponse({'error': str(e)}, status=400)

        # Validate access_token
        access_token = tokens.get('access_token')
        if not access_token or '.' not in access_token:
            print("[DEBUG] Invalid or missing access_token in Microsoft token response:", tokens)
            return JsonResponse({'error': 'Failed to obtain valid Microsoft access token', 'token_response': tokens}, status=400)

        # Save only relevant tokens to session for reuse
        session_tokens = {
            'access_token': access_token,
            'refresh_token': tokens.get('refresh_token'),
            'expires_in': tokens.get('expires_in'),
            'scope': tokens.get('scope'),
            'token_type': tokens.get('token_type'),
        }
        request.session['microsoft_tokens'] = session_tokens
        request.session.modified = True  # <--- Force save
        print("[DEBUG] Microsoft tokens saved to session:", session_tokens)

        return redirect('/')  # or wherever you want to redirect after login

    except Exception as e:
        print(f"[DEBUG] Exception during Microsoft auth callback: {e}")
        return JsonResponse({'error': str(e)}, status=500)