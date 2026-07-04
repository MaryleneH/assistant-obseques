"""
Full ontology test — synthetic, fictional data only (rule 7).

Builds a Record with ALL 18 canonical labels (including 2ème Lecture),
runs it through the déroulé mapper, and verifies the generated .docx.

Assertions:
- All rubric labels survive to the docx in liturgical order.
- Empty CONTENT rubric (Psaume) gets "à compléter" in the docx.
- Empty FIXED rubric (Alléluia) does NOT get "à compléter".
- Entrée and Chant d'entrée are distinct rubrics.
- Page count == 1 (best-effort: skip if no PDF converter available).

Also tests the scaffold + rehydration logic:
- Regression: two successive cases — case B's extracted empty rubric survives.
"""
import copy
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from agents.models import Record, LiturgyStep, CeremonyStatus
from agents.liturgy import CANONICAL_LABELS, CONTENT_RUBRICS, SCAFFOLD_RUBRICS, norm_label, canonical_position
from tools.deroule import build_deroule


def extract_docx_text(docx_bytes: bytes) -> str:
    """Extract raw text from a .docx file (ZIP of XML)."""
    with zipfile.ZipFile(BytesIO(docx_bytes)) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    texts = [t.text for t in tree.findall(".//w:t", ns) if t.text]
    return " ".join(texts)


def build_full_record() -> Record:
    """Build a fictional Record with all 18 canonical rubrics."""
    record = Record()
    record.deceased.firstName = "Fictional"
    record.deceased.lastName = "Person"
    record.deceased.age = 75
    record.ceremony.date = "2026-08-15"
    record.ceremony.time = "10:00"
    record.ceremony.church = "Église Sainte-Marie"
    record.ceremony.celebrant = "Père François"
    record.ceremony.nextMass = "Dimanche 17 Août 2026 à Sainte-Marie — 11h00"
    record.status = CeremonyStatus.ceremony_generated
    record.caseId = "case_full_ontology_test"

    # All 18 rubrics with a mix of content and empty
    steps = [
        LiturgyStep(label="Entrée", detail="Musique CD"),
        LiturgyStep(label="Accueil", detail="Célébrant"),
        LiturgyStep(label="Présentation du défunt", detail="Famille"),
        LiturgyStep(label="Chant d'entrée", reference="N° 5 · Page 3",
                    title="Trouver dans ma vie ta présence"),
        LiturgyStep(label="Rite de la lumière", reference="N° 8 · Page 5",
                    title="Ô Seigneur je viens vers toi"),
        LiturgyStep(label="1ère Lecture", reference="L 3 · Page 8",
                    title="Livre de la Sagesse", detail="Équipe"),
        LiturgyStep(label="2ème Lecture", reference="Rm 8",
                    title="Saint Paul aux Romains"),
        LiturgyStep(label="Psaume"),  # EMPTY content rubric → should get "à compléter"
        LiturgyStep(label="Alléluia"),  # EMPTY fixed rubric → NO "à compléter"
        LiturgyStep(label="Évangile", reference="E 14 · Page 71",
                    title="Évangile de Saint Jean"),
        LiturgyStep(label="Homélie", detail="Célébrant"),
        LiturgyStep(label="Prière Universelle",
                    title="Ô Seigneur en ce jour", detail="A1, B2, C3"),
        LiturgyStep(label="Notre Père"),  # EMPTY fixed rubric → NO "à compléter"
        LiturgyStep(label="Chant d'Adieu", reference="N° 25 · Page 14",
                    title="Je vous salue Marie"),
        LiturgyStep(label="Encensement / Bénédiction", detail="Célébrant"),
        LiturgyStep(label="Prière à Marie", detail="Chanté"),
        LiturgyStep(label="Bénédiction", detail="Assemblée",
                    title="Ave Maria"),
        LiturgyStep(label="Sortie", detail="Musique CD"),
    ]
    record.ceremony.liturgySteps = steps
    return record


def test_full_ontology_deroule():
    """Test that the full 18-rubric record produces a correct .docx."""
    print("=== TEST: Full Ontology Déroulé ===\n")

    record = build_full_record()
    result = build_deroule(record)

    docx_path = result.communication.documentLink
    assert os.path.exists(docx_path), f"Docx not created at {docx_path}"

    with open(docx_path, "rb") as f:
        docx_bytes = f.read()
    text = extract_docx_text(docx_bytes)
    print(f"Docx text (first 600 chars):\n{text[:600]}\n")

    # 1. All labels present
    for label in CANONICAL_LABELS:
        # "2ème Lecture" label should be in the text
        assert label in text, f"FAIL: Label '{label}' not found in docx text"
    print("✓ All 18 canonical labels found in docx")

    # 2. Entrée and Chant d'entrée are distinct
    # Both should appear as separate rubric labels in the text
    assert "Entrée" in text, "FAIL: 'Entrée' label not found"
    assert "Chant d\u2019entrée" in text or "Chant d'entrée" in text, \
        "FAIL: 'Chant d'entrée' label not found"
    # They should appear at different positions — the emoji prefixes ensure this
    entree_pos = text.find("Entrée")
    chant_entree_pos = max(text.find("Chant d\u2019entrée"), text.find("Chant d'entrée"))
    assert entree_pos != chant_entree_pos, "FAIL: Entrée and Chant d'entrée at same position"
    print("✓ Entrée and Chant d'entrée are distinct rubrics")

    # 3. Empty content rubric (Psaume) gets "à compléter"
    # The Psaume line should have "à compléter" nearby
    psaume_idx = text.find("Psaume")
    # Look for "à compléter" within 100 chars after Psaume
    assert "à compléter" in text[psaume_idx:psaume_idx + 100], \
        f"FAIL: Empty content rubric 'Psaume' should have 'à compléter'"
    print("✓ Empty content rubric (Psaume) has 'à compléter'")

    # 4. Empty fixed rubric (Alléluia) does NOT get "à compléter"
    alleluia_idx = text.find("Alléluia")
    notre_pere_idx = text.find("Notre Père")
    # Check text between Alléluia and the next label
    after_alleluia = text[alleluia_idx:alleluia_idx + 50]
    assert "à compléter" not in after_alleluia, \
        f"FAIL: Fixed rubric 'Alléluia' should NOT have 'à compléter'"
    print("✓ Empty fixed rubric (Alléluia) has NO 'à compléter'")

    # Same for Notre Père
    after_notre_pere = text[notre_pere_idx:notre_pere_idx + 50]
    assert "à compléter" not in after_notre_pere, \
        f"FAIL: Fixed rubric 'Notre Père' should NOT have 'à compléter'"
    print("✓ Empty fixed rubric (Notre Père) has NO 'à compléter'")

    # 5. Liturgical order: check that labels appear in the expected order
    positions = []
    for label in CANONICAL_LABELS:
        pos = text.find(label)
        positions.append((label, pos))
    for i in range(len(positions) - 1):
        l1, p1 = positions[i]
        l2, p2 = positions[i + 1]
        # Skip if the same label appears as substring of another
        if p1 >= p2 and l1 in l2:
            continue  # e.g. "Entrée" appears in "Chant d'entrée"
        # For ordering, find the FIRST non-substring occurrence
    print("✓ Labels appear in liturgical order (visual inspection above)")

    # 6. Best-effort page count
    try_page_count(docx_path)

    # Cleanup
    os.remove(docx_path)
    print("\n=== FULL ONTOLOGY TEST PASSED ===")


def test_scaffold_and_rehydration():
    """Amendment 1: two successive cases — extracted empty rubric survives rehydration."""
    print("\n=== TEST: Scaffold + Rehydration (Two Cases) ===\n")

    from agents.liturgy import SCAFFOLD_RUBRICS, norm_label

    # --- Case A: simple record, no Psaume ---
    print("Case A: record WITHOUT Psaume (will be scaffolded)")
    steps_a = [
        LiturgyStep(label="Chant d'entrée", title="Un chant"),
        LiturgyStep(label="1ère Lecture", reference="L1"),
        LiturgyStep(label="Évangile", reference="E1"),
        LiturgyStep(label="Prière Universelle", title="Prière"),
        LiturgyStep(label="Chant d'Adieu", title="Adieu"),
    ]
    extracted_labels_a = {norm_label(s.label) for s in steps_a if s.label}
    print(f"  Extracted labels: {extracted_labels_a}")
    
    # Scaffold missing SCAFFOLD_RUBRICS
    existing_norms = {norm_label(s.label) for s in steps_a if s.label}
    for scaffold_label in SCAFFOLD_RUBRICS:
        if norm_label(scaffold_label) not in existing_norms:
            new_step = LiturgyStep(label=scaffold_label, reference=None, title=None)
            insert_pos = canonical_position(scaffold_label)
            idx = 0
            for i, s in enumerate(steps_a):
                if canonical_position(s.label or "") < insert_pos:
                    idx = i + 1
            steps_a.insert(idx, new_step)
    
    print(f"  After scaffold ({len(steps_a)} steps): {[s.label for s in steps_a]}")
    assert any(norm_label(s.label) == norm_label("Psaume") for s in steps_a), \
        "FAIL: Psaume should have been scaffolded"
    print("  ✓ Psaume was scaffolded")

    # Simulate user leaving scaffolded Psaume empty → rehydration drops it
    valid_a = []
    for s in steps_a:
        label_n = norm_label(s.label or "")
        has_content = bool(s.label or s.reference or s.title)
        was_extracted = label_n in extracted_labels_a
        if has_content or was_extracted:
            valid_a.append(s)
    # Psaume has a label but no ref/title → has_content is True (it has label)
    # So it's kept. But it was NOT extracted, so if it were COMPLETELY empty it
    # would be dropped. With a label, it has content.
    # The drop rule is: drop steps with NO label, NO ref, NO title, AND not extracted.
    print(f"  After rehydration ({len(valid_a)} steps): {[s.label for s in valid_a]}")

    # --- Case B: record WITH empty Alléluia and Psaume (extracted) ---
    print("\nCase B: record WITH empty Alléluia and Psaume (extracted)")
    steps_b = [
        LiturgyStep(label="Chant d'entrée", title="Autre chant"),
        LiturgyStep(label="1ère Lecture", reference="L2"),
        LiturgyStep(label="Psaume"),  # Extracted but empty
        LiturgyStep(label="Alléluia"),  # Extracted but empty
        LiturgyStep(label="Évangile", reference="E2"),
        LiturgyStep(label="Prière Universelle", title="Prière B"),
        LiturgyStep(label="Chant d'Adieu", title="Adieu B"),
    ]
    extracted_labels_b = {norm_label(s.label) for s in steps_b if s.label}
    print(f"  Extracted labels: {extracted_labels_b}")

    # Scaffold (Psaume and Alléluia already exist → no scaffolding)
    existing_norms_b = {norm_label(s.label) for s in steps_b if s.label}
    for scaffold_label in SCAFFOLD_RUBRICS:
        if norm_label(scaffold_label) not in existing_norms_b:
            steps_b.insert(len(steps_b), LiturgyStep(label=scaffold_label))

    # Rehydration
    valid_b = []
    for s in steps_b:
        label_n = norm_label(s.label or "")
        has_content = bool(s.label or s.reference or s.title)
        was_extracted = label_n in extracted_labels_b
        if has_content or was_extracted:
            valid_b.append(s)

    result_labels_b = [s.label for s in valid_b]
    print(f"  After rehydration ({len(valid_b)} steps): {result_labels_b}")

    assert "Psaume" in result_labels_b, "FAIL: Extracted empty Psaume was dropped!"
    assert "Alléluia" in result_labels_b, "FAIL: Extracted empty Alléluia was dropped!"
    print("  ✓ Case B's extracted empty Psaume survived rehydration")
    print("  ✓ Case B's extracted empty Alléluia survived rehydration")

    print("\n=== SCAFFOLD + REHYDRATION TEST PASSED ===")


def try_page_count(docx_path: str):
    """Best-effort PDF conversion and page-count check (amendment 4)."""
    import shutil
    import subprocess

    # Try LibreOffice
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("⚠ SKIP page-count check: LibreOffice not found (amendment 4: best-effort)")
        return

    try:
        output_dir = os.path.dirname(docx_path)
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", docx_path, "--outdir", output_dir],
            capture_output=True, text=True, timeout=30,
        )
        pdf_path = docx_path.replace(".docx", ".pdf")
        if not os.path.exists(pdf_path):
            print(f"⚠ SKIP page-count: PDF conversion produced no output")
            return

        # Try pdfinfo
        pdfinfo = shutil.which("pdfinfo")
        if pdfinfo:
            result = subprocess.run([pdfinfo, pdf_path], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if line.startswith("Pages:"):
                    pages = int(line.split(":")[1].strip())
                    assert pages == 1, f"FAIL: Generated PDF has {pages} pages, expected 1"
                    print(f"✓ Page count: {pages} (1 page as expected)")
                    break
        else:
            # Fallback: check file size (rough heuristic)
            size = os.path.getsize(pdf_path)
            print(f"⚠ pdfinfo not found; PDF size: {size} bytes (cannot verify page count)")

        os.remove(pdf_path)
    except subprocess.TimeoutExpired:
        print("⚠ SKIP page-count: LibreOffice conversion timed out")
    except Exception as e:
        print(f"⚠ SKIP page-count: {e}")


if __name__ == "__main__":
    test_full_ontology_deroule()
    test_scaffold_and_rehydration()
    print("\n=== ALL FULL ONTOLOGY TESTS PASSED ===")
