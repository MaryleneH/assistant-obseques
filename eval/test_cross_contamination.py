"""
Cross-contamination regression test for the Writer agent.
Runs TWO fictional cases through the full pipeline and asserts that:
  - Jeanne Martin's output references "Martin" (golden case works)
  - Marcel Dupont's output references "Dupont" and contains NONE of the
    golden-case proper nouns (Jeanne, Martin, Claire, Pierre)
This proves prompts are case-agnostic and facts come from the record only.
"""
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

# Load .env, then widen the allowlist to include test emails
load_dotenv()
existing = os.environ.get("ALLOWED_EMAILS", "")
os.environ["ALLOWED_EMAILS"] = existing + ",abbe.moreau@example.com"

from agents.orchestrator import run_until_review, run_after_validation
from agents.models import CeremonyStatus

GOLDEN_CASE_NOTES = open("examples/jeanne_martin/notes.md", "r", encoding="utf-8").read()

DUPONT_NOTES = """
## Page 1

Obsèques de Monsieur Marcel Dupont, 72 ans, jeudi 10 juillet à 14h00
à l'église Notre-Dame-de-la-Paix.

La famille décrit Marcel comme un homme jovial, passionné de jardinage,
qui aimait recevoir ses amis autour d'un bon repas. Ancien instituteur,
il était très apprécié dans le quartier.

Ne pas mentionner le divorce.

## Page 2

Sa fille Sophie lira la première lecture.
Son petit-fils Antoine aimerait lire une intention de prière.

Chant d'entrée souhaité : « Amazing Grace ».
Chant du dernier adieu : « Ave Maria ».

Le prêtre sera l'Abbé Moreau.
Envoyer le déroulé à abbe.moreau@example.com et à equipe.obseques@example.com.
"""

FORBIDDEN_IN_DUPONT = {"jeanne", "martin", "claire", "pierre", "bernard", "saint-martin"}


def run_case(name: str, notes: str) -> dict:
    """Run a case through Phase 1 + Phase 2 and return writer outputs."""
    print(f"\n{'='*60}")
    print(f"  CASE: {name}")
    print(f"{'='*60}")

    record = run_until_review([notes])
    print(f"  Phase 1 → qualityCheck.status = {record.qualityCheck.status}")

    # Simulate human validation
    record.security.humanValidated = True
    record.status = CeremonyStatus.ready_for_generation

    record = run_after_validation(record)
    print(f"  Phase 2 → status = {record.status}")

    subject = record.communication.emailSubject or ""
    body = record.communication.emailBody or ""
    mot = record.ceremony.motDAccueil or ""
    intentions = " ".join(record.ceremony.universalPrayerIntentions or [])

    return {
        "subject": subject,
        "body": body,
        "mot": mot,
        "intentions": intentions,
        "full_text": f"{subject} {body} {mot} {intentions}",
    }


def main():
    print("=== CROSS-CONTAMINATION REGRESSION TEST ===\n")

    # ── Run both cases ──
    jeanne = run_case("Jeanne Martin (golden)", GOLDEN_CASE_NOTES)
    dupont = run_case("Marcel Dupont (fictional)", DUPONT_NOTES)

    # ── Print subjects side by side ──
    print(f"\n{'='*60}")
    print(f"  SUBJECTS SIDE BY SIDE")
    print(f"{'='*60}")
    print(f"  Jeanne Martin : {jeanne['subject']}")
    print(f"  Marcel Dupont : {dupont['subject']}")

    # ── Assertions: Jeanne Martin ──
    print(f"\n--- Jeanne Martin assertions ---")
    assert "martin" in jeanne["subject"].lower(), \
        f"FAIL: 'Martin' not in Jeanne's subject: {jeanne['subject']}"
    print("  ✓ Subject contains 'Martin'")

    # ── Assertions: Marcel Dupont ──
    print(f"\n--- Marcel Dupont assertions ---")
    assert "dupont" in dupont["subject"].lower(), \
        f"FAIL: 'Dupont' not in Dupont's subject: {dupont['subject']}"
    print("  ✓ Subject contains 'Dupont'")

    dupont_lower = dupont["full_text"].lower()
    for forbidden in FORBIDDEN_IN_DUPONT:
        if forbidden in dupont_lower:
            # Find the contaminated line for diagnosis
            for field_name, field_val in [("subject", dupont["subject"]),
                                          ("body", dupont["body"]),
                                          ("mot", dupont["mot"]),
                                          ("intentions", dupont["intentions"])]:
                if forbidden in field_val.lower():
                    print(f"  ✗ CONTAMINATION: '{forbidden}' found in {field_name}!")
                    print(f"    Excerpt: ...{field_val[max(0, field_val.lower().index(forbidden)-40):field_val.lower().index(forbidden)+40]}...")
            sys.exit(1)
    print("  ✓ No golden-case contamination in Dupont's output")

    # ── Verify Jeanne case doesn't contain Dupont data either ──
    print(f"\n--- Reverse contamination check ---")
    jeanne_lower = jeanne["full_text"].lower()
    for forbidden in {"dupont", "marcel", "sophie", "antoine", "moreau"}:
        if forbidden in jeanne_lower:
            print(f"  ✗ REVERSE CONTAMINATION: '{forbidden}' found in Jeanne's output!")
            sys.exit(1)
    print("  ✓ No Dupont contamination in Jeanne's output")

    print(f"\n=== ALL CROSS-CONTAMINATION TESTS PASSED ===")


if __name__ == "__main__":
    main()
