import os
os.environ["EXTRACTOR_MODEL"] = "gemini-2.5-pro"
os.environ["WRITER_MODEL"] = "gemini-2.5-pro"
os.environ["GOOGLE_API_KEY"] = "mock_key"

import pytest
from fastapi.testclient import TestClient
from ui.app import app, get_canonical_steps
from agents.models import Record, CeremonyStatus, QualityCheck

client = TestClient(app)

import ui.app as ui_app

def test_form_validation_and_rehydration():
    # 1. Start a fresh session with a dummy record to bypass LLM and env vars
    dummy_record = Record()
    dummy_record.caseId = "test-case-123"
    dummy_record.qualityCheck.status = "WARNING"
    ui_app.session_record = dummy_record
    
    # 2. Check the initial messages contain our dataModel and components
    msg_response = client.get("/api/messages")
    assert msg_response.status_code == 200
    messages = msg_response.json()
    
    # Assert dataModel exists
    dataModel = None
    for msg in messages:
        if "updateDataModel" in msg:
            dataModel = msg["updateDataModel"]["value"]
    assert dataModel is not None, "DataModel should be returned in messages"

    # 3. Simulate BLOCKING status
    ui_app.session_record.qualityCheck.status = "BLOCKING"
    
    # Try to validate with BLOCKING
    action_payload = {
        "action": {"name": "validate", "surfaceId": "main"},
        "dataModel": dataModel
    }
    action_response = client.post("/api/action", json=action_payload)
    assert action_response.status_code == 409, "Should reject validation when BLOCKING"
    
    # 4. Fix BLOCKING and edit a field to test rehydration
    ui_app.session_record.qualityCheck.status = "WARNING" # or something else
    
    # Modify dataModel as if edited on the frontend
    # For example, let's say we set the gospel title to "Jean 14, 1-6"
    # Find the step index for gospel
    gospel_idx = -1
    for i, step in enumerate(dataModel["ceremony"]["liturgySteps"]):
        if step["label"] and "Évangile" in step["label"]:
            gospel_idx = i
            break
            
    assert gospel_idx != -1, "Évangile step should have been added by scaffolding"
    dataModel["ceremony"]["liturgySteps"][gospel_idx]["title"] = "Jean 14, 1-6"
    
    # Send the action again
    action_payload["dataModel"] = dataModel
    action_response = client.post("/api/action", json=action_payload)
    assert action_response.status_code == 200
    response_json = action_response.json()
    assert response_json.get("redirect") == "/screen_c"
    
    # Assert the session_record received the modification
    rehydrated_record = ui_app.session_record
    assert rehydrated_record.security.humanValidated == True, "Validation flag should be set"
    assert rehydrated_record.status == CeremonyStatus.ready_for_generation
    assert rehydrated_record.ceremony.liturgySteps[gospel_idx].title == "Jean 14, 1-6", "The modified field should survive rehydration"
    
    print("ALL TESTS PASSED: BDD gates confirmed.")

if __name__ == "__main__":
    test_form_validation_and_rehydration()
