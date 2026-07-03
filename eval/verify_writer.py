import os
import sys
import copy
from dotenv import load_dotenv

# Load environment variables and override ALLOWED_EMAILS explicitly
load_dotenv()
os.environ["ALLOWED_EMAILS"] = "pere.bernard@example.com,equipe.obseques@example.com"

from agents.extractor import extract_record
from agents.checker import check_record
from agents.writer import write_record
from agents.models import Record, CeremonyStatus

def main():
    print("=== Verification: Extractor + Checker + Writer Pipeline ===")
    
    notes_path = os.path.join("examples", "jeanne_martin", "notes.md")
    with open(notes_path, "r", encoding="utf-8") as f:
        notes_content = f.read()
        
    print("\n1. Running Extractor...")
    record = extract_record(notes_content)
    
    print("\n2. Running Checker...")
    record = check_record(record)
    
    print("\n3. Simulating Human Validation Gate...")
    record.security.humanValidated = True
    record.status = CeremonyStatus.ready_for_generation
    
    print("\n4. Running Writer...")
    try:
        record = write_record(record)
    except Exception as e:
        print(f"Writer failed: {e}")
        sys.exit(1)
        
    print("\n--- Generated Content ---")
    print("\n[Mot d'accueil]")
    print(record.ceremony.motDAccueil)
    
    print("\n[Intentions de Prière Universelle]")
    for i, intention in enumerate(record.ceremony.universalPrayerIntentions, 1):
        print(f"{i}. {intention}")
        
    print("\n[Email Subject]")
    print(record.communication.emailSubject)
    
    print("\n[Email Body]")
    print(record.communication.emailBody)
    
    print("\n--- Deterministic Assertions ---")
    
    # a) The string "maladie" appears in NO generated text
    full_text = (
        (record.ceremony.motDAccueil or "") + " " +
        " ".join(record.ceremony.universalPrayerIntentions) + " " +
        (record.communication.emailSubject or "") + " " +
        (record.communication.emailBody or "")
    ).lower()
    
    has_maladie = "maladie" in full_text
    print(f"Assertion 'maladie' NOT present: {'FAIL' if has_maladie else 'PASS'}")
    
    # b) "à compléter" appears for the missing gospel/psalm in the email
    email_text = (record.communication.emailBody or "").lower()
    has_a_completer = "à compléter" in email_text or "a completer" in email_text
    print(f"Assertion 'à compléter' present for missing fields: {'PASS' if has_a_completer else 'FAIL'}")
    
    # c) status is "ceremony_generated"
    is_generated_status = record.status == CeremonyStatus.ceremony_generated
    print(f"Assertion status == 'ceremony_generated': {'PASS' if is_generated_status else 'FAIL'}")
    
    print("\n--- Safety-Net Negative Test ---")
    print("Forcing 'ses petits-enfants' into avoidMentioning and running Writer...")
    # Reset status so Writer accepts it
    record.status = CeremonyStatus.ready_for_generation
    record.deceased.avoidMentioning = ["ses petits-enfants"]
    try:
        record = write_record(record)
        
        full_text_neg = (
            (record.ceremony.motDAccueil or "") + " " +
            " ".join(record.ceremony.universalPrayerIntentions) + " " +
            (record.communication.emailSubject or "") + " " +
            (record.communication.emailBody or "")
        ).lower()
        
        has_petits_enfants = "petits-enfants" in full_text_neg
        if not has_petits_enfants:
            print("Outcome: PASS (Safety retry successfully removed 'petits-enfants')")
        else:
            print("Outcome: FAIL ('petits-enfants' still present!)")
            
    except ValueError as e:
        if "avoidMentioning" in str(e):
            print("Outcome: PASS (Writer raised explicit safety exception)")
        else:
            print(f"Outcome: FAIL (Unexpected exception: {e})")

if __name__ == "__main__":
    main()
