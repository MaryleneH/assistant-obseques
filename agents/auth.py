"""
Google Auth Helper for Assistant Obsèques.
Provides an OAuth 2.0 Installed App Flow for Gmail MCP.
"""
import os
import json
import logging
from typing import Optional
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Scopes needed for Gmail + Drive (single OAuth grant for the sacristan)
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/drive.file',   # upload déroulé as Google Doc
]

TOKEN_FILE = 'token.local.json'

def get_google_credentials() -> Credentials:
    """
    Obtains valid Google OAuth2 credentials.
    Reads GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET from environment.
    Caches the token to token.local.json for reuse.
    """
    creds = None
    
    # Load cached token if it exists
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logging.warning(f"Failed to load cached token: {e}")

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.warning(f"Failed to refresh token: {e}")
                creds = None

        if not creds:
            raise ValueError(f"No valid OAuth token found. Please run 'python agents/auth.py' first to authorize.")

    return creds

def _run_interactive_auth():
    """
    Runs the interactive OAuth consent flow and saves the token.
    Intended to be run manually by the user.
    """
    from utils.env import load_environment
    load_environment()
    
    client_id = os.getenv("GMAIL_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GMAIL_OAUTH_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise ValueError("GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET must be set in .env")
    
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"]
        }
    }
    
    logging.info("Initiating Google OAuth flow...")
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    
    # Run the interactive local server flow
    creds = flow.run_local_server(port=0)
    
    with open(TOKEN_FILE, 'w') as token:
        token.write(creds.to_json())
        
    print("Token saved — subsequent runs are non-interactive.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _run_interactive_auth()