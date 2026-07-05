"""
Unified test runner — executes every eval suite and reports a PASS/FAIL table.

Usage:
    python eval/run_all.py

Exit code 0 = all suites passed; 1 = at least one failure.
"""
import os
import sys
import subprocess
import time

sys.stdout.reconfigure(encoding="utf-8")

# Each entry: (label, script path)
SUITES = [
    ("Auth gate",          "eval/test_auth.py"),
    ("Full ontology",      "eval/test_full_ontology.py"),
    ("Cross-contamination","eval/test_cross_contamination.py"),
    ("Fallback recipient", "eval/test_fallback_recipient.py"),
    ("Edit survival",      "eval/test_edit_survival.py"),
    ("Adversarial (injection)", "eval/test_injection.py"),
    ("Photo page ordering","eval/test_photo_order.py"),
    ("Mobile rendering",   "eval/test_mobile_rendering.py"),
]

# These are optional / heavy — only run if explicitly asked
OPTIONAL_SUITES = [
    ("LLM-as-judge",       "eval/judge.py"),
    ("UI journey (Playwright)", "eval/test_ui_journey.py"),
]


def run_suite(label: str, script: str) -> tuple[str, float, str]:
    """Run a test script, return (status, duration_s, snippet)."""
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max per suite
            encoding="utf-8",
            errors="replace",
        )
        elapsed = time.time() - start
        output = result.stdout + result.stderr

        if result.returncode == 0:
            return ("PASS", elapsed, "")
        else:
            # Grab last 3 lines for the snippet
            lines = output.strip().splitlines()
            snippet = "\n".join(lines[-3:]) if lines else "(no output)"
            return ("FAIL", elapsed, snippet)

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return ("TIMEOUT", elapsed, "Exceeded 300s")
    except Exception as e:
        elapsed = time.time() - start
        return ("ERROR", elapsed, str(e))


def main():
    include_optional = "--all" in sys.argv

    suites = list(SUITES)
    if include_optional:
        suites.extend(OPTIONAL_SUITES)

    print("=" * 70)
    print("  ASSISTANT OBSÈQUES — EVALUATION RUNNER")
    print("=" * 70)
    print(f"\n  Suites: {len(suites)}  |  --all: {'yes' if include_optional else 'no (add --all for optional suites)'}\n")

    results = []
    all_pass = True

    for label, script in suites:
        print(f"  ▶ {label} ({script})...", end="", flush=True)
        status, elapsed, snippet = run_suite(label, script)
        results.append((label, status, elapsed))

        if status == "PASS":
            print(f"  ✓ {elapsed:.1f}s")
        else:
            all_pass = False
            print(f"  ✗ {status} ({elapsed:.1f}s)")
            if snippet:
                for line in snippet.splitlines():
                    print(f"      {line}")

    # Final table
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"\n  {'Suite':<30} {'Status':<10} {'Time':>8}")
    print(f"  {'─' * 30} {'─' * 10} {'─' * 8}")
    for label, status, elapsed in results:
        icon = "✓" if status == "PASS" else "✗"
        print(f"  {icon} {label:<28} {status:<10} {elapsed:>7.1f}s")

    print(f"\n  {'─' * 50}")
    total = sum(e for _, _, e in results)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = len(results) - passed
    verdict = "ALL PASSED" if all_pass else f"{failed} FAILED"
    print(f"  {passed}/{len(results)} passed | {total:.1f}s total | {verdict}")
    print()

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
