"""
Orchestrator Agent for Assistant Obsèques.
Manages the end-to-end multi-agent pipeline and state transitions.
"""
import logging
from typing import List
from .models import Record, CeremonyStatus
from .extractor import extract_record
from .checker import check_record
from .writer import write_record
from tools.deroule import build_deroule

from tools.mcp_clients import create_gmail_draft, append_ceremony_row, create_deroule_gdoc

def run_until_review(pages: List[str]) -> Record:
    """
    Phase 1: Extraction and Safety/Quality Checking.
    The pipeline STOPS here by design, waiting for human validation.
    """
    record = extract_record(pages)
    record = check_record(record)
    assert record.status == CeremonyStatus.needs_review, "Record did not transition to needs_review"
    return record

def run_after_validation(record: Record) -> Record:
    """
    Phase 2: Generation and Output creation.
    Requires a human-validated record to proceed.
    
    Returns the record. The record's communication fields are populated,
    and if the Gmail draft used the fallback recipient (SACRISTAN_EMAIL),
    record._draft_fallback is set to True (non-model attribute, used only
    by the UI layer for Screen C wording).
    """
    if not record.security.humanValidated:
        raise ValueError("Record must be explicitly human-validated before proceeding.")
    if record.status != CeremonyStatus.ready_for_generation:
        raise ValueError("Record status must be 'ready_for_generation'.")
        
    # Generate content
    record = write_record(record)
    record = build_deroule(record)
    
    # Upload the .docx to Google Drive as a native Google Doc.
    # Failure here must NOT abort the pipeline — draft + sheet still matter.
    try:
        gdoc_link = create_deroule_gdoc(record)
        if gdoc_link:
            record.communication.gdocLink = gdoc_link
            print(f"-> GDOC CREATED: {gdoc_link}")
        else:
            logging.warning("Drive: Google Doc upload returned None (see logs above).")
    except Exception as e:
        logging.error("Drive: Google Doc upload failed (non-fatal): %s", e, exc_info=True)
        record.communication.gdocLink = None

    # Run external MCP tools
    draft_result = create_gmail_draft(record)
    # Track whether the fallback recipient was used so the UI can show
    # the appropriate notice on Screen C. We use object.__setattr__
    # to bypass Pydantic's strict attribute checks (no schema change).
    draft_fallback = False
    draft_attachment = False
    if draft_result:
        print(f"-> GMAIL DRAFT CREATED: {draft_result}")
        draft_fallback = bool(draft_result.get('fallback_recipient'))
        draft_attachment = bool(draft_result.get('attachment'))
        
    record.communication.emailDraftCreated = True
    record.status = CeremonyStatus.email_draft_created
    
    append_result = append_ceremony_row(record)
    if append_result:
        print(f"-> SHEETS ROW APPENDED: {append_result}")
    
    # Attach non-model metadata for UI consumption
    record.__dict__['_draft_fallback'] = draft_fallback
    record.__dict__['_draft_attachment'] = draft_attachment
    
    return record

