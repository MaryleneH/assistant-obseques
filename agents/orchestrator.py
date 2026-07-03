"""
Orchestrator Agent for Assistant Obsèques.
Manages the end-to-end multi-agent pipeline and state transitions.
"""
from typing import List
from .models import Record, CeremonyStatus
from .extractor import extract_record
from .checker import check_record
from .writer import write_record
from tools.deroule import build_deroule

from tools.mcp_clients import create_gmail_draft, append_ceremony_row

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
    """
    if not record.security.humanValidated:
        raise ValueError("Record must be explicitly human-validated before proceeding.")
    if record.status != CeremonyStatus.ready_for_generation:
        raise ValueError("Record status must be 'ready_for_generation'.")
        
    # Generate content
    record = write_record(record)
    record = build_deroule(record)
    
    # Run external MCP tools
    draft_result = create_gmail_draft(record)
    if draft_result:
        print(f"-> GMAIL DRAFT CREATED: {draft_result}")
        
    record.communication.emailDraftCreated = True
    record.status = CeremonyStatus.email_draft_created
    
    append_result = append_ceremony_row(record)
    if append_result:
        print(f"-> SHEETS ROW APPENDED: {append_result}")
    
    return record
