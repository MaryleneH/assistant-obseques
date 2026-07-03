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

model_name = os.getenv("EXTRACTOR_MODEL")
if not model_name or "placeholder" in model_name:
    print("FATAL: EXTRACTOR_MODEL environment variable must be set to a valid model ID.", file=sys.stderr)
    sys.exit(1)

_INSTRUCTIONS = """You are the Extractor agent for Assistant Obsèques.
Your job is to read free-form interview notes or photos and extract exactly ONE consolidated JSON record.

CRITICAL BEHAVIOUR CONTRACT:
1. NEVER INVENT DATA & FIELD SEMANTICS: If a field is unknown or not explicitly stated in the input, leave it as null/empty. Content fields (like `ceremony.firstReading` or `ceremony.universalPrayerIntentions`) hold CONTENT only. If the notes only state WHO does something (e.g. "read by Pierre"), the content field stays null/empty, and you must add the missing content to `extraction.missingFields`.
2. LITURGY STEPS & CANONICAL LABELS: Extract `ceremony.liturgySteps` in liturgical order. Use canonical rubric labels for known steps: « Chant d'entrée », « 1ère Lecture », « Psaume », « Évangile », « Prière Universelle », « Chant d'Adieu ». Keep verbatim titles/references. The `detail` field must preserve the ASSIGNMENT notes (who does what, e.g. "Pierre (fils)" or "Claire (petite-fille) - une intention"). Only drop detail text if it merely repeats the rubric label.
3. DATE & TIME NORMALIZATION: `ceremony.date` must be ISO YYYY-MM-DD. `ceremony.time` must be HH:MM. If the year is absent in the notes, infer the current year (based on the "Today's Date" provided below) AND add a note to `extraction.needsHumanReview` stating the year was inferred.
4. MISSING FIELDS QUALITY: `extraction.missingFields` must contain human-readable French descriptions of ceremony-content gaps only (e.g., "référence ou texte de la première lecture", "références (n°/page) des chants choisis", "nombre ou textes des intentions de prière"). Do NOT list system-assigned fields (caseId, timestamps, status, communication internals).
5. CONTRADICTIONS: If notes contradict each other, do not silently overwrite. Log in `extraction.contradictions` (field, values, pages).
6. UNCERTAINTY: For uncertain readings, list the key in `extraction.needsHumanReview` and assign a score (<1.0) in `extraction.fieldConfidences`.
7. AVOID MENTIONING: Capture any topics the family asked to avoid verbatim in `deceased.avoidMentioning`.
8. SOURCE TYPE: Set `extraction.sourceType` to the exact value "manual_notes" (unless it's a photo/PDF).
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
        
    response = client.models.generate_content(
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
        try:
            record_dict = json.loads(response.text)
            return Record(**record_dict)
        except Exception as e:
            print("Failed to parse response into Record:", response.text)
            raise e
