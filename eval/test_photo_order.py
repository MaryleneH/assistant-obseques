"""
Multi-photo page ordering test — verifies that:
  (a) Two pages sent as [p1, p2] produce a consolidated extraction
      covering content from BOTH pages.
  (b) Two pages sent as [p2, p1] (swapped) ALSO produce a consolidated
      extraction covering content from both pages — the extractor
      consolidates regardless of page order.
  (c) The backend receives photos in the order specified by the client
      (FormData array order = display order = page order).

Uses synthetic PIL images with text (fictional data only — hard rule 7).
Each image contains a subset of rubrics so we can verify that BOTH
pages contributed to the final extraction.

This test calls the Gemini multimodal model (EXTRACTOR_MODEL).
"""
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
os.environ["AUTH_MODE"] = "off"

from PIL import Image, ImageDraw, ImageFont
from agents.orchestrator import run_until_review
from agents.liturgy import norm_label


# ── Synthetic page images ─────────────────────────────────────

# Page 1: identity + first half of rubrics (Entrée through Psaume)
PAGE_1_TEXT = """
FEUILLE DE PRÉPARATION — PAGE 1

Défunte : Marie-Louise Garnier, 86 ans
Née le 5 février 1940
Date : vendredi 25 juillet 2026 à 15h00
Église : Saint-Étienne
Célébrant : Père Bernard

Entrée : Famille et amis
Chant d'entrée : N° 5 — Trouver dans ma vie ta présence
Rite de la lumière : porteurs André, Sophie
1ère Lecture : L3 Page 12 (Livre de la Sagesse)
Lecteur : André (fils)
Psaume : 22 — Le Seigneur est mon berger
"""

# Page 2: second half of rubrics (Évangile through Sortie)
PAGE_2_TEXT = """
FEUILLE DE PRÉPARATION — PAGE 2

Évangile : E7 Page 45 (Saint Jean)
Prière Universelle : refrain Dieu de tendresse
Chant d'Adieu : N° 18 — Je vous salue Marie
Encensement / Bénédiction : Célébrant
Prière à Marie : Récitée par l'assemblée
Bénédiction : Ave Maria — Assemblée
Sortie : Musique CD

Traits : généreuse, discrète, aimait la couture
Ne pas mentionner le divorce
"""


def create_text_image(text: str) -> Image.Image:
    """Create a synthetic white image with black text — readable by Gemini."""
    img = Image.new("RGB", (900, 700), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    draw.text((30, 20), text.strip(), fill="black", font=font)
    return img


# ── Markers: rubrics only present on page 1 vs page 2 ─────────
# If the extraction contains BOTH, it consolidated across pages.
# These must match norm_label() output: lowercase, accents KEPT.
PAGE_1_MARKERS = {"chant d'entrée", "1ère lecture", "psaume", "rite de la lumière"}
PAGE_2_MARKERS = {"évangile", "chant d'adieu", "prière à marie", "sortie"}


def extract_label_set(record) -> set[str]:
    """Return normalized labels from the record's liturgySteps."""
    return {
        norm_label(s.label)
        for s in record.ceremony.liturgySteps
        if s.label
    }


def assert_both_pages_present(labels: set[str], case_name: str):
    """Assert that rubrics from BOTH pages appear in the extraction."""
    found_p1 = PAGE_1_MARKERS & labels
    found_p2 = PAGE_2_MARKERS & labels

    print(f"    Page-1 markers found: {found_p1}")
    print(f"    Page-2 markers found: {found_p2}")

    assert len(found_p1) >= 2, (
        f"[{case_name}] Expected ≥2 page-1 markers, found {found_p1}"
    )
    assert len(found_p2) >= 2, (
        f"[{case_name}] Expected ≥2 page-2 markers, found {found_p2}"
    )


# ── Test (a): [p1, p2] — normal order ─────────────────────────

def test_normal_order():
    """Two pages in order [p1, p2] → consolidated extraction."""
    print("\n" + "=" * 60)
    print("  TEST A: Normal order [page1, page2]")
    print("=" * 60)

    img1 = create_text_image(PAGE_1_TEXT)
    img2 = create_text_image(PAGE_2_TEXT)

    record = run_until_review([img1, img2])
    labels = extract_label_set(record)

    print(f"  Extracted {len(record.ceremony.liturgySteps)} liturgy steps")
    print(f"  Labels: {sorted(labels)}")
    print(f"  Deceased: {record.deceased.firstName} {record.deceased.lastName}")

    # Identity from page 1
    assert record.deceased.lastName and "garnier" in record.deceased.lastName.lower(), (
        f"Expected 'Garnier', got '{record.deceased.lastName}'"
    )

    # Content from both pages
    assert_both_pages_present(labels, "normal_order")

    # avoidMentioning from page 2
    avoid = [a.lower() for a in (record.deceased.avoidMentioning or [])]
    avoid_text = " ".join(avoid)
    assert "divorce" in avoid_text, (
        f"Expected 'divorce' in avoidMentioning (page 2), got {avoid}"
    )

    print("  ✓ Identity extracted (page 1)")
    print("  ✓ Rubrics consolidated from both pages")
    print("  ✓ avoidMentioning captured (page 2)")
    print("  ✓ TEST A PASSED")

    return record


# ── Test (b): [p2, p1] — swapped order ────────────────────────

def test_swapped_order():
    """Two pages in swapped order [p2, p1] → still consolidated."""
    print("\n" + "=" * 60)
    print("  TEST B: Swapped order [page2, page1]")
    print("=" * 60)

    img1 = create_text_image(PAGE_1_TEXT)
    img2 = create_text_image(PAGE_2_TEXT)

    # Send page2 FIRST, page1 SECOND
    record = run_until_review([img2, img1])
    labels = extract_label_set(record)

    print(f"  Extracted {len(record.ceremony.liturgySteps)} liturgy steps")
    print(f"  Labels: {sorted(labels)}")
    print(f"  Deceased: {record.deceased.firstName} {record.deceased.lastName}")

    # Identity still found (from page 1, even though it arrived second)
    assert record.deceased.lastName and "garnier" in record.deceased.lastName.lower(), (
        f"Expected 'Garnier' even with swapped pages, got '{record.deceased.lastName}'"
    )

    # Content from both pages — regardless of order
    assert_both_pages_present(labels, "swapped_order")

    print("  ✓ Identity extracted despite swap")
    print("  ✓ Rubrics consolidated from both pages")
    print("  ✓ TEST B PASSED")

    return record


# ── Test (c): backend order preservation via TestClient ────────

def test_backend_order_preservation():
    """Verify that the /extract endpoint receives photos in FormData order."""
    print("\n" + "=" * 60)
    print("  TEST C: Backend receives photos in client array order")
    print("=" * 60)

    import io
    from fastapi.testclient import TestClient
    import ui.app as app_module

    client = TestClient(app_module.app)

    # Create two distinguishable tiny images
    img_a = Image.new("RGB", (50, 50), color="red")
    img_b = Image.new("RGB", (50, 50), color="blue")

    buf_a = io.BytesIO()
    img_a.save(buf_a, format="JPEG")
    buf_a.seek(0)

    buf_b = io.BytesIO()
    img_b.save(buf_b, format="JPEG")
    buf_b.seek(0)

    # Send as multipart — order: [red, blue]
    files = [
        ("photos", ("page1.jpg", buf_a, "image/jpeg")),
        ("photos", ("page2.jpg", buf_b, "image/jpeg")),
    ]
    data = {"notes": ""}

    # We just need to verify the endpoint accepts multi-file in order.
    # Patch run_until_review to avoid calling the LLM — capture the
    # PIL images it receives and return a minimal valid Record.
    from unittest.mock import patch
    from agents.models import Record, CeremonyStatus

    # A real (minimal) Record — MagicMock can't fake Pydantic nesting
    stub_record = Record()
    stub_record.status = CeremonyStatus.needs_review

    received_pages = []

    def capture_run(pages):
        """Intercept: capture the images, return a stub Record."""
        received_pages.extend(pages)
        return stub_record

    with patch.object(app_module, "run_until_review", side_effect=capture_run):
        resp = client.post("/extract", data=data, files=files, follow_redirects=False)

    # The endpoint should have received 2 images in order
    assert len(received_pages) == 2, f"Expected 2 pages, got {len(received_pages)}"
    assert isinstance(received_pages[0], Image.Image), "Page 1 should be a PIL Image"
    assert isinstance(received_pages[1], Image.Image), "Page 2 should be a PIL Image"

    # Verify color order: red first, blue second
    r1, g1, b1 = received_pages[0].getpixel((25, 25))
    r2, g2, b2 = received_pages[1].getpixel((25, 25))

    assert r1 > 200 and b1 < 50, f"First image should be red, got RGB({r1},{g1},{b1})"
    assert b2 > 200 and r2 < 50, f"Second image should be blue, got RGB({r2},{g2},{b2})"

    print("  ✓ /extract received 2 images")
    print(f"  ✓ Image 1: RGB({r1},{g1},{b1}) — red (correct order)")
    print(f"  ✓ Image 2: RGB({r2},{g2},{b2}) — blue (correct order)")
    print("  ✓ TEST C PASSED")


# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== MULTI-PHOTO PAGE ORDERING TESTS ===\n")
    print("All data is fictional (hard rule 7).\n")

    # Test C is fast (no LLM) — run first
    test_backend_order_preservation()

    # Tests A and B call the multimodal model
    test_normal_order()
    test_swapped_order()

    print("\n=== ALL PAGE-ORDERING TESTS PASSED ===")
