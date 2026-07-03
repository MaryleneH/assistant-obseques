"""
MCP Clients for Assistant Obsèques.
Provides thin wrappers to interact with external MCP servers for Google Sheets and Gmail.
"""
import os
import logging
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, List
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters

from agents.models import Record
from agents.auth import get_google_credentials

# Cache discovered tool lists to log them only once at startup
_GMAIL_TOOLS_DISCOVERED = False
_SHEETS_TOOLS_DISCOVERED = False

import base64
from email.message import EmailMessage
from googleapiclient.discovery import build

def create_gmail_draft(record: Record) -> Any:
    """
    Fallback: Official Gmail MCP server is Developer-Preview-gated.
    We create the draft via the Gmail API directly, using the same OAuth credentials
    (gmail.readonly + gmail.compose).
    """
    recipients = []
    if record.communication.priestEmail:
        recipients.append(record.communication.priestEmail)
    if record.communication.teamEmails:
        recipients.extend(record.communication.teamEmails)
        
    if not recipients:
        logging.info("Gmail: No recipients defined (priestEmail/teamEmail). Skipping draft creation.")
        return None

    creds = get_google_credentials()
    service = build('gmail', 'v1', credentials=creds)

    subject = record.communication.emailSubject
    body_text = record.communication.emailBody

    message = EmailMessage()
    message.set_content(body_text)
    message['To'] = ", ".join(recipients)
    message['Subject'] = subject

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {'message': {'raw': encoded_message}}

    try:
        logging.info("Gmail: Calling drafts().create()...")
        draft = service.users().drafts().create(userId="me", body=create_message).execute()
        logging.info(f"-> GMAIL DRAFT CREATED: id={draft['id']}")
        return draft
    except Exception as e:
        logging.error(f"Failed to create Gmail draft: {e}")
        return None


def append_ceremony_row(record: Record) -> Any:
    """
    Fallback: mcp-z/mcp-sheets fails on Windows path parsing (ENOENT C:\\C:\\...).
    We append the row via the Google Sheets API directly using the service account.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    sheet_id = os.getenv("SHEET_ID")
    if not sheet_id:
        raise ValueError("SHEET_ID env var must be set for Sheets API.")
        
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY_FILE")
    if not key_file:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_KEY_FILE env var must be set for Sheets API.")
        
    creds = service_account.Credentials.from_service_account_file(
        key_file,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    service = build('sheets', 'v4', credentials=creds)

    row_data = [
        record.caseId,
        record.status.value,
        record.deceased.name if hasattr(record.deceased, 'name') else f"{record.deceased.lastName} {record.deceased.firstName}",
        str(record.deceased.age),
        record.participants.mainFamilyContact.name if record.participants.mainFamilyContact else "",
        record.participants.mainFamilyContact.phone if record.participants.mainFamilyContact else "",
        record.participants.mainFamilyContact.email if record.participants.mainFamilyContact else "",
        record.ceremony.date,
        record.ceremony.time,
        json.dumps([step.model_dump() for step in record.ceremony.liturgySteps], ensure_ascii=False)
    ]
    
    headers = [
        "caseId", "status", "deceasedName", "deceasedAge", 
        "contactName", "contactPhone", "contactEmail", 
        "date", "time", "liturgy_json"
    ]
    
    sheet = service.spreadsheets()
    
    # Try to get existing rows to check if we need to write headers
    logging.info(f"Sheets API: Checking if sheet {sheet_id} is empty...")
    try:
        result = sheet.values().get(spreadsheetId=sheet_id, range="Sheet1!A1:A2").execute()
        values = result.get('values', [])
    except Exception as e:
        logging.warning(f"Failed to read sheet: {e}. Assuming empty.")
        values = []
        
    if not values:
        logging.info("Sheets API: Sheet appears empty, bootstrapping headers...")
        body = {'values': [headers]}
        sheet.values().append(
            spreadsheetId=sheet_id, range="Sheet1!A1",
            valueInputOption="USER_ENTERED", body=body).execute()
            
    logging.info("Sheets API: Appending ceremony row...")
    body = {'values': [row_data]}
    append_result = sheet.values().append(
        spreadsheetId=sheet_id, range="Sheet1!A1",
        valueInputOption="USER_ENTERED", body=body).execute()
        
    updates = append_result.get('updates', {})
    logging.info(f"-> SHEETS ROW APPENDED: range={updates.get('updatedRange')}")
    return updates
