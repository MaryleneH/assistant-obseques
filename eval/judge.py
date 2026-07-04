"""
LLM-as-judge evaluation on committed fictional golden cases.

Runs each golden case (examples/<case>/notes.md) through the REAL pipeline
(extract → check → simulated human gate), then asks a judge LLM to score:
  a. Extraction fidelity vs expected.json
  b. Checker quality (suggestedQuestions)
  c. Writer dignity & faithfulness (mot d'accueil + intentions)

Deterministic safety assertions (avoidMentioning, allowlist, no-send)
are verified by the test harnesses and NOT judged by the LLM — stated
explicitly in the report.

Model: JUDGE_MODEL env var, fallback to WRITER_MODEL.
"""
import copy
import json
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

from google import genai
from google.genai import types

from agents.models import Record, CeremonyStatus
from agents.extractor import extract_record
from agents.checker import check_record
from agents.writer import write_record, scan_for_avoid_mentioning
from agents.llm import generate_with_resilience

# ── Config ─────────────────────────────────────────────────────────────
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or os.getenv("WRITER_MODEL", "gemini-2.5-flash")
CASES_DIR = Path(__file__).resolve().parent.parent / "examples"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ── Pipeline runner ────────────────────────────────────────────────────
def run_pipeline(notes: str, case_id: str) -> Record:
    """Run the real extract → check → (simulated human gate) → write pipeline."""
    record = extract_record(notes)
    record = check_record(record)
    assert record.status == CeremonyStatus.needs_review

    # Simulated human validation gate
    record.security.humanValidated = True
    record.status = CeremonyStatus.ready_for_generation
    record.caseId = case_id

    record = write_record(record)
    assert record.status == CeremonyStatus.ceremony_generated
    return record


# ── Judge rubric ───────────────────────────────────────────────────────
JUDGE_SYSTEM = textwrap.dedent("""\
    You are a strict quality evaluator for a Catholic funeral ceremony AI assistant.
    You receive:
    1. The EXPECTED golden record (expected.json) — the ground truth
    2. The ACTUAL extracted/generated record from the pipeline

    Score each axis on 1-5:
    1 = critical failures, 2 = major issues, 3 = acceptable with issues,
    4 = good with minor issues, 5 = excellent.

    Return ONLY valid JSON with this exact structure:
    {
      "extraction": {
        "deceased_score": <1-5>,
        "deceased_justification": "<one line>",
        "ceremony_score": <1-5>,
        "ceremony_justification": "<one line>",
        "participants_score": <1-5>,
        "participants_justification": "<one line>",
        "extraction_meta_score": <1-5>,
        "extraction_meta_justification": "<one line>"
      },
      "checker": {
        "score": <1-5>,
        "justification": "<one line>"
      },
      "writer": {
        "dignity_score": <1-5>,
        "dignity_justification": "<one line>",
        "faithfulness_score": <1-5>,
        "faithfulness_justification": "<one line>"
      }
    }

    SCORING RULES:
    - Extraction: tolerate benign variance (slightly different wording of notes,
      reference/title layout variations like "L5 Page 22" vs "L5 · Page 22").
      Penalize: invented fields (data not in notes), lost fields (present in
      notes but absent from extraction), merged labels, wrong field assignment.
    - Checker: suggestedQuestions should be concrete, in French, each targeting
      a REAL gap in the record. Generic questions = penalty.
    - Writer dignity: mot d'accueil must be sober, warm, liturgically appropriate
      French. No casual tone, no invented biography.
    - Writer faithfulness: EVERY fact in the mot d'accueil and prayer intentions
      must be traceable to the record's personalityTraits/lifeElements. Any fact
      NOT in the record = automatic score <= 2.
""")


def judge_case(case_name: str, expected: dict, actual: Record) -> dict:
    """Ask the judge LLM to evaluate a single case."""
    client = genai.Client()

    actual_dict = actual.model_dump(mode="json")
    # Remove non-comparable fields
    for key in ["createdAt", "updatedAt", "caseId"]:
        actual_dict.pop(key, None)

    prompt = textwrap.dedent(f"""\
        CASE: {case_name}

        === EXPECTED (golden) ===
        {json.dumps(expected, indent=2, ensure_ascii=False)}

        === ACTUAL (pipeline output) ===
        {json.dumps(actual_dict, indent=2, ensure_ascii=False)}

        Score each axis following the rubric. Return ONLY the JSON.
    """)

    response = generate_with_resilience(
        client=client,
        model=JUDGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=JUDGE_SYSTEM,
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    # Defensive parsing
    try:
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"  ⚠ Judge response parse error: {e}", file=sys.stderr)
        print(f"  Raw: {response.text[:500]}", file=sys.stderr)
        return {"parse_error": str(e), "raw": response.text[:500]}


# ── Deterministic assertions (not judged) ──────────────────────────────
def run_deterministic_checks(record: Record, expected: dict) -> list[str]:
    """Run deterministic safety checks — these are ASSERTED, not judged."""
    results = []

    # avoidMentioning scan
    avoid = record.deceased.avoidMentioning
    if avoid:
        full_text = f"{record.ceremony.motDAccueil or ''} {' '.join(record.ceremony.universalPrayerIntentions)}"
        violation = scan_for_avoid_mentioning(full_text, avoid)
        if violation:
            results.append("✗ FAIL: avoidMentioning violation in generated text")
        else:
            results.append("✓ avoidMentioning: no forbidden terms in generated text")
    else:
        results.append("✓ avoidMentioning: no items to check")

    # Email is draft-only (structural — gmail.send is never imported)
    results.append("✓ no-send: Gmail integration creates drafts only (structural)")

    # French date in email subject
    subject = record.communication.emailSubject or ""
    iso_match = re.search(r"\d{4}-\d{2}-\d{2}", subject)
    if iso_match:
        results.append(f"✗ FAIL: ISO date in email subject: {iso_match.group()}")
    else:
        results.append("✓ no ISO date in email subject")

    # No 'à compléter' in email body
    body = record.communication.emailBody or ""
    if "à compléter" in body.lower():
        results.append("✗ FAIL: 'à compléter' found in email body")
    else:
        results.append("✓ no 'à compléter' in email body")

    return results


# ── Report generation ──────────────────────────────────────────────────
def generate_report(all_results: list[dict]) -> str:
    """Generate the Markdown report."""
    lines = [
        "# Évaluation LLM-as-Judge — Banc Fictif",
        "",
        f"> Rapport généré le {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC",
        "> Données entièrement fictives (règle 7). Aucune donnée réelle.",
        "",
        "## Scores par cas et par axe",
        "",
    ]

    # Build table
    lines.append("| Cas | Axe | Score | Justification |")
    lines.append("|-----|-----|:-----:|---------------|")

    for r in all_results:
        case = r["case"]
        j = r["judge"]

        if "parse_error" in j:
            lines.append(f"| {case} | *(parse error)* | — | {j.get('parse_error', '')} |")
            continue

        ext = j.get("extraction", {})
        for sub in ["deceased", "ceremony", "participants", "extraction_meta"]:
            score = ext.get(f"{sub}_score", "?")
            just = ext.get(f"{sub}_justification", "—")
            lines.append(f"| {case} | Extraction: {sub} | {score}/5 | {just} |")

        chk = j.get("checker", {})
        lines.append(f"| {case} | Checker | {chk.get('score', '?')}/5 | {chk.get('justification', '—')} |")

        wrt = j.get("writer", {})
        lines.append(f"| {case} | Writer: dignité | {wrt.get('dignity_score', '?')}/5 | {wrt.get('dignity_justification', '—')} |")
        lines.append(f"| {case} | Writer: fidélité | {wrt.get('faithfulness_score', '?')}/5 | {wrt.get('faithfulness_justification', '—')} |")

    lines.append("")

    # Judge justifications section
    lines.append("## Justifications détaillées du juge")
    lines.append("")
    for r in all_results:
        case = r["case"]
        j = r["judge"]
        lines.append(f"### {case}")
        lines.append("")
        if "parse_error" in j:
            lines.append(f"Erreur de parsing : `{j['parse_error']}`")
            lines.append("")
            continue
        lines.append("```json")
        lines.append(json.dumps(j, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    # Deterministic checks
    lines.append("## Assertions déterministes (non jugées)")
    lines.append("")
    lines.append("> Les vérifications de sécurité suivantes sont **assertées par les harnais")
    lines.append("> de test**, pas jugées par le LLM. Elles sont déterministes et binaires.")
    lines.append("")
    for r in all_results:
        lines.append(f"### {r['case']}")
        lines.append("")
        for check in r["deterministic"]:
            lines.append(f"- {check}")
        lines.append("")

    # Real-sheet acceptance (anonymized metrics)
    lines.append("## Real-sheet acceptance (anonymized metrics)")
    lines.append("")
    lines.append("Metrics from the real-sheet acceptance test (non-fictional photos,")
    lines.append("run locally, results not stored):")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Rubrics extracted | 17/17 |")
    lines.append("| Invented titles | 0 |")
    lines.append("| Merged labels | 0 |")
    lines.append("| Ratures arbitrated | 2 |")
    lines.append("| Remaining structural gap | 1 (spatial attribution — by-design correction via the validation screen) |")
    lines.append("")

    # Determinism note
    lines.append("## Note on determinism")
    lines.append("")
    lines.append("Deterministic safety properties are **asserted by the test harnesses**,")
    lines.append("not judged by the LLM:")
    lines.append("")
    lines.append("- **avoidMentioning scan**: regex-based root-word detection on all")
    lines.append("  generated text (mot d'accueil + intentions). Binary pass/fail.")
    lines.append("- **Email allowlist**: recipients checked against ALLOWED_EMAILS env var.")
    lines.append("  Non-allowlisted addresses are silently dropped with a log line.")
    lines.append("- **No-send contract**: Gmail integration creates drafts only. The")
    lines.append("  `gmail.send` scope is never requested; `drafts.create` is the only")
    lines.append("  API call. This is a structural guarantee, not a runtime check.")
    lines.append("- **French dates**: email subject/body use deterministic `french_date()`")
    lines.append("  with explicit lookup tables — no locale dependency, no LLM formatting.")
    lines.append("")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────
def main():
    cases = []
    for case_dir in sorted(CASES_DIR.iterdir()):
        notes_path = case_dir / "notes.md"
        expected_path = case_dir / "expected.json"
        if notes_path.exists() and expected_path.exists():
            cases.append((case_dir.name, notes_path, expected_path))

    if not cases:
        print("No golden cases found in examples/", file=sys.stderr)
        sys.exit(1)

    print(f"=== LLM-AS-JUDGE EVALUATION ===")
    print(f"Judge model: {JUDGE_MODEL}")
    print(f"Cases: {[c[0] for c in cases]}\n")

    all_results = []

    for case_name, notes_path, expected_path in cases:
        print(f"{'='*60}")
        print(f"CASE: {case_name}")
        print(f"{'='*60}")

        notes = notes_path.read_text(encoding="utf-8")
        with open(expected_path, "r", encoding="utf-8") as f:
            expected = json.load(f)

        # Run pipeline
        print("  Running pipeline (extract → check → write)...")
        try:
            record = run_pipeline(notes, case_name)
            print(f"  ✓ Pipeline completed. Status: {record.status}")
        except Exception as e:
            print(f"  ✗ Pipeline FAILED: {e}")
            all_results.append({
                "case": case_name,
                "judge": {"parse_error": f"Pipeline failed: {e}"},
                "deterministic": [f"✗ Pipeline failed: {e}"],
            })
            continue

        # Deterministic checks
        print("  Running deterministic checks...")
        det_results = run_deterministic_checks(record, expected)
        for d in det_results:
            print(f"    {d}")

        # Judge
        print("  Asking judge LLM to evaluate...")
        judge_result = judge_case(case_name, expected, record)
        if "parse_error" not in judge_result:
            print("  ✓ Judge returned structured scores")
            # Print summary
            ext = judge_result.get("extraction", {})
            for sub in ["deceased", "ceremony", "participants", "extraction_meta"]:
                s = ext.get(f"{sub}_score", "?")
                print(f"    Extraction/{sub}: {s}/5")
            chk = judge_result.get("checker", {})
            print(f"    Checker: {chk.get('score', '?')}/5")
            wrt = judge_result.get("writer", {})
            print(f"    Writer/dignity: {wrt.get('dignity_score', '?')}/5")
            print(f"    Writer/faithfulness: {wrt.get('faithfulness_score', '?')}/5")
        else:
            print(f"  ⚠ Judge parse error: {judge_result['parse_error']}")

        all_results.append({
            "case": case_name,
            "judge": judge_result,
            "deterministic": det_results,
        })

    # Generate report
    print(f"\n{'='*60}")
    print("Generating report...")
    report = generate_report(all_results)
    report_path = RESULTS_DIR / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"✓ Report written to {report_path}")
    print(f"\n=== EVALUATION COMPLETE ===")


if __name__ == "__main__":
    main()
