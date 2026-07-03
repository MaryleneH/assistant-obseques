import os
import sys
from dotenv import load_dotenv

# Load environment variables and override ALLOWED_EMAILS explicitly
load_dotenv()
os.environ["ALLOWED_EMAILS"] = "pere.bernard@example.com,equipe.obseques@example.com"

from agents.orchestrator import run_until_review, run_after_validation
from agents.models import CeremonyStatus

def main():
    print("=== Verification: Full Orchestrator Pipeline ===")
    
    notes_path = os.path.join("examples", "jeanne_martin", "notes.md")
    with open(notes_path, "r", encoding="utf-8") as f:
        notes_content = f.read()
        
    print("\n1. Running Phase 1 (Extractor -> Checker)...")
    record = run_until_review([notes_content])
    
    assert record.qualityCheck.status == "WARNING", f"Expected Checker WARNING, got {record.qualityCheck.status}"
    
    print(f"-> Phase 1 passed. Suggested Questions count: {len(record.qualityCheck.suggestedQuestions)}")
    
    print("\n2. Simulating Human Validation Gate...")
    record.security.humanValidated = True
    record.status = CeremonyStatus.ready_for_generation
    
    print("\n3. Running Phase 2 (Writer -> Word Déroulé)...")
    try:
        record = run_after_validation(record)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Phase 2 failed: {e}")
        sys.exit(1)
        
    print("\n--- Phase 2 Assertions ---")
    
    is_doc_created = record.status == CeremonyStatus.email_draft_created
    print(f"Assertion status == 'email_draft_created': {'PASS' if is_doc_created else 'FAIL'}")
    
    docx_path = record.communication.documentLink
    doc_exists = docx_path and os.path.exists(docx_path)
    doc_non_empty = doc_exists and os.path.getsize(docx_path) > 0
    print(f"Assertion Node output docx exists and is non-empty: {'PASS' if doc_non_empty else 'FAIL'}")
    if doc_exists:
        print(f"-> Generated file: {docx_path}")
    
    full_text = (
        (record.ceremony.motDAccueil or "") + " " +
        " ".join(record.ceremony.universalPrayerIntentions) + " " +
        (record.communication.emailSubject or "") + " " +
        (record.communication.emailBody or "")
    ).lower()
    has_maladie = "maladie" in full_text
    print(f"Assertion 'maladie' NOT present in Writer output: {'FAIL' if has_maladie else 'PASS'}")

if __name__ == "__main__":
    main()
