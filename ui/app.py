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
    
    # Pre-fill canonical liturgy steps if missing
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
    
    messages = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "main",
                "catalogId": "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
            }
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "main",
                "value": record_dict
            }
        }
    ]
    
    components = []
    def add_c(comp):
        components.append(comp)
        return comp["id"]
        
    root_children = []
    
    # Status Banner
    status = session_record.qualityCheck.status
    if status == "BLOCKING":
        root_children.append(add_c({
            "id": "banner_blocking", "component": "Card", "child": "banner_txt_blocking"
        }))
        add_c({"id": "banner_txt_blocking", "component": "Text", "text": "BLOQUANT: Veuillez vérifier les incohérences ou champs manquants."})
    elif status == "WARNING":
        root_children.append(add_c({
            "id": "banner_warning", "component": "Card", "child": "banner_txt_warning"
        }))
        add_c({"id": "banner_txt_warning", "component": "Text", "text": "ATTENTION: Des points nécessitent votre vérification."})

    # Section 1: Informations générales
    col1_children = []
    col1_children.append(add_c({"id": "tf_fn", "component": "TextField", "label": "Prénom du défunt", "value": {"path": "/deceased/firstName"}}))
    col1_children.append(add_c({"id": "tf_ln", "component": "TextField", "label": "Nom du défunt", "value": {"path": "/deceased/lastName"}}))
    col1_children.append(add_c({"id": "tf_date", "component": "TextField", "label": "Date", "value": {"path": "/ceremony/date"}}))
    col1_children.append(add_c({"id": "tf_time", "component": "TextField", "label": "Heure", "value": {"path": "/ceremony/time"}}))
    col1_children.append(add_c({"id": "tf_church", "component": "TextField", "label": "Église", "value": {"path": "/ceremony/church"}}))
    col1_children.append(add_c({"id": "tf_cele", "component": "TextField", "label": "Célébrant", "value": {"path": "/ceremony/celebrant"}}))
    add_c({"id": "col1", "component": "Column", "children": col1_children})
    root_children.append(add_c({"id": "card1", "component": "Card", "child": "col1"}))
    
    # Section 2: Famille & contacts
    col2_children = []
    col2_children.append(add_c({"id": "tf_cname", "component": "TextField", "label": "Contact principal", "value": {"path": "/participants/mainFamilyContact/name"}}))
    col2_children.append(add_c({"id": "tf_crel", "component": "TextField", "label": "Lien de parenté", "value": {"path": "/participants/mainFamilyContact/relationship"}}))
    col2_children.append(add_c({"id": "tf_cphone", "component": "TextField", "label": "Téléphone", "value": {"path": "/participants/mainFamilyContact/phone"}}))
    col2_children.append(add_c({"id": "tf_cemail", "component": "TextField", "label": "Email", "value": {"path": "/participants/mainFamilyContact/email"}}))
    add_c({"id": "col2", "component": "Column", "children": col2_children})
    root_children.append(add_c({"id": "card2", "component": "Card", "child": "col2"}))
    
    # Section 3: Profil & vie
    col3_children = []
    # Simplified to TextFields for MVP instead of dynamic chips for now
    col3_children.append(add_c({"id": "tf_life", "component": "TextField", "label": "Éléments de vie", "value": {"path": "/deceased/lifeElements/0"}}))
    col3_children.append(add_c({"id": "tf_traits", "component": "TextField", "label": "Traits de caractère", "value": {"path": "/deceased/personalityTraits/0"}}))
    add_c({"id": "col3", "component": "Column", "children": col3_children})
    root_children.append(add_c({"id": "card3", "component": "Card", "child": "col3"}))

    # Section 4: Déroulé
    col4_children = []
    for i, step in enumerate(session_record.ceremony.liturgySteps):
        row_id = f"step_row_{i}"
        tf_lbl_id = f"tf_step_lbl_{i}"
        tf_ref_id = f"tf_step_ref_{i}"
        tf_tit_id = f"tf_step_tit_{i}"
        
        col4_children.append(add_c({"id": tf_lbl_id, "component": "TextField", "label": f"Étape {i+1} - Rôle", "value": {"path": f"/ceremony/liturgySteps/{i}/label"}}))
        col4_children.append(add_c({"id": tf_ref_id, "component": "TextField", "label": "Référence", "value": {"path": f"/ceremony/liturgySteps/{i}/reference"}}))
        col4_children.append(add_c({"id": tf_tit_id, "component": "TextField", "label": "Titre", "value": {"path": f"/ceremony/liturgySteps/{i}/title"}}))
        
    if not col4_children:
        col4_children.append(add_c({"id": "no_deroule", "component": "Text", "text": "Aucune note repérée."}))
        
    add_c({"id": "col4", "component": "Column", "children": col4_children})
    root_children.append(add_c({"id": "card4", "component": "Card", "child": "col4"}))
    
    # Section 5: Prière universelle
    col5_children = []
    col5_children.append(add_c({"id": "tf_pu", "component": "TextField", "label": "Intentions", "value": {"path": "/ceremony/universalPrayerIntentions/0"}}))
    add_c({"id": "col5", "component": "Column", "children": col5_children})
    root_children.append(add_c({"id": "card5", "component": "Card", "child": "col5"}))

    # Points à vérifier (readonly)
    col6_children = []
    needs_review = session_record.extraction.needsHumanReview
    missing = session_record.extraction.missingFields
    contras = session_record.extraction.contradictions
    
    if needs_review:
        col6_children.append(add_c({"id": "txt_nr", "component": "Text", "text": f"À vérifier : {', '.join(needs_review)}"}))
    if missing:
        col6_children.append(add_c({"id": "txt_mi", "component": "Text", "text": f"Manquants : {', '.join(missing)}"}))
    if contras:
        col6_children.append(add_c({"id": "txt_co", "component": "Text", "text": f"Contradictions : {len(contras)} repérées"}))
        
    if not col6_children:
         col6_children.append(add_c({"id": "txt_all_good", "component": "Text", "text": "Aucun point à vérifier."}))
         
    add_c({"id": "col6", "component": "Column", "children": col6_children})
    root_children.append(add_c({"id": "card6", "component": "Card", "child": "col6"}))

    # avoidMentioning (highlighted)
    if session_record.deceased.avoidMentioning:
        col7_children = []
        for i, avoid in enumerate(session_record.deceased.avoidMentioning):
             col7_children.append(add_c({"id": f"tf_avoid_{i}", "component": "TextField", "label": "À éviter", "value": {"path": f"/deceased/avoidMentioning/{i}"}}))
        add_c({"id": "col7", "component": "Column", "children": col7_children})
        root_children.append(add_c({"id": "card7", "component": "Card", "child": "col7"}))


    # Valider button
    add_c({"id": "btn_valider_label", "component": "Text", "text": "Valider le dossier"})
    btn_variant = "primary"
    
    # Passing disabled prop for the Button if A2UI supports it (fallback to client-side JS otherwise)
    btn_props = {
        "id": "btn_valider", 
        "component": "Button", 
        "child": "btn_valider_label", 
        "variant": btn_variant, 
        "action": {"event": {"name": "validate"}}
    }
    # For A2UI Basic Button, we might need to set disabled in the dataModel, or we just rely on the server 409
    
    add_c(btn_props)
    
    root_children.append("btn_valider")
    
    add_c({"id": "root", "component": "Column", "children": root_children})
    
    messages.append({
        "version": "v0.9",
        "updateComponents": {
            "surfaceId": "main",
            "components": components
        }
    })
    
    return messages

def background_generation(record: Record):
    global session_record
    try:
        session_record = run_after_validation(record)
    except Exception as e:
        logger.error(f"Generation failed: {e}")

@app.post("/api/action")
async def post_action(request: Request, background_tasks: BackgroundTasks):
    global session_record
    payload = await request.json()
    action = payload.get("action", {})
    dataModel = payload.get("dataModel", {})
    
    if action.get("name") == "validate":
        # 1. Enforce BLOCKING check
        if session_record.qualityCheck.status == "BLOCKING":
            raise HTTPException(status_code=409, detail="Cannot validate: Record is BLOCKING.")
        
        # 2. Safely rehydrate Record
        try:
            # We reconstruct a NEW Record object from the incoming dataModel
            new_record = Record(**dataModel)
            
            # PRESERVE non-editable system fields from session_record
            new_record.extraction = session_record.extraction
            new_record.qualityCheck = session_record.qualityCheck
            new_record.caseId = session_record.caseId
            new_record.security.humanValidated = True
            new_record.status = CeremonyStatus.ready_for_generation
            
            # Drop empty liturgy steps
            valid_steps = [s for s in new_record.ceremony.liturgySteps if s.label or s.reference or s.title]
            new_record.ceremony.liturgySteps = valid_steps
            
            session_record = new_record
            
            # 3. Spawn run_after_validation
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

@app.get("/api/download_deroule")
async def download_deroule():
    from fastapi.responses import FileResponse
    import glob
    # Look for any docx in the examples/jeanne_martin directory (or current dir)
    files = glob.glob(f"examples/*_deroule.docx")
    if files:
        files.sort(key=os.path.getctime, reverse=True)
        return FileResponse(files[0], filename="deroule.docx")
    return {"error": "File not found"}

if __name__ == "__main__":
    logger.info("Starting A2UI UI on http://localhost:8002")
    uvicorn.run(app, host="0.0.0.0", port=8002)
