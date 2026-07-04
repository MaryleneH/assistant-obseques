"""
Orchestrator Agent for Assistant Obsèques.
Manages the end-to-end multi-agent pipeline and state transitions.

Observability: each pipeline run is traced via Langfuse (opt-in).
One trace per case, one span per pipeline step.  PRIVACY DEFAULT:
traces carry operational metadata only (model id, duration, counts,
status).  Note/record content is sent ONLY when LANGFUSE_TRACE_CONTENT=true
— intended for fictional dev runs.
"""
import os
import logging
import time
from typing import List
from .models import Record, CeremonyStatus
from .extractor import extract_record
from .checker import check_record
from .writer import write_record
from .telemetry import get_client, safe_input, safe_output, safe_metadata
from tools.deroule import build_deroule

from tools.mcp_clients import create_gmail_draft, append_ceremony_row, create_deroule_gdoc

logger = logging.getLogger(__name__)


def _span(client, name: str, **kwargs):
    """Shorthand: open a child span under the current trace context."""
    return client.start_as_current_observation(name=name, as_type="span", **kwargs)


def run_until_review(pages: List[str]) -> Record:
    """
    Phase 1: Extraction and Safety/Quality Checking.
    The pipeline STOPS here by design, waiting for human validation.
    """
    lf = get_client()

    with _span(lf, name="orchestrator.run_until_review",
               metadata=safe_metadata({"page_count": len(pages)})) as trace_span:

        # ── Extraction ──
        t0 = time.monotonic()
        with _span(lf, name="extractor",
                   metadata=safe_metadata({
                       "model": os.getenv("EXTRACTOR_MODEL", "?"),
                       "page_count": len(pages),
                   }),
                   input=safe_input({"pages": f"{len(pages)} page(s)"})) as ext_span:
            record = extract_record(pages)
            dt = time.monotonic() - t0
            ext_span.update(
                metadata=safe_metadata({
                    "duration_s": round(dt, 2),
                    "steps_extracted": len(record.ceremony.liturgySteps),
                    "missing_fields": len(record.extraction.missingFields),
                    "needs_human_review": len(record.extraction.needsHumanReview),
                }),
                output=safe_output({"steps": len(record.ceremony.liturgySteps)}),
            )

        # ── Checker ──
        t0 = time.monotonic()
        with _span(lf, name="checker",
                   metadata=safe_metadata({
                       "model": os.getenv("WRITER_MODEL", "?"),
                   })) as chk_span:
            record = check_record(record)
            dt = time.monotonic() - t0
            chk_span.update(
                metadata=safe_metadata({
                    "duration_s": round(dt, 2),
                    "qc_status": record.qualityCheck.status,
                    "alert_count": len(record.qualityCheck.alerts),
                    "question_count": len(record.qualityCheck.suggestedQuestions),
                }),
                output=safe_output({"status": record.qualityCheck.status}),
            )

        assert record.status == CeremonyStatus.needs_review, "Record did not transition to needs_review"

        trace_span.update(
            metadata=safe_metadata({
                "case_id": record.caseId,
                "qc_status": record.qualityCheck.status,
                "record_status": str(record.status),
            }),
        )

    lf.flush()
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

    lf = get_client()

    with _span(lf, name="orchestrator.run_after_validation",
               metadata=safe_metadata({"case_id": record.caseId})) as trace_span:

        # ── Writer ──
        t0 = time.monotonic()
        with _span(lf, name="writer",
                   metadata=safe_metadata({
                       "model": os.getenv("WRITER_MODEL", "?"),
                   })) as wr_span:
            record = write_record(record)
            dt = time.monotonic() - t0
            wr_span.update(
                metadata=safe_metadata({
                    "duration_s": round(dt, 2),
                    "intentions_count": len(record.ceremony.universalPrayerIntentions or []),
                    "has_mot_accueil": bool(record.ceremony.motDAccueil),
                }),
            )

        # ── Word déroulé ──
        t0 = time.monotonic()
        with _span(lf, name="word_deroule") as doc_span:
            record = build_deroule(record)
            dt = time.monotonic() - t0
            doc_span.update(
                metadata=safe_metadata({
                    "duration_s": round(dt, 2),
                    "has_document": bool(record.communication.documentLink),
                }),
            )

        # ── Google Doc upload (non-fatal) ──
        t0 = time.monotonic()
        with _span(lf, name="gdoc_upload") as gdoc_span:
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
            dt = time.monotonic() - t0
            gdoc_span.update(
                metadata=safe_metadata({
                    "duration_s": round(dt, 2),
                    "has_gdoc": bool(record.communication.gdocLink),
                }),
            )

        # ── Gmail draft ──
        t0 = time.monotonic()
        with _span(lf, name="gmail_draft") as draft_span:
            draft_result = create_gmail_draft(record)
            draft_fallback = False
            draft_attachment = False
            if draft_result:
                print(f"-> GMAIL DRAFT CREATED: {draft_result}")
                draft_fallback = bool(draft_result.get('fallback_recipient'))
                draft_attachment = bool(draft_result.get('attachment'))

            record.communication.emailDraftCreated = True
            record.status = CeremonyStatus.email_draft_created
            dt = time.monotonic() - t0
            draft_span.update(
                metadata=safe_metadata({
                    "duration_s": round(dt, 2),
                    "fallback_recipient": draft_fallback,
                    "has_attachment": draft_attachment,
                }),
            )

        # ── Sheets row ──
        t0 = time.monotonic()
        with _span(lf, name="sheets_row") as sheet_span:
            append_result = append_ceremony_row(record)
            if append_result:
                print(f"-> SHEETS ROW APPENDED: {append_result}")
            dt = time.monotonic() - t0
            sheet_span.update(
                metadata=safe_metadata({
                    "duration_s": round(dt, 2),
                    "appended": bool(append_result),
                }),
            )

        # ── Trace-level summary ──
        trace_span.update(
            metadata=safe_metadata({
                "case_id": record.caseId,
                "record_status": str(record.status),
                "has_gdoc": bool(record.communication.gdocLink),
                "has_draft": record.communication.emailDraftCreated,
                "draft_fallback": draft_fallback,
            }),
        )

    # Attach non-model metadata for UI consumption
    record.__dict__['_draft_fallback'] = draft_fallback
    record.__dict__['_draft_attachment'] = draft_attachment

    lf.flush()
    return record
