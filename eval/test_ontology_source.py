"""
Source-of-truth test: asserts that CANONICAL_LABELS matches the labels in
skills/deroule-obseques/references/exemple_deroule.json (plus the documented
"2ème Lecture" insertion).

If this test fails, someone changed the reference or the constant without
keeping them in sync.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from agents.liturgy import CANONICAL_LABELS, norm_label


def test_canonical_matches_reference():
    ref_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "skills", "deroule-obseques", "references", "exemple_deroule.json",
    )
    with open(ref_path, "r", encoding="utf-8") as f:
        ref = json.load(f)

    ref_labels = [step["label"] for step in ref["etapes"]]
    assert len(ref_labels) == 17, f"Reference has {len(ref_labels)} labels, expected 17"

    # CANONICAL_LABELS = reference 17 labels + "2ème Lecture" inserted after
    # "1ère Lecture" (documented in liturgy.py).
    expected = list(ref_labels)
    # Find "1ère Lecture" index and insert "2ème Lecture" after it
    idx_1ere = next(i for i, l in enumerate(expected) if norm_label(l) == norm_label("1ère Lecture"))
    expected.insert(idx_1ere + 1, "2ème Lecture")

    assert len(CANONICAL_LABELS) == len(expected), (
        f"CANONICAL_LABELS has {len(CANONICAL_LABELS)} entries, expected {len(expected)}"
    )

    for i, (got, want) in enumerate(zip(CANONICAL_LABELS, expected)):
        assert norm_label(got) == norm_label(want), (
            f"Position {i}: CANONICAL_LABELS has '{got}', reference expects '{want}'"
        )

    print("✓ CANONICAL_LABELS matches reference + documented 2ème Lecture insertion")


def test_norm_label():
    """Sanity check for the normalizer."""
    assert norm_label("Chant d\u2019entrée") == norm_label("Chant d'entrée")
    assert norm_label("  1ère   Lecture  ") == norm_label("1ère Lecture")
    assert norm_label("PRIÈRE UNIVERSELLE") == norm_label("Prière Universelle")
    assert norm_label("Entrée") != norm_label("Chant d'entrée")  # distinct rubrics
    print("✓ norm_label works correctly")


if __name__ == "__main__":
    test_norm_label()
    test_canonical_matches_reference()
    print("\n=== ALL SOURCE-OF-TRUTH TESTS PASSED ===")
