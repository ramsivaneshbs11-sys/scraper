"""
API Testing Router — Automated REST API Verification (Swagger / OpenAPI).

Endpoints:
  POST /projects/{project_id}/api/import-spec        — Import OpenAPI spec & generate tests
  POST /projects/{project_id}/api/execute            — Execute API tests against target base URL
  GET  /projects/{project_id}/api/test-cases         — List generated API test cases
  GET  /projects/{project_id}/api/runs               — List API execution runs & latency reports
  GET  /projects/{project_id}/api/export/postman     — Download Postman Collection v2.1.0
"""

import io
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import httpx

from app.database import get_db
from app import models
from app.execution.api_engine import ApiTestingEngine

router = APIRouter(tags=["api-testing"])


class ImportSpecRequest(BaseModel):
    spec_url: Optional[str] = None
    spec_json: Optional[Dict[str, Any]] = None


class ExecuteApiRequest(BaseModel):
    base_url: Optional[str] = "http://localhost:8000"
    test_case_ids: Optional[List[str]] = None


@router.post("/projects/{project_id}/api/import-spec")
def import_openapi_spec(
    project_id: str,
    req: ImportSpecRequest,
    db: Session = Depends(get_db)
):
    """Imports an OpenAPI/Swagger spec and generates Positive, Negative, and Security test cases."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    spec = req.spec_json
    if not spec and req.spec_url:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(req.spec_url)
                if res.status_code == 200:
                    spec = res.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch OpenAPI spec from {req.spec_url}: {e}")

    # Fallback to local FastAPI spec if none provided
    if not spec:
        from app.main import app
        spec = app.openapi()

    generated_cases = ApiTestingEngine.parse_and_generate_tests(
        spec=spec,
        project_id=project.id,
        db=db
    )

    return {
        "status": "success",
        "project_id": project.id,
        "total_endpoints": len(spec.get("paths", {})),
        "total_test_cases_generated": len(generated_cases),
        "breakdown": {
            "positive": sum(1 for c in generated_cases if c.test_type == "POSITIVE"),
            "negative": sum(1 for c in generated_cases if c.test_type == "NEGATIVE"),
            "security": sum(1 for c in generated_cases if c.test_type == "SECURITY")
        }
    }


@router.post("/projects/{project_id}/api/execute")
def execute_api_suite(
    project_id: str,
    req: ExecuteApiRequest,
    db: Session = Depends(get_db)
):
    """Executes all API tests against base_url, calculating latency and assertion status."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    try:
        results = ApiTestingEngine.execute_api_suite(
            project_id=project.id,
            base_url=req.base_url,
            test_case_ids=req.test_case_ids,
            db=db
        )
        return results
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API execution error: {e}")


@router.get("/projects/{project_id}/api/test-cases")
def list_api_test_cases(project_id: str, db: Session = Depends(get_db)):
    """Returns all generated API test cases for a project."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    cases = db.query(models.ApiTestCase).filter(
        models.ApiTestCase.project_id == project.id
    ).all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "method": c.method,
            "endpoint": c.endpoint,
            "test_type": c.test_type,
            "expected_status": c.expected_status,
            "body": c.body,
            "query_params": c.query_params
        }
        for c in cases
    ]


@router.get("/projects/{project_id}/api/runs")
def list_api_runs(project_id: str, db: Session = Depends(get_db)):
    """Returns execution run history for API tests."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    runs = db.query(models.ApiExecutionRun).filter(
        models.ApiExecutionRun.project_id == project.id
    ).order_by(models.ApiExecutionRun.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "base_url": r.base_url,
            "total_requests": r.total_requests,
            "passed_requests": r.passed_requests,
            "failed_requests": r.failed_requests,
            "avg_latency_ms": r.avg_latency_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "results": r.results
        }
        for r in runs
    ]


@router.get("/projects/{project_id}/api/export/postman")
def export_postman(project_id: str, base_url: str = Query("http://localhost:8000"), db: Session = Depends(get_db)):
    """Exports test cases as standard Postman Collection v2.1.0."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    collection = ApiTestingEngine.export_postman_collection(
        project_id=project.id,
        base_url=base_url,
        db=db
    )

    content = json.dumps(collection, indent=2)
    filename = f"{project.name.replace(' ', '_').lower()}_postman_collection.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
