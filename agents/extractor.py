"""
Extractor Agent for Assistant Obsèques.
Extracts structured information from notes or photos using a Multimodal Gemini model.
"""
import os
import sys
from typing import Any
import json
from datetime import date

from google.adk import Agent
from google import genai
from google.genai import types

from .models import Record
from .llm import generate_with_resilience
from .liturgy import CANONICAL_LABELS

model_name = os.getenv("EXTRACTOR_MODEL")
if not model_name or "placeholder" in model_name:
    print("FATAL: EXTRACTOR_MODEL environment variable must be set to a valid model ID.", file=sys.stderr)
    sys.exit(1)

# Build the canonical label list for the prompt from the shared ontology.
_LABEL_LIST = ", ".join(f"« {l} »" for l in CANONICAL_LABELS)

_INSTRUCTIONS = f"""You are the Extractor agent for Assistant Obsèques.
Your job is to read free-form interview notes or photos and extract exactly ONE consolidated JSON record.

CRITICAL BEHAVIOUR CONTRACT:

1. NEVER INVENT DATA & FIELD SEMANTICS
   If a field is unknown or not explicitly stated in the input, leave it as null/empty.
   Content fields (like `ceremony.firstReading` or `ceremony.universalPrayerIntentions`)
   hold CONTENT only.  If the notes only state WHO does something (e.g. "read by Pierre"),
   the content field stays null/empty, and you must add the missing content to
   `extraction.missingFields`.

2. FULL RUBRIC ONTOLOGY — LITURGY STEPS & CANONICAL LABELS
   Extract `ceremony.liturgySteps` in PRINTED ORDER on the sheet. Use these
   exact canonical rubric labels when they match:
   {_LABEL_LIST}.
   Rules:
   - Transcribe EVERY rubric present on the sheet, in the order it appears.
   - NEVER merge two rubrics.  "Entrée" and "Chant d'entrée" are DISTINCT steps.
     "Bénédiction" and "Encensement / Bénédiction" are DISTINCT.
   - A rubric present on the sheet but with no content written is STILL a step
     (emit it with null title/reference/detail).
   - Pre-printed assignments ("Célébrant", "Assemblée", "Famille") go into the
     `detail` field, NEVER into `title`.
   - The `detail` field preserves ASSIGNMENT notes (who does what, e.g.
     "Pierre (fils)", "Équipe", "Célébrant", "En entier", "CD").
   - Only drop detail text if it merely repeats the rubric label with no added
     information.

3. VERBATIM TITLES — NEVER FABRICATE
   The `title` field must contain ONLY words explicitly written as a title or
   song name.  Rules:
   - Do NOT copy the label into the title (e.g. "Psaume 114" when the label is
     "Psaume" and the reference is "114 Page 24" — title stays null).
   - Do NOT copy the label into the title (e.g. "Prière à Marie" when the label
     IS "Prière à Marie" — title stays null).
   - Do NOT invent descriptive titles (e.g. "Musique de sortie" — if only "CD"
     is written, that goes to detail; title stays null).
   - Performance notes like "En entier", "CD", "Récitée", "Chanté" go to `detail`,
     never to `title`.

4. RATURE (CROSSED-OUT TEXT) POLICY
   Crossed-out text is corrected-away text:
   - If a REPLACEMENT is written next to the crossed-out text (e.g. JUIN crossed
     out → JUILLET written), use the REPLACEMENT only.
   - If text is crossed out with NO replacement (e.g. a struck surname), OMIT
     the crossed-out text entirely.  When the omission touches an identity field
     (name, relationship), add a French note to `extraction.needsHumanReview`:
     "Nom raturé ignoré — vérifier l'orthographe : <crossed-out text>".

5. DATE & TIME NORMALIZATION
   `ceremony.date` must be ISO YYYY-MM-DD.  `ceremony.time` must be HH:MM.
   If the year is absent in the notes, infer the current year (based on the
   "Today's Date" provided below) AND add a note to `extraction.needsHumanReview`
   stating the year was inferred.

6. MISSING FIELDS QUALITY
   `extraction.missingFields` must contain human-readable French descriptions
   of ceremony-content gaps only (e.g., "référence ou texte de la première
   lecture", "références (n°/page) des chants choisis", "nombre ou textes des
   intentions de prière").  Do NOT list system-assigned fields (caseId,
   timestamps, status, communication internals).

7. CONTRADICTIONS
   If notes contradict each other, do not silently overwrite.  Log in
   `extraction.contradictions` (field, values, pages).

8. UNCERTAINTY
   For uncertain readings (especially handwriting), list the key in
   `extraction.needsHumanReview` and assign a confidence score (< 1.0) in
   `extraction.fieldConfidences`.

9. AVOID MENTIONING
   Capture any topics the family asked to avoid verbatim in
   `deceased.avoidMentioning`.

10. SOURCE TYPE
    Set `extraction.sourceType` to "manual_notes" for text notes, or "photo"
    for photo/PDF input.
"""

extractor_agent = Agent(
    name="extractor",
    instruction=_INSTRUCTIONS,
    model=model_name,
    output_schema=Record
)

def extract_record(notes_or_photos: Any) -> Record:
    """
    Extracts exactly ONE record from multi-page notes.
    Flags missing fields and contradictions without inventing data.
    """
    client = genai.Client()
    
    if isinstance(notes_or_photos, list):
        prompt = ["Please extract a single consolidated record from the following pages of notes:\n"] + notes_or_photos
    else:
        prompt = ["Please extract a single consolidated record from the following notes:\n", notes_or_photos]
    
    # We join strings if they are purely text, though GenAI client accepts lists of strings
    if all(isinstance(p, str) for p in prompt):
        prompt_content = "\n".join(prompt)
    else:
        prompt_content = prompt
        
    def remove_additional_properties(d):
        if isinstance(d, dict):
            d.pop("additionalProperties", None)
            for k, v in d.items():
                remove_additional_properties(v)
        elif isinstance(d, list):
            for item in d:
                remove_additional_properties(item)
        return d
        
    schema_dict = Record.model_json_schema()
    schema_dict = remove_additional_properties(schema_dict)
    
    # Inject today's date to give the model a clock for year inference
    current_instruction = _INSTRUCTIONS + f"\n[SYSTEM DATA]\nToday's Date: {date.today().isoformat()}"
        
    response = generate_with_resilience(
        client=client,
        model=model_name,
        contents=prompt_content,
        config=types.GenerateContentConfig(
            system_instruction=current_instruction,
            response_mime_type="application/json",
            response_schema=schema_dict,
            temperature=0.0
        )
    )
    
    # Check if the client parsed it into a pydantic model or dict
    if isinstance(response.parsed, Record):
        return response.parsed
    elif isinstance(response.parsed, dict):
        return Record(**response.parsed)
    else:
        # Fallback manual parse
        record_dict = json.loads(response.text)
        return Record(**record_dict)
