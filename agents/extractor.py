"""
Extractor Agent for Assistant Obsèques.
Extracts structured information from notes or photos using a Multimodal Gemini model.
"""
from typing import Any

def extract_record(notes_or_photos: Any) -> dict[str, Any]:
    """
    Extracts exactly ONE record from multi-page notes.
    Flags missing fields and contradictions without inventing data.
    """
    # TODO: Implement extraction using Multimodal model
    pass
