"""
Orchestrator Agent for Assistant Obsèques.
This agent is the root agent exposed to ADK. It orchestrates the Extractor, Checker,
and Writer agents, and invokes external MCP tools and runtime skills.
"""
from typing import Any
import logging
import subprocess

# Note: google.adk will be used here. Expose as root_agent.
# from google.adk import Agent # Example ADK import

from .telemetry import init_telemetry

def start_pipeline(notes: str) -> dict[str, Any]:
    """
    Entry point for the orchestration pipeline.
    """
    init_telemetry()
    logging.info("Starting Assistant Obsèques pipeline...")
    # TODO: Implement orchestration logic
    return {"status": "mock_response"}

def build_deroule(input_json_path: str, output_docx_path: str) -> None:
    """
    Invokes the runtime skill to build the Word document.
    """
    cmd = [
        "node", 
        "skills/deroule-obseques/scripts/build_deroule.js", 
        input_json_path, 
        output_docx_path
    ]
    subprocess.run(cmd, check=True)

# Define root_agent here for ADK discovery
root_agent = start_pipeline # Placeholder
