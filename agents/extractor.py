"""
Extractor Agent for Assistant Obsèques.
Extracts structured information from notes or photos using a Multimodal Gemini model.
"""
import os
import sys
from typing import Any
import json

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
1. NEVER INVENT DATA: If a field is unknown or not explicitly stated in the input, leave it as null/empty. Add its key to `extraction.missingFields`. Do NOT invent names, dates, emails, or readings.
2. LITURGY STEPS: Extract `ceremony.liturgySteps` in their original liturgical order. Keep hymn-book references, titles, and assignment notes VERBATIM. Do NOT fabricate steps not mentioned.
3. CONTRADICTIONS: If different pages or parts of the notes contradict each other (e.g. two different times), do NOT silently overwrite. Log the contradiction in `extraction.contradictions` with the field name, the conflicting values, and the page numbers.
4. UNCERTAINTY: If handwriting or context makes a field uncertain, output the best guess, but list the field key in `extraction.needsHumanReview` and assign a confidence score (< 1.0) in `extraction.fieldConfidences`.
5. AVOID MENTIONING: Capture any topics the family asked to avoid verbatim in `deceased.avoidMentioning`.
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
        
    response = client.models.generate_content(
        model=model_name,
        contents=prompt_content,
        config=types.GenerateContentConfig(
            system_instruction=_INSTRUCTIONS,
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
