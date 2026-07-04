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
from .llm import generate_with_resilience

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
    
    # We use the Pydantic model directly for response_schema
    
    system_instruction = (
        "You are the Writer agent. Your task is to generate sober, warm, and liturgically appropriate content in French.\n"
        "ALL factual content (names, dates, places, readings, songs, participants) MUST come exclusively from the Record data provided. "
        "NEVER invent, assume, or reuse facts from prior examples.\n\n"

        "1. MOT D'ACCUEIL: Write a short welcoming word based ONLY on deceased.personalityTraits and deceased.lifeElements. "
        "Do not invent biography or add facts not present in the record.\n\n"

        "2. UNIVERSAL PRAYER INTENTIONS: Complete universalPrayerIntentions to 3-4 total intentions. "
        "Keep any existing intentions and their reader assignments from record.participants.prayerReaders.\n\n"

        "3. EMAIL (subject + body):\n"
        "   - Subject: 'Préparation des obsèques de {deceased.firstName} {deceased.lastName}' followed by the ceremony date from record.ceremony.date if available.\n"
        "   - Body: a sober French email to the priest and pastoral team presenting the ceremony preparation.\n"
        "     Structure the body as follows:\n"
        "     a) Opening line with the deceased's name (from the record) and ceremony logistics (date, time, church — from the record; mark missing ones as 'à compléter').\n"
        "     b) Liturgy recap: iterate over record.ceremony.liturgySteps; for each step, state its label and title/reference. "
        "If a step has no title or reference, mark it explicitly as 'à compléter'.\n"
        "     c) Readers and prayer readers: list the actual names and roles from record.participants.readers and record.participants.prayerReaders. "
        "State the total number of proposed universal prayer intentions.\n"
        "     d) A one-line mention that the mot d'accueil is drafted from the family's words.\n"
        "     e) If record.deceased.avoidMentioning is non-empty, add a discreet note: 'À ne pas mentionner lors de la célébration : [list]'.\n"
        "     f) Close with a polite sign-off.\n"
        "   - For ANY missing liturgical field, explicitly state 'à compléter'.\n\n"

        "CRITICAL: Do NOT mention any term derived from deceased.avoidMentioning in any of the generated text.\n"
        "CRITICAL: Do NOT double-escape newlines in the email body or subject. Use actual newline characters, not literal backslash-n sequences."
    )
    
    prompt = f"Record data:\n{record.model_dump_json(indent=2)}"
    
    def try_generate(extra_instruction=""):
        response = generate_with_resilience(
            client=client,
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction + extra_instruction,
                response_mime_type="application/json",
                response_schema=WriterLLMResponse,
                temperature=0.0
            )
        )
        if isinstance(response.parsed, WriterLLMResponse):
            return response.parsed
        elif isinstance(response.parsed, dict):
            return WriterLLMResponse(**response.parsed)
        else:
            return WriterLLMResponse(**json.loads(response.text))

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
