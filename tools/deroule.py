import os
import sys
import json
import shutil
import tempfile
import subprocess
from datetime import datetime
from typing import Dict, Any

from agents.models import Record, CeremonyStatus
from agents.liturgy import CONTENT_RUBRICS, norm_label

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
            # Placeholder only for content rubrics (readings, songs, prayer).
            # Fixed liturgical moments (Entrée, Accueil, Alléluia, Notre Père,
            # Homélie, etc.) are legitimately empty — stamping them with
            # "à compléter" would be incorrect.
            label_norm = norm_label(step.label or "")
            content_norms = {norm_label(c) for c in CONTENT_RUBRICS}
            if label_norm in content_norms:
                etape["sub"] = "à compléter"
            
        etapes.append(etape)
        
    skill_input = {
        "defunt": defunt_str,
        "eglise": eglise_str,
        "celebrant": record.ceremony.celebrant or "",
        "etapes": etapes,
        "prochaineMesse": record.ceremony.nextMass or ""
    }

    # 2. Resolve Node.js executable portably (works on Windows, Linux, macOS)
    node_bin = shutil.which("node")
    if not node_bin:
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
        # shell=False: safe on all platforms; no argument-dropping on Linux.
        # stdin=DEVNULL: prevents node from hanging waiting on stdin if script
        #   path is wrong or missing.
        # timeout=60s: belt-and-suspenders against runaway processes.
        # Node resolves require('docx') by walking up from the script to the
        # repo-root node_modules — no NODE_PATH manipulation needed.
        cmd = [node_bin, script_path, temp_input_path, output_docx]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
            timeout=60,
            shell=False,
        )
        
        record.communication.documentLink = output_docx
        record.status = CeremonyStatus.document_created
        return record
    except subprocess.TimeoutExpired:
        print("FATAL: Word déroulé generation timed out after 60s.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"FATAL: Word déroulé generation failed.", file=sys.stderr)
        print(f"STDOUT: {e.stdout}", file=sys.stderr)
        print(f"STDERR: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    finally:
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)

