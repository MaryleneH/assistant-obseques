import os
import sys
import json
import tempfile
import subprocess
from datetime import datetime
from typing import Dict, Any

from agents.models import Record, CeremonyStatus

def _get_french_date(iso_date_str: str) -> str:
    """Deterministic French date formatting avoiding system locale dependency."""
    if not iso_date_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date_str)
        weekdays = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        months = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", 
                  "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        weekday = weekdays[dt.weekday()]
        day = dt.day
        day_str = "1er" if day == 1 else str(day)
        month = months[dt.month - 1]
        year = dt.year
        return f"{weekday} {day_str} {month} {year}"
    except ValueError:
        return iso_date_str

def build_deroule(record: Record) -> Record:
    """
    Renders a validated record into a one-page A4 Word document using the Node.js script.
    """
    if record.status != CeremonyStatus.ceremony_generated:
        raise ValueError("Record status must be 'ceremony_generated' to build déroulé.")

    # 1. Map Record to the JSON input expected by the Node.js skill
    
    # Defunt name format: "LastName FirstName, <age> ans"
    first = record.deceased.firstName or ""
    last = (record.deceased.lastName or "").upper()
    age = record.deceased.age
    defunt_name = f"{last} {first}".strip()
    defunt_str = f"{defunt_name}, {age} ans" if age else defunt_name
    
    # Eglise format: "Église Saint-Martin le Mardi 7 Juillet 2026 / 10h30"
    church = record.ceremony.church or ""
    date_str = _get_french_date(record.ceremony.date or "")
    time_str = (record.ceremony.time or "").replace(":", "h")
    
    eglise_parts = []
    if church:
        eglise_parts.append(church)
    if date_str:
        eglise_parts.append(f"le {date_str}")
    if time_str:
        eglise_parts.append(f"/ {time_str}")
    eglise_str = " ".join(eglise_parts)
    
    # Etapes mapping
    etapes = []
    for step in record.ceremony.liturgySteps:
        etape: Dict[str, Any] = {}
        if step.label:
            etape["label"] = step.label
            
        inline_val = step.reference or step.title or ""
        if inline_val:
            if not step.reference and step.title:
                # If there's no reference but a title, inline becomes italic
                etape["inline"] = [{"t": step.title, "i": True}]
            else:
                etape["inline"] = step.reference
                
        sub_parts = []
        if step.reference and step.title:
            sub_parts.append({"t": step.title, "i": True})
            if step.detail:
                sub_parts.append({"t": f" — {step.detail}"})
        elif step.detail:
            sub_parts.append({"t": step.detail})
            
        if sub_parts:
            # Flatten sub array or use as string
            etape["sub"] = sub_parts
        elif not inline_val:
            # Placeholder for missing values
            etape["sub"] = "à compléter"
            
        etapes.append(etape)
        
    skill_input = {
        "defunt": defunt_str,
        "eglise": eglise_str,
        "celebrant": record.ceremony.celebrant or "",
        "etapes": etapes,
        "prochaineMesse": record.ceremony.nextMass or ""
    }

    # 2. Invoke Node.js script
    # Ensure node is available
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True, shell=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("FATAL: Node.js is not installed or not in PATH. Required for deroule generation.", file=sys.stderr)
        sys.exit(1)

    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
    os.makedirs(output_dir, exist_ok=True)
    output_docx = os.path.join(output_dir, f"deroule_{record.caseId or 'temp'}.docx")
    
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "skills", "deroule-obseques", "scripts", "build_deroule.js"))

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmp_in:
        json.dump(skill_input, tmp_in, ensure_ascii=False)
        temp_input_path = tmp_in.name

    try:
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, check=True, shell=True).stdout.strip()
        env = os.environ.copy()
        env["NODE_PATH"] = npm_root
        
        cmd = ["node", script_path, temp_input_path, output_docx]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", env=env, shell=True)
        
        record.communication.documentLink = output_docx
        record.status = CeremonyStatus.document_created
        return record
    except subprocess.CalledProcessError as e:
        print(f"FATAL: Word déroulé generation failed.", file=sys.stderr)
        print(f"STDOUT: {e.stdout}", file=sys.stderr)
        print(f"STDERR: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    finally:
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)
