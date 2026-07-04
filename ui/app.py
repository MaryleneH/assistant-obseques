import os
import sys
from utils.env import load_environment
load_environment()

from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import logging
import asyncio

from agents.models import Record, CeremonyStatus, LiturgyStep
from agents.orchestrator import run_until_review, run_after_validation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ui.app")

app = FastAPI()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    # Return a generic French error to prevent traceback leaks
    return HTMLResponse(
        status_code=500,
        content="<html><body><h1>Une erreur interne s'est produite.</h1><p>Veuillez réessayer plus tard.</p></body></html>"
    )

app.mount("/static", StaticFiles(directory="ui/static"), name="static")
templates = Jinja2Templates(directory="ui/templates")

# Global state for MVP
session_record: Record = None
session_task = None

def get_canonical_steps():
    return [
        {"label": "Chant d'entrée", "reference": "", "title": ""},
        {"label": "1ère Lecture", "reference": "", "title": ""},
        {"label": "Psaume", "reference": "", "title": ""},
        {"label": "Évangile", "reference": "", "title": ""},
        {"label": "Prière Universelle", "reference": "", "title": ""},
        {"label": "Chant d'Adieu", "reference": "", "title": ""}
    ]

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return HTMLResponse(templates.get_template("screen_a.html").render({"request": request}))

@app.get("/api/example")
async def get_example():
    try:
        with open("examples/jeanne_martin/notes.md", "r", encoding="utf-8") as f:
            return {"notes": f.read()}
    except Exception as e:
        return {"notes": ""}

from typing import List, Optional
from fastapi import File, UploadFile
from PIL import Image, ImageOps

@app.post("/extract")
async def post_extract(request: Request, notes: Optional[str] = Form(""), photos: List[UploadFile] = File(None)):
    global session_record
    
    contents = []
    if photos:
        for photo in photos:
            if photo.filename:
                if not photo.content_type.startswith("image/"):
                    raise HTTPException(status_code=400, detail="Veuillez n'envoyer que des images (JPEG, PNG).")
                
                try:
                    img = Image.open(photo.file)
                    img = ImageOps.exif_transpose(img)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    max_size = 1600
                    if max(img.width, img.height) > max_size:
                        ratio = max_size / max(img.width, img.height)
                        new_size = (int(img.width * ratio), int(img.height * ratio))
                        img = img.resize(new_size, Image.Resampling.LANCZOS)
                    contents.append(img)
                except Exception as e:
                    logger.error(f"Image processing error: {e}")
                    raise HTTPException(status_code=400, detail="Fichier image invalide ou corrompu.")
    
    if not contents and notes:
        contents = [notes]
    
    # Run orchestration phase 1
    session_record = run_until_review(contents)
    return RedirectResponse(url="/screen_b", status_code=303)

@app.get("/screen_b", response_class=HTMLResponse)
async def get_screen_b(request: Request):
    if not session_record:
        return RedirectResponse(url="/")
    return HTMLResponse(templates.get_template("screen_b.html").render({"request": request}))

@app.get("/api/messages")
async def get_messages():
    if not session_record:
        return []
    
    existing_labels = [s.label.lower() for s in session_record.ceremony.liturgySteps if s.label]
    for cstep in get_canonical_steps():
        if cstep["label"].lower() not in existing_labels:
            cstep["title"] = "À compléter"
            session_record.ceremony.liturgySteps.append(LiturgyStep(**cstep))
            
    if not session_record.deceased.lifeElements:
        session_record.deceased.lifeElements = [""]
    if not session_record.deceased.personalityTraits:
        session_record.deceased.personalityTraits = [""]
    if not session_record.ceremony.universalPrayerIntentions:
        session_record.ceremony.universalPrayerIntentions = [""]
        
    record_dict = session_record.model_dump()
    
    messages = []
    
    def add_surface(surface_id, root_children, components_list):
        components_list.append({"id": "root", "component": "Column", "children": root_children})
        messages.append({
            "version": "v0.9",
            "createSurface": {
                "surfaceId": surface_id,
                "catalogId": "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json",
                "sendDataModel": True
            }
        })
        messages.append({
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": surface_id,
                "value": record_dict
            }
        })
        messages.append({
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": surface_id,
                "components": components_list
            }
        })
    
    # 1. info_generales
    c_info = []
    def add_info(c): c_info.append(c); return c["id"]
    
    r1 = []
    r1.append(add_info({"id": "tf_fn", "component": "TextField", "label": "Prénom", "value": {"path": "/deceased/firstName"}}))
    r1.append(add_info({"id": "tf_ln", "component": "TextField", "label": "Nom", "value": {"path": "/deceased/lastName"}}))
    add_info({"id": "row_name", "component": "Row", "children": r1})
    
    r2 = []
    r2.append(add_info({"id": "tf_date", "component": "TextField", "label": "Date", "value": {"path": "/ceremony/date"}}))
    r2.append(add_info({"id": "tf_time", "component": "TextField", "label": "Heure", "value": {"path": "/ceremony/time"}}))
    add_info({"id": "row_datetime", "component": "Row", "children": r2})
    
    r3 = []
    r3.append(add_info({"id": "tf_church", "component": "TextField", "label": "Église", "value": {"path": "/ceremony/church"}}))
    r3.append(add_info({"id": "tf_cele", "component": "TextField", "label": "Célébrant", "value": {"path": "/ceremony/celebrant"}}))
    add_info({"id": "row_place", "component": "Row", "children": r3})
    
    add_surface("info_generales", ["row_name", "row_datetime", "row_place"], c_info)
    
    # 2. famille_contacts
    c_fam = []
    def add_fam(c): c_fam.append(c); return c["id"]
    
    add_fam({"id": "tf_cname", "component": "TextField", "label": "Contact principal", "value": {"path": "/participants/mainFamilyContact/name"}})
    add_fam({"id": "tf_crel", "component": "TextField", "label": "Lien de parenté", "value": {"path": "/participants/mainFamilyContact/relationship"}})
    r4 = []
    r4.append(add_fam({"id": "tf_cphone", "component": "TextField", "label": "Téléphone", "value": {"path": "/participants/mainFamilyContact/phone"}}))
    r4.append(add_fam({"id": "tf_cemail", "component": "TextField", "label": "Email", "value": {"path": "/participants/mainFamilyContact/email"}}))
    add_fam({"id": "row_contact", "component": "Row", "children": r4})
    
    add_surface("famille_contacts", ["tf_cname", "tf_crel", "row_contact"], c_fam)
    
    # 3. profil_vie
    c_prof = []
    def add_prof(c): c_prof.append(c); return c["id"]
    add_prof({"id": "tf_life", "component": "TextField", "label": "Éléments de vie", "value": {"path": "/deceased/lifeElements/0"}})
    add_prof({"id": "tf_traits", "component": "TextField", "label": "Traits de caractère", "value": {"path": "/deceased/personalityTraits/0"}})
    add_surface("profil_vie", ["tf_life", "tf_traits"], c_prof)
    
    # 4. deroule
    c_der = []
    def add_der(c): c_der.append(c); return c["id"]
    der_children = []
    for i, step in enumerate(session_record.ceremony.liturgySteps):
        r_id = f"row_step_{i}"
        lbl_id = f"tf_step_lbl_{i}"
        ref_id = f"tf_step_ref_{i}"
        tit_id = f"tf_step_tit_{i}"
        
        row_children = []
        row_children.append(add_der({"id": lbl_id, "component": "TextField", "label": "Étape", "value": {"path": f"/ceremony/liturgySteps/{i}/label"}}))
        row_children.append(add_der({"id": ref_id, "component": "TextField", "label": "Référence", "value": {"path": f"/ceremony/liturgySteps/{i}/reference"}}))
        row_children.append(add_der({"id": tit_id, "component": "TextField", "label": "Titre", "value": {"path": f"/ceremony/liturgySteps/{i}/title"}}))
        
        add_der({"id": r_id, "component": "Row", "children": row_children})
        der_children.append(r_id)
        
    add_surface("deroule", der_children, c_der)
    
    # 5. priere
    c_pri = []
    def add_pri(c): c_pri.append(c); return c["id"]
    add_pri({"id": "tf_pu", "component": "TextField", "label": "Intentions", "value": {"path": "/ceremony/universalPrayerIntentions/0"}})
    add_surface("priere", ["tf_pu"], c_pri)
    
    # 6. points_verif
    c_verif = []
    def add_verif(c): c_verif.append(c); return c["id"]
    verif_children = []
    
    needs_review = session_record.extraction.needsHumanReview
    missing = session_record.extraction.missingFields
    contras = session_record.extraction.contradictions
    
    if needs_review:
        add_verif({"id": "txt_nr_hdr", "component": "Text", "text": "À vérifier :"})
        verif_children.append("txt_nr_hdr")
        for i, item in enumerate(needs_review):
            add_verif({"id": f"txt_nr_{i}", "component": "Text", "text": f"• {item}"})
            verif_children.append(f"txt_nr_{i}")
            
    if missing:
        add_verif({"id": "txt_mi_hdr", "component": "Text", "text": "Champs manquants :"})
        verif_children.append("txt_mi_hdr")
        for i, item in enumerate(missing):
            add_verif({"id": f"txt_mi_{i}", "component": "Text", "text": f"• {item}"})
            verif_children.append(f"txt_mi_{i}")
            
    if contras:
        add_verif({"id": "txt_co_hdr", "component": "Text", "text": "Contradictions repérées :"})
        verif_children.append("txt_co_hdr")
        for i, item in enumerate(contras):
             add_verif({"id": f"txt_co_{i}", "component": "Text", "text": f"• {item}"})
             verif_children.append(f"txt_co_{i}")
             
    if not verif_children:
        add_verif({"id": "txt_all_good", "component": "Text", "text": "Aucun point à vérifier."})
        verif_children.append("txt_all_good")
        
    add_surface("points_verif", verif_children, c_verif)
    
    # 7. questions
    c_quest = []
    def add_quest(c): c_quest.append(c); return c["id"]
    quest_children = []
    sug = session_record.qualityCheck.suggestedQuestions
    if sug:
        for i, item in enumerate(sug):
            add_quest({"id": f"txt_qu_{i}", "component": "Text", "text": f"• {item}"})
            quest_children.append(f"txt_qu_{i}")
    if not quest_children:
        add_quest({"id": "txt_no_qu", "component": "Text", "text": "Aucune question suggérée."})
        quest_children.append("txt_no_qu")
    add_surface("questions", quest_children, c_quest)
    
    # 8. avoid_mentioning
    c_avoid = []
    def add_avoid(c): c_avoid.append(c); return c["id"]
    avoid_children = []
    avoid_list = session_record.deceased.avoidMentioning
    if avoid_list:
        for i, item in enumerate(avoid_list):
            add_avoid({"id": f"tf_avoid_{i}", "component": "TextField", "label": "À éviter", "value": {"path": f"/deceased/avoidMentioning/{i}"}})
            avoid_children.append(f"tf_avoid_{i}")
    if not avoid_children:
        add_avoid({"id": "txt_no_avoid", "component": "Text", "text": "Aucune restriction."})
        avoid_children.append("txt_no_avoid")
    add_surface("avoid_mentioning", avoid_children, c_avoid)
    
    # 9. actions
    c_act = []
    def add_act(c): c_act.append(c); return c["id"]
    add_act({"id": "btn_valider_label", "component": "Text", "text": "✓ Valider le dossier"})
    btn_variant = "primary"
    status = session_record.qualityCheck.status
    add_act({
        "id": "btn_valider", 
        "component": "Button", 
        "child": "btn_valider_label", 
        "variant": btn_variant, 
        "disabled": (status == "BLOCKING"),
        "action": {"event": {"name": "validate"}}
    })
    
    status = session_record.qualityCheck.status
    if status == "BLOCKING":
        add_act({"id": "err_blocking", "component": "Text", "text": "BLOQUANT: Veuillez corriger les incohérences avant de valider."})
        add_surface("actions", ["err_blocking", "btn_valider"], c_act)
    else:
        add_surface("actions", ["btn_valider"], c_act)

    return messages

def background_generation(record: Record):
    global session_record
    try:
        logger.info(f"background_generation: starting, record.status={record.status}")
        result = run_after_validation(record)
        logger.info(f"background_generation: completed, result.status={result.status}, docLink={result.communication.documentLink}")
        session_record = result
    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)

def extract_diffs(original, updated):
    diff = {}
    for k, v in updated.items():
        if k not in original:
            diff[k] = v
        elif isinstance(v, dict) and isinstance(original[k], dict):
            sub_diff = extract_diffs(original[k], v)
            if sub_diff:
                diff[k] = sub_diff
        elif isinstance(v, list) and isinstance(original[k], list):
            # For lists, if they are identical, skip. If they differ, take the new list entirely.
            if v != original[k]:
                diff[k] = v
        elif v != original[k]:
            diff[k] = v
    return diff

def apply_diffs(target, diff):
    for k, v in diff.items():
        if isinstance(v, dict) and k in target and isinstance(target[k], dict):
            apply_diffs(target[k], v)
        else:
            target[k] = v

@app.post("/api/action")
async def post_action(request: Request, background_tasks: BackgroundTasks):
    global session_record
    payload = await request.json()
    action = payload.get("action", {})
    
    if action.get("name") == "validate":
        if session_record.qualityCheck.status == "BLOCKING":
            raise HTTPException(status_code=409, detail="Cannot validate: Record is BLOCKING.")
        
        try:
            data_model_wrapper = payload.get("dataModel", {})
            surfaces = data_model_wrapper.get("surfaces", {}) if data_model_wrapper.get("version") == "v0.9" else {}
            
            original_dict = session_record.model_dump()
            final_dict = original_dict.copy()
            
            for surface_id, surface_data in surfaces.items():
                diffs = extract_diffs(original_dict, surface_data)
                apply_diffs(final_dict, diffs)
            
            new_record = Record(**final_dict)
            new_record.extraction = session_record.extraction
            new_record.qualityCheck = session_record.qualityCheck
            new_record.caseId = session_record.caseId
            new_record.security.humanValidated = True
            new_record.status = CeremonyStatus.ready_for_generation
            
            valid_steps = [s for s in new_record.ceremony.liturgySteps if s.label or s.reference or s.title]
            new_record.ceremony.liturgySteps = valid_steps
            
            session_record = new_record
            background_tasks.add_task(background_generation, session_record)
            
            return {"redirect": "/screen_c"}
            
        except Exception as e:
            logger.error(f"Rehydration failed: {e}")
            raise HTTPException(status_code=400, detail="Data validation failed.")

    return {"status": "ignored"}

@app.get("/screen_c", response_class=HTMLResponse)
async def get_screen_c(request: Request):
    if not session_record:
        return RedirectResponse(url="/")
    
    context = {
        "request": request,
        "status": session_record.status.value,
        "deceased_name": f"{session_record.deceased.firstName} {session_record.deceased.lastName}".strip()
    }
    return HTMLResponse(templates.get_template("screen_c.html").render(context))

from fastapi.responses import FileResponse
from pathlib import Path

@app.get("/api/download_deroule")
async def download_deroule():
    if not session_record:
        return JSONResponse(status_code=404, content={"error": "Fichier introuvable"})
        
    # Allow download once generation pipeline has completed (document_created or later)
    terminal_states = {
        CeremonyStatus.document_created,
        CeremonyStatus.email_draft_created,
        CeremonyStatus.validated,
        CeremonyStatus.archived,
    }
    if session_record.status not in terminal_states:
        return JSONResponse(status_code=202, content={"error": "Génération en cours…"})
        
    doc_link = session_record.communication.documentLink
    if not doc_link:
         return JSONResponse(status_code=404, content={"error": "Fichier introuvable"})
    
    try:
        # Resolve absolute path
        base_dir = Path(__file__).resolve().parent.parent
        # Prevent traversal manually if needed, but doc_link comes from backend
        file_path = (base_dir / doc_link).resolve()
        
        if not str(file_path).startswith(str(base_dir)):
             return JSONResponse(status_code=403, content={"error": "Accès refusé"})
             
        if not file_path.exists():
             logger.error(f"Download requested but file missing: {file_path}")
             return JSONResponse(status_code=404, content={"error": "Fichier introuvable"})
             
        return FileResponse(
            path=file_path, 
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
            filename=f"deroule_{session_record.caseId}.docx"
        )
    except Exception as e:
        logger.error(f"Download error: {e}")
        return JSONResponse(status_code=500, content={"error": "Erreur serveur"})

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erreur serveur inattendue: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Une erreur inattendue s'est produite. Veuillez réessayer."}
    )

if __name__ == "__main__":
    logger.info("Starting A2UI UI on http://localhost:8002")
    uvicorn.run(app, host="0.0.0.0", port=8002)
