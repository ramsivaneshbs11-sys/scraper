"""
SQLAlchemy ORM models — defines what actually gets stored in the database.

These mirror the Pydantic schemas from Day 2 (schemas.py), but are a
separate set of classes: Pydantic validates API request/response data,
SQLAlchemy defines the database tables. They look similar on purpose,
but serve different jobs.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "admin" | "tester"
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    uploaded_by = Column(String, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="uploaded")


class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    chunk_type = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    source_page = Column(Integer, nullable=True)
    source_section = Column(String, nullable=True)
    source_line_start = Column(Integer, nullable=True)
    source_line_end = Column(Integer, nullable=True)
    embedding_status = Column(Boolean, default=False)


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    text = Column(Text, nullable=False)
    linked_chunk_ids = Column(JSON, default=list)  # stored as a JSON list
    status = Column(String, default="proposed")
    confidence = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)


class Ambiguity(Base):
    __tablename__ = "ambiguities"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    description = Column(Text, nullable=False)
    related_requirement_ids = Column(JSON, default=list)
    suggested_clarification = Column(Text, nullable=False)
    status = Column(String, default="open")
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    title = Column(String, nullable=False)
    preconditions = Column(Text, nullable=True)
    steps = Column(JSON, nullable=False)  # stored as a JSON list of strings
    expected_result = Column(Text, nullable=False)
    priority = Column(String, default="P2")
    linked_requirement_ids = Column(JSON, default=list)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_generated_at = Column(DateTime, default=datetime.utcnow)


class ExecutionRun(Base):
    __tablename__ = "execution_runs"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    target_url = Column(String, nullable=False)
    status = Column(String, default="completed")  # running | completed | failed
    total_tests = Column(Integer, default=0)
    passed_tests = Column(Integer, default=0)
    failed_tests = Column(Integer, default=0)
    duration_ms = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExecutionEvidence(Base):
    __tablename__ = "execution_evidence"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("execution_runs.id"), nullable=False)
    test_case_id = Column(String, ForeignKey("test_cases.id"), nullable=False)
    status = Column(String, nullable=False)  # PASSED | FAILED
    duration_ms = Column(Float, default=0.0)
    screenshot_path = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ApiTestCase(Base):
    __tablename__ = "api_test_cases"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    method = Column(String, nullable=False)  # GET | POST | PUT | DELETE
    endpoint = Column(String, nullable=False)
    test_type = Column(String, default="POSITIVE")  # POSITIVE | NEGATIVE | SECURITY | BOUNDARY
    headers = Column(JSON, default=dict)
    query_params = Column(JSON, default=dict)
    body = Column(JSON, nullable=True)
    expected_status = Column(Integer, default=200)
    expected_response_schema = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ApiExecutionRun(Base):
    __tablename__ = "api_execution_runs"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    base_url = Column(String, nullable=False)
    total_requests = Column(Integer, default=0)
    passed_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    avg_latency_ms = Column(Float, default=0.0)
    results = Column(JSON, default=list)  # Detailed request/response telemetry
    created_at = Column(DateTime, default=datetime.utcnow)
