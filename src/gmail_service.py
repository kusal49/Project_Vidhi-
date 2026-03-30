"""
Gmail OAuth authentication and email sending.

"""
import os
import base64
from email.mime.text import MIMEText

from .utils.config import gmail_credentials_path, gmail_token_path


# Cached Gmail API service ─────────────────────────────────────────────────
_gmail_service = None


def _build_gmail_service():
    """Build and cache the Gmail API service."""
    global _gmail_service
    if _gmail_service is not None:
        return _gmail_service

    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
    creds = None
    token_path = gmail_token_path()
    creds_path = gmail_credentials_path()

    # Load existing token
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # Refresh or create new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save token for next time
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    _gmail_service = build("gmail", "v1", credentials=creds)
    return _gmail_service


def pre_authenticate():
    """
    Pre-authenticate Gmail. Call this from the UI thread so the OAuth
    browser flow doesn't block inside the LangGraph pipeline.
    Returns True if authentication succeeded.
    """
    try:
        service = _build_gmail_service()
        # Quick test — get user profile
        service.users().getProfile(userId="me").execute()
        return True
    except Exception as e:
        print(f"[Gmail] Pre-auth failed: {e}")
        return False


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Send an email using Gmail API directly.
    Returns True if sent successfully.
    """
    service = _build_gmail_service()

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()
    return True


def gmail_configured() -> bool:
    """Returns True if credentials.json exists."""
    return os.path.exists(gmail_credentials_path())


def gmail_authenticated() -> bool:
    """Returns True if token.json exists (OAuth completed)."""
    return os.path.exists(gmail_token_path())

