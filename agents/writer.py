"""
Writer Agent for Assistant Obsèques.
Generates liturgy contents and drafts communication emails.

Design rationale: the email subject/body use a DETERMINISTIC template
(not LLM-generated) for the liturgy recap and the date so that:
  1. edits from the A2UI always survive to the email (no LLM paraphrasing);
  2. dates are French long-form by construction (never ISO);
  3. "à compléter" never leaks into the email (the .docx keeps its own
     placeholder rules independently).
The LLM is still used for the mot d'accueil and prayer intentions.
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
from .liturgy import french_date, CONTENT_RUBRICS, norm_label

model_name = os.getenv("WRITER_MODEL")
if not model_name or "placeholder" in model_name:
    print("FATAL: WRITER_MODEL environment variable must be set to a valid model ID.", file=sys.stderr)
    sys.exit(1)


# ── The LLM only generates the creative/pastoral content ─────────────
class WriterLLMResponse(BaseModel):
    motDAccueil: str = Field(description="Short mot d'accueil drawing ONLY on personalityTraits and lifeElements")
    universalPrayerIntentions: list[str] = Field(description="Completed list of 3-4 universal prayer intentions")


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


def _build_liturgy_recap(record: Record) -> str:
    """Build the liturgy recap for the email body — deterministic, not LLM.

    Every liturgyStep is listed in order:
    - Step WITH content: "label : title/reference (detail)"
    - Step WITHOUT content: bare "label" alone
    NO "à compléter" — the email is the sacristan's internal tool;
    she knows what to fill.  Placeholders belong to the .docx only.
    """
    lines = []
    for step in record.ceremony.liturgySteps:
        label = step.label or "(sans libellé)"
        parts = []
        if step.reference:
            parts.append(step.reference)
        if step.title:
            parts.append(step.title)
        if step.detail:
            parts.append(step.detail)
        if parts:
            lines.append(f"  • {label} : {' — '.join(parts)}")
        else:
            lines.append(f"  • {label}")
    return "\n".join(lines)


def _build_email_subject(record: Record) -> str:
    """Deterministic email subject with French long date."""
    first = record.deceased.firstName or ""
    last = record.deceased.lastName or ""
    name = f"{first} {last}".strip()
    date_str = french_date(record.ceremony.date or "", capitalize=False)
    if date_str:
        return f"Préparation des obsèques de {name} — {date_str}"
    return f"Préparation des obsèques de {name}"


def _build_email_body(record: Record, mot_accueil: str) -> str:
    """Deterministic email body with French dates everywhere."""
    first = record.deceased.firstName or ""
    last = record.deceased.lastName or ""
    name = f"{first} {last}".strip()
    date_str = french_date(record.ceremony.date or "", capitalize=False)
    time_str = (record.ceremony.time or "").replace(":", "h")
    church = record.ceremony.church or ""

    # Opening
    lines = [f"Bonjour,\n"]
    logistics = f"la préparation des obsèques de {name}"
    if date_str or time_str or church:
        details = []
        if date_str:
            details.append(f"le {date_str}")
        if time_str:
            details.append(f"à {time_str}")
        if church:
            details.append(f"à {church}")
        logistics += f" ({', '.join(details)})"
    lines.append(f"Veuillez trouver ci-dessous le récapitulatif pour {logistics}.\n")

    # Liturgy recap — bare labels for empty steps, no "à compléter"
    lines.append("Déroulé liturgique :")
    lines.append(_build_liturgy_recap(record))
    lines.append("")

    # Readers
    if record.participants.readers:
        lines.append("Lecteurs :")
        for r in record.participants.readers:
            rname = r.name or "?"
            task = f" — {r.task}" if r.task else ""
            lines.append(f"  • {rname}{task}")
        lines.append("")

    # Prayer readers
    if record.participants.prayerReaders:
        lines.append("Lecteurs de la prière universelle :")
        for r in record.participants.prayerReaders:
            rname = r.name or "?"
            lines.append(f"  • {rname}")
        lines.append("")

    # Mot d'accueil
    lines.append("Le mot d'accueil a été rédigé à partir des paroles de la famille.\n")

    # Avoid mentioning
    if record.deceased.avoidMentioning:
        topics = ", ".join(record.deceased.avoidMentioning)
        lines.append(f"À ne pas mentionner lors de la célébration : {topics}\n")

    lines.append("Cordialement,")
    return "\n".join(lines)


def write_record(record: Record) -> Record:
    if not record.security.humanValidated:
        raise ValueError("Record must be human-validated before generation.")
    if record.status != CeremonyStatus.ready_for_generation:
        raise ValueError("Record status must be 'ready_for_generation' before generation.")

    client = genai.Client()

    # The LLM generates ONLY pastoral content (mot d'accueil + prayer
    # intentions).  The email subject/body are built deterministically
    # from the record so that A2UI edits always survive.
    system_instruction = (
        "You are the Writer agent. Generate sober, warm, liturgically appropriate content in French.\n"
        "ALL factual content MUST come exclusively from the Record data provided. NEVER invent facts.\n\n"
        "1. MOT D'ACCUEIL: Write a short welcoming word based ONLY on deceased.personalityTraits "
        "and deceased.lifeElements. Do not invent biography.\n\n"
        "2. UNIVERSAL PRAYER INTENTIONS: Complete universalPrayerIntentions to 3-4 total intentions. "
        "Keep any existing intentions and their reader assignments from record.participants.prayerReaders.\n\n"
        "CRITICAL: Do NOT mention any term derived from deceased.avoidMentioning."
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

    # Deterministic post-check for avoidMentioning
    full_text = f"{res.motDAccueil} {' '.join(res.universalPrayerIntentions)}"
    has_violation = scan_for_avoid_mentioning(full_text, record.deceased.avoidMentioning)

    if has_violation:
        print("Violation detected! Retrying generation...", file=sys.stderr)
        aggro_inst = "\n\nAGGRESSIVE CONSTRAINT: YOU FAILED TO AVOID MENTIONING THE FORBIDDEN TOPICS. REWRITE ENTIRELY WITHOUT THEM."
        res = try_generate(extra_instruction=aggro_inst)

        full_text = f"{res.motDAccueil} {' '.join(res.universalPrayerIntentions)}"
        if scan_for_avoid_mentioning(full_text, record.deceased.avoidMentioning):
            raise ValueError("HARD SAFETY CONTRACT VIOLATED: avoidMentioning terms still present after retry.")

    record.ceremony.motDAccueil = res.motDAccueil
    record.ceremony.universalPrayerIntentions = res.universalPrayerIntentions

    # Email subject/body: deterministic, built from the record itself.
    # This guarantees that A2UI edits (which mutated the record) always
    # appear in the email, and that dates are French by construction.
    record.communication.emailSubject = _build_email_subject(record)
    record.communication.emailBody = _build_email_body(record, res.motDAccueil)

    record.status = CeremonyStatus.ceremony_generated
    return record
