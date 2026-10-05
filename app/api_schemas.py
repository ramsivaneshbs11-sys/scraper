"""
API-facing Pydantic schemas (request/response shapes for FastAPI endpoints).

These are distinct from app/models.py (the SQLAlchemy DB tables) - this file
defines what the API accepts and returns over HTTP.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    project_id: str
    filename: str
    file_type: str
    uploaded_by: str
    uploaded_at: datetime
    status: str

    class Config:
        from_attributes = True  # lets this be built directly from a SQLAlchemy row


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True
