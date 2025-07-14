import re

def is_valid_email_param(value, param_name):
    """
    Helper to validate email and other required params for Google actions.
    """
    if param_name == "to_email":
        if not value:
            return False
        # Accept comma-separated emails or single email
        emails = [e.strip() for e in value.split(",")]
        for email in emails:
            if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
                return False
        return True
    elif param_name in ["subject", "body", "task_title", "task_notes", "due_date", "summary", "start_time", "end_time", "description", "location"]:
        return bool(value and str(value).strip())
    elif param_name == "add_meet":
        return value in [True, False]
    return bool(value)
