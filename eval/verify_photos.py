import os
import sys
from pathlib import Path

# Setup path so we can import agents
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.env import load_environment
load_environment()

from PIL import Image, ImageDraw, ImageFont
from agents.extractor import extract_record

def create_synthetic_notes_image() -> Image.Image:
    """Creates a basic image with text resembling hand-written notes."""
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Text from the Jeanne Martin example
    text = """
    Défunt: Jeanne Martin
    Née le 12 avril 1940
    Date obsèques: 15 mai, 14h00, Eglise St Jean
    
    Contact: Pierre Martin (fils) - 06 12 34 56 78
    
    Chant d'entrée: Trouver dans ma vie ta présence (Lu par Anne)
    1ère Lecture: Lettre de St Paul aux Romains
    
    Traits de caractère:
    - Aimait son jardin
    - Toujours souriante
    """
    
    # We use a default font
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
        
    draw.text((20, 20), text, fill='black', font=font)
    return img

def run_test():
    print("Generating synthetic image...")
    img = create_synthetic_notes_image()
    
    print("Running extraction (this will use the multimodal model)...")
    record = extract_record([img])
    
    print("\nExtraction complete. Verifying...")
    
    # Assertions
    assert record.deceased.firstName == "Jeanne", f"Expected 'Jeanne', got '{record.deceased.firstName}'"
    assert record.deceased.lastName == "Martin", f"Expected 'Martin', got '{record.deceased.lastName}'"
    
    # Check that Psalm is missing/empty (we only provided entrance chant and 1st reading)
    psalm_step = next((s for s in record.ceremony.liturgySteps if "psaume" in (s.label or "").lower()), None)
    if psalm_step:
        assert not psalm_step.title and not psalm_step.reference, "Psalm should be empty since it was not in the notes"
    
    print("OK: All photo extraction assertions passed!")

if __name__ == "__main__":
    try:
        run_test()
    except AssertionError as e:
        print(f"Error: Test Failed: {e}")
        sys.exit(1)
