"""
Record & Playback Automation Router — V2 Architecture.

Endpoints:
  POST /recorder/playback                       — Execute recorded action sequence with live headless Playwright
  POST /projects/{project_id}/recorder/save     — Save recorded action sequence as a Project Test Case
  POST /recorder/launch-codegen                 — Launch live headful Playwright Codegen browser
  POST /recorder/stop-codegen                   — Stop Codegen session and import generated actions
  POST /projects/{project_id}/recorder/import   — Import raw Playwright Python script as a Test Case
  GET  /recorder/evidence/{session_id}/screenshot — View Playback screenshot evidence
"""

import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.execution.recorder import RecorderService, EVIDENCE_DIR

router = APIRouter(prefix="/recorder", tags=["record-and-playback"])


class ActionItem(BaseModel):
    type: str  # NAVIGATE | CLICK | FILL | ASSERT_VISIBLE | ASSERT_TEXT | SCREENSHOT
    selector: Optional[str] = ""
    value: Optional[str] = ""


class PlaybackRequest(BaseModel):
    target_url: str = "http://localhost:8000/review"
    actions: List[ActionItem] = []
    project_id: Optional[str] = None


class SaveRecordedTestCaseRequest(BaseModel):
    title: str = "User Flow Recording"
    target_url: str = "http://localhost:8000/review"
    actions: List[ActionItem] = []
    expected_result: Optional[str] = None


class CodegenLaunchRequest(BaseModel):
    target_url: str = "http://localhost:8000/review"


class CodegenStopRequest(BaseModel):
    session_id: str
    project_id: Optional[str] = None


class ImportScriptRequest(BaseModel):
    title: str = "Imported Playwright Script"
    target_url: str = "http://localhost:8000/review"
    script_code: str


@router.post("/playback")
def execute_playback(req: PlaybackRequest):
    """
    Executes recorded actions in headless Chromium with self-healing locators.
    Returns step telemetry and screenshot evidence.
    """
    try:
        actions_dict = [a.model_dump() for a in req.actions]
        result = RecorderService.execute_playback(
            target_url=req.target_url,
            actions=actions_dict,
            project_id=req.project_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Playback execution failed: {str(e)}")


@router.post("/projects/{project_id}/save")
def save_recorded_test(
    project_id: str,
    req: SaveRecordedTestCaseRequest,
    db: Session = Depends(get_db)
):
    """
    Converts recorded user actions into a standardized TestCase with Gherkin steps
    and persists it in SQLite under the given project.
    """
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    actions_dict = [a.model_dump() for a in req.actions]
    tc = RecorderService.save_as_test_case(
        project_id=project.id,
        title=req.title,
        target_url=req.target_url,
        actions=actions_dict,
        expected_result=req.expected_result,
        db=db
    )

    return {
        "status": "success",
        "message": f"Recorded test case '{tc.id}' created successfully!",
        "test_case": {
            "id": tc.id,
            "project_id": tc.project_id,
            "title": tc.title,
            "steps": tc.steps,
            "expected_result": tc.expected_result,
            "priority": tc.priority,
            "status": tc.status
        }
    }


@router.post("/launch-codegen")
def launch_codegen(req: CodegenLaunchRequest):
    """
    Spawns Playwright Codegen recorder window on target URL.
    """
    try:
        return RecorderService.launch_codegen(target_url=req.target_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch Codegen: {str(e)}")


@router.post("/stop-codegen")
def stop_codegen(req: CodegenStopRequest, db: Session = Depends(get_db)):
    """
    Terminates active Codegen session and imports recorded script.
    """
    try:
        return RecorderService.stop_codegen(
            session_id=req.session_id,
            project_id=req.project_id,
            db=db
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop Codegen: {str(e)}")


@router.post("/projects/{project_id}/import-script")
def import_playwright_script(
    project_id: str,
    req: ImportScriptRequest,
    db: Session = Depends(get_db)
):
    """
    Parses pasted Playwright Python script, extracts actions,
    and registers it as a standard TestCase.
    """
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    actions = RecorderService.parse_playwright_python_code(req.script_code)
    if not actions:
        # Default fallback action
        actions = [{"type": "NAVIGATE", "value": req.target_url, "selector": ""}]

    tc = RecorderService.save_as_test_case(
        project_id=project.id,
        title=req.title,
        target_url=req.target_url,
        actions=actions,
        expected_result="Custom Playwright script executes cleanly without assertion errors.",
        db=db
    )

    return {
        "status": "success",
        "message": f"Imported {len(actions)} actions into new test case {tc.id}!",
        "test_case": {
            "id": tc.id,
            "title": tc.title,
            "steps": tc.steps,
            "expected_result": tc.expected_result
        }
    }


@router.get("/evidence/{session_id}/screenshot")
def get_playback_screenshot(session_id: str):
    """Returns captured screenshot evidence for the playback session."""
    filepath = os.path.join(EVIDENCE_DIR, f"{session_id}.png")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Screenshot evidence not found.")
    return FileResponse(filepath, media_type="image/png")
