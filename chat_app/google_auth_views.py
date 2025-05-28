import json
from django.shortcuts import redirect
from django.conf import settings
from django.http import JsonResponse
from .google_services import get_auth_flow, build_credentials_from_code

def google_login(request):
    print("[DEBUG] Redirecting to Google login...")
    flow = get_auth_flow()
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    return redirect(auth_url)


def google_auth_callback(request):
    print("[DEBUG] Google auth callback hit...")

    try:
        code = request.GET.get('code')
        if not code:
            return JsonResponse({'error': 'Missing authorization code'}, status=400)

        creds = build_credentials_from_code(code)

        # Save credentials to session for reuse
        request.session['google_credentials'] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
        }
        print("[DEBUG] Credentials saved to session.")

        return redirect('/')  # or wherever you want to redirect after login

    except Exception as e:
        print(f"[DEBUG] Exception during auth callback: {e}")
        return JsonResponse({'error': str(e)}, status=500)
