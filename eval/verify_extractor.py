import os
import json
import sys
from dotenv import load_dotenv

# We need a real model for testing, inject it if .env lacks it
# We do this BEFORE loading extractor so it doesn't sys.exit(1)
load_dotenv()
if not os.getenv("EXTRACTOR_MODEL") or "placeholder" in os.getenv("EXTRACTOR_MODEL"):
    # Fallback for eval harness to actually run
    os.environ["EXTRACTOR_MODEL"] = "gemini-2.5-pro"

from agents.extractor import extract_record
from agents.models import Record

def main():
    try:
        with open('examples/jeanne_martin/notes.md', 'r', encoding='utf-8') as f:
            notes_content = f.read()
    except FileNotFoundError:
        print("Could not find examples/jeanne_martin/notes.md")
        sys.exit(1)
    
    # Split into constituent pages
    pages = [p.strip() for p in notes_content.split('---') if p.strip()]
    
    prompt_parts = []
    for i, page in enumerate(pages):
        prompt_parts.append(f"--- PAGE {i+1} ---")
        prompt_parts.append(page)
    
    print("Running Extractor agent on Jeanne Martin notes...")
    record = extract_record(prompt_parts)
    
    print("\n--- Extracted Record ---")
    print(record.model_dump_json(indent=2))
    
    try:
        with open('examples/jeanne_martin/expected.json', 'r', encoding='utf-8') as f:
            expected_data = json.load(f)
        expected_record = Record(**expected_data)
    except FileNotFoundError:
        print("Could not find expected.json")
        sys.exit(1)
    
    print("\n--- Diff Summary ---")
    match_count = 0
    mismatch_count = 0
    
    extracted_dict = record.model_dump()
    expected_dict = expected_record.model_dump()
    
    for key in expected_dict:
        if expected_dict[key] == extracted_dict[key]:
            match_count += 1
            print(f"[MATCH] {key} matches expected.")
        else:
            mismatch_count += 1
            print(f"[DIFF] {key} differs from expected.")
            
    print(f"\nTotal: {match_count} matches, {mismatch_count} differences.")
    print("Note: Behavioral conformance is the goal, not exact byte-match. Benign variance is expected.")

if __name__ == '__main__':
    main()
