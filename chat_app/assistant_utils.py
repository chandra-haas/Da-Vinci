FEATURE_TO_SERVICE = {
    # Google features
    "gmail": "google",
    "google_tasks": "google",
    "google_drive": "google",
    "calendar": "google",
    "gnotes": "google",
    "google_meet": "google",
    # Microsoft features
    "outlook_mail": "microsoft",
    "microsoft_todo": "microsoft",
    "microsoft_teams": "microsoft",
    "one_drive": "microsoft",
    # Brave features
    "brave": "brave",
    # Add more as needed
}

import importlib

def handle_intent(intent: str, user_input: str, **kwargs):
    """
    Routes the intent to its dedicated handler module, using the modular path.
    For example, 'gmail.compose' -> chat_app.app_services.google.gmail.compose
    """
    try:
        parts = intent.split('.')
        if len(parts) == 2:
            feature, action = parts
            service = FEATURE_TO_SERVICE.get(feature)
            if not service:
                return f"Unknown service for feature: {feature}"
        elif len(parts) == 3:
            service, feature, action = parts
        else:
            return f"Invalid intent format: {intent}"

        module_path = f"chat_app.app_services.{service}.{feature}.{action}"
        handler_module = importlib.import_module(module_path)
        if hasattr(handler_module, "handle"):
            return handler_module.handle(user_input, **kwargs)
        else:
            return f"Handler for intent '{intent}' does not implement a 'handle' function."
    except ImportError as e:
        return f"No handler found for intent: {intent} ({e})"
    except Exception as e:
        return f"Error while handling intent '{intent}': {str(e)}"
