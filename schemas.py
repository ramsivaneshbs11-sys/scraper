"""
Core Pydantic schemas for the AI Test Case Generator.

These define the exact shape of every piece of data that flows through the
pipeline: Project/User/Document (organizational layer), ChunkMetadata
(evidence layer), Requirement/Ambiguity (human review layer), and TestCase
(output layer).

No business logic here — just data shapes and validation.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums — fixed-choice fields, prevents typo bugs like "aproved" vs "approved"
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    ADMIN = "admin"
    TESTER = "tester"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    CHUNKED = "chunked"
    ANALYZED = "analyzed"
    FAILED = "failed"


class ChunkType(str, Enum):
    REQUIREMENT_DOC = "requirement_doc"
    CODE = "code"
    ARCHITECTURE_DOC = "architecture_doc"
    PROMPT_DOC = "prompt_doc"


class RequirementStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class AmbiguityStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class TestCaseStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class TestCasePriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"



# ---------------------------------------------------------------------------
# Organizational layer — who owns what, and what's been uploaded
# ---------------------------------------------------------------------------

class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_by: str  # User.id
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole
    project_ids: List[str] = Field(default_factory=list)  # projects this user can access
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Document(BaseModel):
    id: str
    project_id: str
    filename: str
    file_type: str  # e.g. "pdf", "docx", "py"
    uploaded_by: str  # User.id
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    status: DocumentStatus = DocumentStatus.UPLOADED


# ---------------------------------------------------------------------------
# Evidence layer — where did this come from (the traceability backbone)
# ---------------------------------------------------------------------------

class ChunkMetadata(BaseModel):
    chunk_id: str
    project_id: str
    document_id: str
    chunk_type: ChunkType
    text: str
    source_page: Optional[int] = None       # for PDFs
    source_section: Optional[str] = None    # for docs with headings
    source_line_start: Optional[int] = None  # for code
    source_line_end: Optional[int] = None    # for code
    embedding_status: bool = False  # has this chunk been embedded into Qdrant yet


# ---------------------------------------------------------------------------
# Human review layer — what's approved, what's unclear
# ---------------------------------------------------------------------------

class Requirement(BaseModel):
    id: str
    project_id: str
    text: str
    linked_chunk_ids: List[str] = Field(default_factory=list)
    status: RequirementStatus = RequirementStatus.PROPOSED
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: Optional[str] = None  # User.id
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class Ambiguity(BaseModel):
    id: str
    project_id: str
    description: str
    related_requirement_ids: List[str] = Field(default_factory=list)
    suggested_clarification: str
    status: AmbiguityStatus = AmbiguityStatus.OPEN
    resolution_note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Output layer — what the tester actually walks away with
# ---------------------------------------------------------------------------

class TestCase(BaseModel):
    id: str
    project_id: str
    title: str
    preconditions: Optional[str] = None
    steps: List[str]
    expected_result: str
    priority: TestCasePriority = TestCasePriority.P2
    linked_requirement_ids: List[str] = Field(default_factory=list)  # traceability
    status: TestCaseStatus = TestCaseStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Quick self-check — run this file directly to confirm everything works
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    project = Project(id="p1", name="UPSC Chatbot", created_by="u1")
    user = User(id="u1", email="admin@example.com", name="Admin", role=UserRole.ADMIN, project_ids=["p1"])
    doc = Document(id="d1", project_id="p1", filename="spec.pdf", file_type="pdf", uploaded_by="u1")
    chunk = ChunkMetadata(
        chunk_id="c1", project_id="p1", document_id="d1",
        chunk_type=ChunkType.REQUIREMENT_DOC, text="The system shall...", source_page=3
    )
    requirement = Requirement(
        id="r1", project_id="p1", text="User can log in with email and password",
        linked_chunk_ids=["c1"], confidence=0.92
    )
    ambiguity = Ambiguity(
        id="a1", project_id="p1", description="Unclear password length limit",
        related_requirement_ids=["r1"], suggested_clarification="What is the max password length?"
    )
    test_case = TestCase(
        id="t1", project_id="p1", title="Verify login with valid credentials",
        steps=["Navigate to login page", "Enter valid email and password", "Click Login"],
        expected_result="User is redirected to the dashboard",
        linked_requirement_ids=["r1"]
    )

    print("All schemas created successfully:")
    for obj in [project, user, doc, chunk, requirement, ambiguity, test_case]:
        print(f"  {obj.__class__.__name__}: OK")
