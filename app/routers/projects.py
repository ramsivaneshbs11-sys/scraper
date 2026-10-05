"""
Projects management router.

Handles:
- POST /projects: Creates a project with an automatically generated UUID.
- GET /projects: Lists all projects.
- GET /projects/{project_id}: Retrieves project details.
"""

import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.api_schemas import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project with an automatically generated UUID."""
    
    # Automatically get or create the default admin user
    default_user = db.query(models.User).first()
    if not default_user:
        default_user = models.User(
            id=str(uuid.uuid4()),
            email="admin@example.com",
            name="Admin User",
            role="admin"
        )
        db.add(default_user)
        db.commit()
        db.refresh(default_user)

    creator_id = default_user.id

    project = models.Project(
        id=str(uuid.uuid4()),  # Automatically generated project ID
        name=payload.name,
        description=payload.description,
        created_by=creator_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectResponse])
@router.get("/", response_model=List[ProjectResponse], include_in_schema=False)
def list_projects(db: Session = Depends(get_db)):
    """List all projects."""
    return db.query(models.Project).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a single project by ID or Name."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    """Delete a project by ID or Name, including all associated documents and disk files."""
    import os
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name == project_id)
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    # Find and delete associated documents & their physical disk files
    docs = db.query(models.Document).filter(models.Document.project_id == project.id).all()
    for doc in docs:
        file_path = os.path.join("storage", f"{doc.id}.{doc.file_type}")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        db.delete(doc)

    db.delete(project)
    db.commit()
    return {
        "status": "success",
        "message": f"Project '{project.name}' ({project.id}) and {len(docs)} document(s) deleted successfully."
    }


@router.post("/{project_id}/reset")
def reset_project_data(project_id: str, db: Session = Depends(get_db)):
    """Wipes all documents, chunks, requirements, ambiguities, and test cases for a fresh start."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    db.query(models.ApiTestCase).filter(models.ApiTestCase.project_id == project.id).delete()
    db.query(models.ApiExecutionRun).filter(models.ApiExecutionRun.project_id == project.id).delete()
    db.query(models.ExecutionRun).filter(models.ExecutionRun.project_id == project.id).delete()
    db.query(models.TestCase).filter(models.TestCase.project_id == project.id).delete()
    db.query(models.Requirement).filter(models.Requirement.project_id == project.id).delete()
    db.query(models.Ambiguity).filter(models.Ambiguity.project_id == project.id).delete()
    db.query(models.Chunk).filter(models.Chunk.project_id == project.id).delete()
    db.query(models.Document).filter(models.Document.project_id == project.id).delete()
    db.commit()

    return {"status": "success", "message": f"Project '{project.name}' reset 100% fresh and clean."}

