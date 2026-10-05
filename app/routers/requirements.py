"""
Requirements & Ambiguity Analysis Router (Day 7).

Endpoints for triggering AI analysis, fetching proposed requirements,
and reviewing ambiguities.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.analyzers import RequirementAnalyzerService

router = APIRouter(tags=["requirements"])


@router.post("/documents/{document_id}/analyze")
def analyze_document_requirements(document_id: str, db: Session = Depends(get_db)):
    """
    Triggers AI Requirement & Ambiguity Analysis (Day 7) on an uploaded document's chunks.
    Validates output against Pydantic schemas and saves to SQLite database.
    """
    try:
        result = RequirementAnalyzerService.analyze_document(document_id, db)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/documents/{document_id}/requirements")
def get_document_requirements(document_id: str, db: Session = Depends(get_db)):
    """Fetch all proposed requirements linked to a document's chunks."""
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get all chunk IDs for this document
    chunks = db.query(models.Chunk).filter(models.Chunk.document_id == document_id).all()
    chunk_ids = {c.chunk_id for c in chunks}

    all_reqs = db.query(models.Requirement).filter(models.Requirement.project_id == doc.project_id).all()
    doc_reqs = [r for r in all_reqs if any(cid in (r.linked_chunk_ids or []) for cid in chunk_ids)]

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "requirements_count": len(doc_reqs),
        "requirements": doc_reqs
    }


@router.get("/documents/{document_id}/ambiguities")
def get_document_ambiguities(document_id: str, db: Session = Depends(get_db)):
    """Fetch all identified ambiguities for the project."""
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    ambiguities = db.query(models.Ambiguity).filter(models.Ambiguity.project_id == doc.project_id).all()
    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "ambiguities_count": len(ambiguities),
        "ambiguities": ambiguities
    }


@router.get("/projects/{project_id}/requirements")
def get_project_requirements(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Fetch all requirements for a project, optionally filtered by status (proposed, approved, rejected)."""
    query = db.query(models.Requirement).filter(models.Requirement.project_id == project_id)
    if status:
        query = query.filter(models.Requirement.status == status)
    reqs = query.all()
    return {
        "project_id": project_id,
        "requirements_count": len(reqs),
        "requirements": reqs
    }


@router.get("/projects/{project_id}/ambiguities")
def get_project_ambiguities(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Fetch all ambiguities for a project, optionally filtered by status (open, resolved)."""
    query = db.query(models.Ambiguity).filter(models.Ambiguity.project_id == project_id)
    if status:
        query = query.filter(models.Ambiguity.status == status)
    ambs = query.all()
    return {
        "project_id": project_id,
        "ambiguities_count": len(ambs),
        "ambiguities": ambs
    }


@router.patch("/requirements/{requirement_id}/approve")
def approve_requirement(
    requirement_id: str,
    reviewer_id: Optional[str] = "u1",
    db: Session = Depends(get_db)
):
    """Admin action: Approve an AI-proposed requirement."""
    req = db.query(models.Requirement).filter(models.Requirement.id == requirement_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    from datetime import datetime
    req.status = "approved"
    req.reviewed_by = reviewer_id
    req.reviewed_at = datetime.utcnow()
    req.rejection_reason = None
    db.commit()
    db.refresh(req)
    return {"status": "success", "message": "Requirement approved", "requirement": req}


@router.patch("/requirements/{requirement_id}/reject")
def reject_requirement(
    requirement_id: str,
    reason: str,
    reviewer_id: Optional[str] = "u1",
    db: Session = Depends(get_db)
):
    """Admin action: Reject an AI-proposed requirement with a reason."""
    req = db.query(models.Requirement).filter(models.Requirement.id == requirement_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    from datetime import datetime
    req.status = "rejected"
    req.reviewed_by = reviewer_id
    req.reviewed_at = datetime.utcnow()
    req.rejection_reason = reason
    db.commit()
    db.refresh(req)
    return {"status": "success", "message": "Requirement rejected", "requirement": req}


@router.patch("/ambiguities/{ambiguity_id}/resolve")
def resolve_ambiguity(
    ambiguity_id: str,
    resolution_note: str,
    db: Session = Depends(get_db)
):
    """Admin action: Mark an ambiguity as resolved with clarification note."""
    amb = db.query(models.Ambiguity).filter(models.Ambiguity.id == ambiguity_id).first()
    if not amb:
        raise HTTPException(status_code=404, detail="Ambiguity not found")

    amb.status = "resolved"
    amb.resolution_note = resolution_note
    db.commit()
    db.refresh(amb)
    return {"status": "success", "message": "Ambiguity resolved", "ambiguity": amb}


@router.post("/projects/{project_id}/requirements/approve-all")
def approve_all_project_requirements(
    project_id: str,
    reviewer_id: Optional[str] = "u1",
    db: Session = Depends(get_db)
):
    """Unified QA action: One-click approve all proposed requirements for a project."""
    from datetime import datetime
    reqs = db.query(models.Requirement).filter(
        models.Requirement.project_id == project_id,
        models.Requirement.status == "proposed"
    ).all()

    for r in reqs:
        r.status = "approved"
        r.reviewed_by = reviewer_id
        r.reviewed_at = datetime.utcnow()

    db.commit()
    return {
        "status": "success",
        "message": f"Approved {len(reqs)} requirements successfully.",
        "approved_count": len(reqs)
    }


@router.patch("/requirements/{requirement_id}/update")
def update_requirement_text(
    requirement_id: str,
    text: str,
    db: Session = Depends(get_db)
):
    """Unified QA action: Directly edit and update requirement text."""
    req = db.query(models.Requirement).filter(models.Requirement.id == requirement_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    req.text = text.strip()
    db.commit()
    db.refresh(req)
    return {"status": "success", "message": "Requirement updated", "requirement": req}


