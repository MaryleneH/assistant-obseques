import os
import sys
import copy
from dotenv import load_dotenv

# Load environment variables but override ALLOWED_EMAILS explicitly
load_dotenv()
os.environ["ALLOWED_EMAILS"] = "pere.bernard@example.com,equipe.obseques@example.com"

from agents.extractor import extract_record
from agents.checker import check_record
from agents.models import Record

def main():
    print("=== Verification: Extractor + Checker Pipeline ===")
    
    notes_path = os.path.join("examples", "jeanne_martin", "notes.md")
    with open(notes_path, "r", encoding="utf-8") as f:
        notes_content = f.read()
        
    print("\n1. Running Extractor...")
    record = extract_record(notes_content)
    
    print("\n2. Running Checker (Golden Path)...")
    golden_record = copy.deepcopy(record)
    golden_record = check_record(golden_record)
    
    print("\n--- Golden Path Result ---")
    print(f"Record Status: {golden_record.status}")
    print(f"QualityCheck Status: {golden_record.qualityCheck.status}")
    print("Alerts:")
    for a in golden_record.qualityCheck.alerts:
        print(f"  - {a}")
    print("Suggested Questions:")
    for q in golden_record.qualityCheck.suggestedQuestions:
        print(f"  - {q}")
    print("Recommended Actions:")
    for r in golden_record.qualityCheck.recommendedActions:
        print(f"  - {r}")
        
    print("\n3. Running Checker (Negative Path: Unauthorized Email)...")
    negative_record = copy.deepcopy(record)
    negative_record.communication.teamEmails.append("outsider@example.com")
    negative_record = check_record(negative_record)
    
    print("\n--- Negative Path Result ---")
    print(f"Record Status: {negative_record.status}")
    print(f"QualityCheck Status: {negative_record.qualityCheck.status}")
    print("Alerts:")
    for a in negative_record.qualityCheck.alerts:
        print(f"  - {a}")

if __name__ == "__main__":
    main()
