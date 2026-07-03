"""
Writer Agent for Assistant Obsèques.
Generates liturgy contents and drafts communication emails.
"""
import os
import sys
import json
import re
from unicodedata import normalize
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from .models import Record, CeremonyStatus

model_name = os.getenv("WRITER_MODEL")
if not model_name or "placeholder" in model_name:
    print("FATAL: WRITER_MODEL environment variable must be set to a valid model ID.", file=sys.stderr)
    sys.exit(1)

class WriterLLMResponse(BaseModel):
    motDAccueil: str = Field(description="Short mot d'accueil drawing ONLY on personalityTraits and lifeElements")
    universalPrayerIntentions: list[str] = Field(description="Completed list of 3-4 universal prayer intentions")
    emailSubject: str = Field(description="Email subject")
    emailBody: str = Field(description="Sober French email to the priest and team. Mark missing liturgical fields as 'à compléter'.")

def _normalize_text(text: str) -> str:
    """Lowercase and remove accents for robust scanning."""
    return normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower()

def scan_for_avoid_mentioning(text: str, avoid_list: list[str]) -> bool:
    """
    Deterministically scan text for any avoidMentioning root words.
    Extract words >= 4 chars, exclude allowlist.
    """
    allowlist = {"dans", "mot", "accueil", "durant", "pendant", "celebration", "ceremonie"}
    
    normalized_text = _normalize_text(text)
    
    for phrase in avoid_list:
        words = re.findall(r'\b\w+\b', _normalize_text(phrase))
        for w in words:
            if len(w) >= 4 and w not in allowlist:
                if w in normalized_text:
                    return True
    return False

def write_record(record: Record) -> Record:
    if not record.security.humanValidated:
        raise ValueError("Record must be human-validated before generation.")
    if record.status != CeremonyStatus.ready_for_generation:
        raise ValueError("Record status must be 'ready_for_generation' before generation.")
        
    client = genai.Client()
    
    def remove_additional_properties(d):
        if isinstance(d, dict):
            d.pop("additionalProperties", None)
            for k, v in d.items():
                remove_additional_properties(v)
        elif isinstance(d, list):
            for item in d:
                remove_additional_properties(item)
        return d
        
    schema_dict = remove_additional_properties(WriterLLMResponse.model_json_schema())
    
    system_instruction = (
        "You are the Writer agent. Your task is to generate sober, warm, and liturgically appropriate content in French.\n"
        "1. Write a short 'mot d'accueil' based ONLY on deceased.personalityTraits and lifeElements. Do not invent biography.\n"
        "2. Complete the universalPrayerIntentions to 3-4 total intentions, keeping any existing ones and their reader assignments.\n"
        "3. Write a sober email (subject and body) to the priest and team presenting the ceremony. For any missing liturgical field (e.g. gospel, psalm), explicitly state 'à compléter'.\n"
        "CRITICAL: Do NOT mention any term derived from deceased.avoidMentioning in any of the generated text."
    )
    
    prompt = f"Record data:\n{record.model_dump_json(indent=2)}"
    
    def try_generate(extra_instruction=""):
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction + extra_instruction,
                        response_mime_type="application/json",
                        response_schema=schema_dict,
                        temperature=0.0
                    )
                )
                if isinstance(response.parsed, WriterLLMResponse):
                    return response.parsed
                elif isinstance(response.parsed, dict):
                    return WriterLLMResponse(**response.parsed)
                else:
                    return WriterLLMResponse(**json.loads(response.text))
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"Generation attempt {attempt + 1} failed: {e}. Retrying...", file=sys.stderr)
                time.sleep(2)

    res = try_generate()
    
    # Deterministic Post-Check
    full_text = f"{res.motDAccueil} {' '.join(res.universalPrayerIntentions)} {res.emailSubject} {res.emailBody}"
    has_violation = scan_for_avoid_mentioning(full_text, record.deceased.avoidMentioning)
    
    if has_violation:
        print("Violation detected! Retrying generation...", file=sys.stderr)
        aggro_inst = "\n\nAGGRESSIVE CONSTRAINT: YOU FAILED TO AVOID MENTIONING THE FORBIDDEN TOPICS. REWRITE ENTIRELY WITHOUT THEM."
        res = try_generate(extra_instruction=aggro_inst)
        
        full_text = f"{res.motDAccueil} {' '.join(res.universalPrayerIntentions)} {res.emailSubject} {res.emailBody}"
        if scan_for_avoid_mentioning(full_text, record.deceased.avoidMentioning):
            raise ValueError("HARD SAFETY CONTRACT VIOLATED: avoidMentioning terms still present after retry.")
            
    record.ceremony.motDAccueil = res.motDAccueil
    record.ceremony.universalPrayerIntentions = res.universalPrayerIntentions
    record.communication.emailSubject = res.emailSubject
    record.communication.emailBody = res.emailBody
    
    record.status = CeremonyStatus.ceremony_generated
    return record
