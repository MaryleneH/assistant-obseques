"""
Checker (Safety) Agent for Assistant Obsèques.
Implements a hybrid checking logic (Deterministic rules + LLM judgment).
"""
import os
import sys
import json
import time
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from .models import Record

model_name = os.getenv("WRITER_MODEL")
if not model_name or "placeholder" in model_name:
    print("FATAL: WRITER_MODEL environment variable must be set to a valid model ID.", file=sys.stderr)
    sys.exit(1)

# Helper Pydantic schema for the LLM portion
class CheckerLLMResponse(BaseModel):
    suggestedQuestions: list[str] = Field(
        default_factory=list, 
        description="Concrete French questions for the family, each targeting a specific missing or uncertain field."
    )
    coherenceObservations: list[str] = Field(
        default_factory=list, 
        description="Nuanced coherence observations, which will be appended to recommendedActions."
    )

def check_record(record: Record) -> Record:
    """
    Validates a Record, applying deterministic safety checks and an LLM-based quality check.
    """
    alerts = []
    recommended_actions = []
    
    # 1. Deterministic Belt
    is_blocking = False
    is_warning = False
    
    # Required identity/logistics (BLOCKING)
    if not record.deceased.firstName:
        alerts.append("Prénom du défunt manquant.")
        is_blocking = True
    if not record.deceased.lastName:
        alerts.append("Nom de famille du défunt manquant.")
        is_blocking = True
    if not record.ceremony.date:
        alerts.append("Date de la cérémonie manquante.")
        is_blocking = True
    if not record.ceremony.time:
        alerts.append("Heure de la cérémonie manquante.")
        is_blocking = True
    if not record.ceremony.church:
        alerts.append("Église de la cérémonie manquante.")
        is_blocking = True
    if not record.ceremony.celebrant:
        alerts.append("Célébrant de la cérémonie manquant.")
        is_blocking = True

    # Content gaps (WARNING)
    if not record.ceremony.entranceSong:
        alerts.append("Chant d'entrée manquant.")
        is_warning = True
    if not record.ceremony.firstReading:
        alerts.append("Première lecture manquante.")
        is_warning = True
    if not record.ceremony.psalm:
        alerts.append("Psaume manquant.")
        is_warning = True
    if not record.ceremony.gospel:
        alerts.append("Évangile manquant.")
        is_warning = True
    if not record.ceremony.finalFarewellSong:
        alerts.append("Chant du dernier adieu manquant.")
        is_warning = True
    if not record.communication.priestEmail:
        alerts.append("Email du prêtre manquant.")
        is_warning = True

    # Recipient allowlist (BLOCKING safety violation)
    allowed_emails_str = os.getenv("ALLOWED_EMAILS", "")
    allowed_emails = [email.strip().lower() for email in allowed_emails_str.split(",") if email.strip()]
    
    emails_to_check = []
    if record.communication.priestEmail:
        emails_to_check.append(record.communication.priestEmail)
    for team_email in record.communication.teamEmails:
        emails_to_check.append(team_email)
        
    for email in emails_to_check:
        if email.strip().lower() not in allowed_emails:
            alerts.append(f"VIOLATION DE SÉCURITÉ: L'adresse email '{email}' n'est pas autorisée.")
            is_blocking = True

    # Ensure avoidMentioning and contradictions carry forward
    if record.extraction.contradictions:
        alerts.append("Contradictions détectées dans les notes.")
        is_warning = True

    # 2. LLM Suspenders
    suggested_questions = []
    coherence_observations = []
    try:
        client = genai.Client()
        
        # We need to drop additionalProperties from the schema since we are using Developer API
        def remove_additional_properties(d):
            if isinstance(d, dict):
                d.pop("additionalProperties", None)
                for k, v in d.items():
                    remove_additional_properties(v)
            elif isinstance(d, list):
                for item in d:
                    remove_additional_properties(item)
            return d
            
        schema_dict = remove_additional_properties(CheckerLLMResponse.model_json_schema())
        
        prompt = (
            "Analyze the following record for missing or uncertain fields. "
            "Generate concrete French questions to ask the family to fill these gaps. "
            "CAP the suggestedQuestions at the 5 most important, prioritizing safety/identity gaps first, then liturgical content. "
            "Also add any nuanced coherence observations. "
            f"Record data:\n{record.model_dump_json(indent=2)}"
        )
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="You are a quality checker for an AI assistant helping a sacristan prepare Catholic funerals.",
                        response_mime_type="application/json",
                        response_schema=schema_dict,
                        temperature=0.0
                    )
                )
                
                if isinstance(response.parsed, CheckerLLMResponse):
                    llm_res = response.parsed
                elif isinstance(response.parsed, dict):
                    llm_res = CheckerLLMResponse(**response.parsed)
                else:
                    llm_res = CheckerLLMResponse(**json.loads(response.text))
                
                suggested_questions = llm_res.suggestedQuestions
                coherence_observations = llm_res.coherenceObservations
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                print(f"Checker attempt {attempt + 1} failed: {e}. Retrying...", file=sys.stderr)
                time.sleep(2)
        
    except Exception as e:
        print(f"Warning: LLM suspenders failed: {e}", file=sys.stderr)
        recommended_actions.append("Le service d'assistance IA (génération de questions) est indisponible pour le moment.")

    # 3. Aggregation and Status Update
    recommended_actions.extend(coherence_observations)
    
    if is_blocking:
        record.qualityCheck.status = "BLOCKING"
    elif is_warning:
        record.qualityCheck.status = "WARNING"
    else:
        record.qualityCheck.status = "OK"
        
    record.qualityCheck.alerts = alerts
    record.qualityCheck.recommendedActions = recommended_actions
    record.qualityCheck.suggestedQuestions = suggested_questions
    
    # Gate keeper always needs review
    record.status = "needs_review"
    
    return record
