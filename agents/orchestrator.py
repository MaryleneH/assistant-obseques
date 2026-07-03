"""
Orchestrator Agent for Assistant Obsèques.
This agent is the root agent exposed to ADK. It orchestrates the Extractor, Checker,
and Writer agents, and invokes external MCP tools and runtime skills.
"""
from typing import Any
import logging
import subprocess

from google.adk import Agent
from .telemetry import init_telemetry

# Initialize telemetry at startup
init_telemetry()

def start_pipeline(notes: str) -> dict[str, Any]:
    """
    Entry point for the orchestration pipeline.
    """
    logging.info("Starting Assistant Obsèques pipeline...")
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

# Define root_agent as an ADK Agent instance so adk web discovery works
root_agent = Agent(
    name="orchestrator",
    instruction="I am the orchestrator for the Assistant Obsèques pipeline. I coordinate notes extraction, checking, human validation, and final document generation.",
    tools=[start_pipeline]
)
