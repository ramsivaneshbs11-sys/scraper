"""
Execution & Evidence Router — V2 Automation Layer.

Endpoints:
  POST /projects/{project_id}/execute                — Run Playwright test suite against target URL
  GET  /projects/{project_id}/runs                   — List all execution runs for a project
  GET  /runs/{run_id}                                — Get full run report with evidence & logs
  GET  /evidence/{evidence_id}/screenshot            — Download / View captured Playwright screenshot
"""

import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.execution.runner import PlaywrightRunnerService

router = APIRouter(tags=["executions"])


class ExecuteSuiteRequest(BaseModel):
    target_url: Optional[str] = "http://localhost:8000/review"
    test_case_ids: Optional[List[str]] = None


@router.post("/projects/{project_id}/execute")
def execute_project_tests(
    project_id: str,
    req: ExecuteSuiteRequest,
    db: Session = Depends(get_db)
):
    """
    Executes all project test cases in Playwright Chromium headless browser.
    Captures screenshots, console messages, and pass/fail evidence.
    """
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    try:
        result = PlaywrightRunnerService.execute_test_suite(
            project_id=project.id,
            target_url=req.target_url,
            test_case_ids=req.test_case_ids,
            db=db
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {e}")


@router.get("/projects/{project_id}/runs")
def list_execution_runs(project_id: str, db: Session = Depends(get_db)):
    """Returns execution history and runs for a project."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    runs = db.query(models.ExecutionRun).filter(
        models.ExecutionRun.project_id == project.id
    ).order_by(models.ExecutionRun.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "target_url": r.target_url,
            "status": r.status,
            "total_tests": r.total_tests,
            "passed_tests": r.passed_tests,
            "failed_tests": r.failed_tests,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run_details(run_id: str, db: Session = Depends(get_db)):
    """Fetches full execution run details including all test case evidence and screenshots."""
    run = db.query(models.ExecutionRun).filter(models.ExecutionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found.")

    evidence = db.query(models.ExecutionEvidence).filter(
        models.ExecutionEvidence.run_id == run.id
    ).all()

    evidence_records = []
    import json
    for ev in evidence:
        tc = db.query(models.TestCase).filter(models.TestCase.id == ev.test_case_id).first()
        steps_telemetry = []
        is_healed = False
        display_logs = ev.logs or ""

        try:
            parsed = json.loads(ev.logs)
            if isinstance(parsed, dict) and "steps" in parsed:
                steps_telemetry = parsed.get("steps", [])
                is_healed = parsed.get("self_healed", False)
                display_logs = "\n".join(parsed.get("console_logs", []))
        except Exception:
            pass

        evidence_records.append({
            "evidence_id": ev.id,
            "test_case_id": ev.test_case_id,
            "test_title": tc.title if tc else ev.test_case_id,
            "priority": tc.priority if tc else "P2",
            "status": ev.status,
            "self_healed": is_healed,
            "duration_ms": ev.duration_ms,
            "has_screenshot": bool(ev.screenshot_path and os.path.exists(ev.screenshot_path)),
            "screenshot_url": f"/evidence/{ev.id}/screenshot" if ev.screenshot_path else None,
            "steps": steps_telemetry,
            "error_message": ev.error_message,
            "logs": display_logs
        })

    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "target_url": run.target_url,
        "status": run.status,
        "total_tests": run.total_tests,
        "passed_tests": run.passed_tests,
        "failed_tests": run.failed_tests,
        "duration_ms": run.duration_ms,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "evidence": evidence_records
    }


@router.get("/evidence/{evidence_id}/screenshot")
def get_evidence_screenshot(evidence_id: str, db: Session = Depends(get_db)):
    """Serves the captured PNG screenshot for visual inspection."""
    evidence = db.query(models.ExecutionEvidence).filter(
        models.ExecutionEvidence.id == evidence_id
    ).first()
    if not evidence or not evidence.screenshot_path or not os.path.exists(evidence.screenshot_path):
        raise HTTPException(status_code=404, detail="Screenshot evidence not found.")

    return FileResponse(evidence.screenshot_path, media_type="image/png")
