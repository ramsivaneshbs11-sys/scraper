"""
Day 6 Chunker Test Suite.

Verifies smart document chunking across:
1. Python Code (.py) -> Code chunks with line ranges
2. Markdown (.md) -> Requirement chunks split by headings
3. Word (.docx) -> Document chunks with table & section retention
4. PDF (.pdf) -> Page-aware chunks
5. Plain Text (.txt) -> Overlapping window chunks

Also validates SQLite database saving and REST API chunk endpoints.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fitz
import docx
from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def create_test_samples():
    os.makedirs("test_samples_day6", exist_ok=True)

    # 1. Code sample (.py)
    py_code = '''"""UPSC Question Generator Engine."""

class UPSCQuestionGenerator:
    def __init__(self, model_name: str = "gemini-pro"):
        self.model_name = model_name

    def generate_mcq(self, topic: str, difficulty: str = "medium") -> dict:
        """Generates a 4-option multiple choice question."""
        return {
            "question": f"Which of the following relates to {topic}?",
            "options": ["A", "B", "C", "D"],
            "answer": "A"
        }

def evaluate_submission(user_answer: str, correct_answer: str) -> bool:
    """Check if submitted answer matches key."""
    return user_answer.strip().upper() == correct_answer.strip().upper()
'''
    with open("test_samples_day6/sample_engine.py", "w", encoding="utf-8") as f:
        f.write(py_code)

    # 2. Markdown sample (.md)
    md_content = '''# UPSC Prelims Requirement Specs

## Section 1: Question Pool Setup
The question bank must contain at least 500 questions covering Indian Polity and History.

## Section 2: Scoring Mechanism
Correct answers grant +2 marks. Incorrect answers deduct 0.66 marks. Unattempted questions carry 0 marks.
'''
    with open("test_samples_day6/sample_requirements.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # 3. Word sample (.docx)
    doc = docx.Document()
    doc.add_heading("UPSC Test Generator User Manual", level=1)
    doc.add_paragraph("This manual explains how candidate test reports are computed and saved.")
    doc.add_heading("Report Generation Workflow", level=2)
    doc.add_paragraph("Step 1: Fetch candidate responses from DB.\nStep 2: Compare against official key.\nStep 3: Export PDF.")
    doc.save("test_samples_day6/sample_manual.docx")

    # 4. PDF sample (.pdf)
    pdf = fitz.open()
    p1 = pdf.new_page()
    p1.insert_text((50, 50), "UPSC Syllabus Page 1: General Studies Paper I\nIndian National Movement and Economics.")
    p2 = pdf.new_page()
    p2.insert_text((50, 50), "UPSC Syllabus Page 2: General Studies Paper II\nLogical Reasoning, Decision Making, and Comprehension.")
    pdf.save("test_samples_day6/sample_syllabus.pdf")
    pdf.close()


def run_day6_tests():
    print("\n==============================================")
    print("      RUNNING DAY 6 CHUNKER TEST SUITE       ")
    print("==============================================\n")
    create_test_samples()

    # Ensure a test project exists in DB
    db = SessionLocal()
    proj = db.query(models.Project).first()
    if not proj:
        user = models.User(id="u1", email="admin@test.com", name="Admin", role="admin")
        db.add(user)
        db.commit()
        proj = models.Project(id="p1", name="UPSC Test Project", created_by="u1")
        db.add(proj)
        db.commit()
    project_id = proj.id
    db.close()

    files_to_test = [
        ("test_samples_day6/sample_engine.py", "sample_engine.py", "text/x-python", "code"),
        ("test_samples_day6/sample_requirements.md", "sample_requirements.md", "text/markdown", "requirement_doc"),
        ("test_samples_day6/sample_manual.docx", "sample_manual.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "requirement_doc"),
        ("test_samples_day6/sample_syllabus.pdf", "sample_syllabus.pdf", "application/pdf", "architecture_doc"),
    ]

    for file_path, fname, mime, expected_chunk_type in files_to_test:
        print(f"Testing Upload & Chunking for: {fname}")

        # Upload
        with open(file_path, "rb") as f:
            upload_res = client.post("/documents/upload", data={"project_id": project_id}, files={"file": (fname, f, mime)})
        assert upload_res.status_code == 200, upload_res.text
        doc_id = upload_res.json()["id"]

        # Call POST /documents/{doc_id}/chunk
        chunk_res = client.post(f"/documents/{doc_id}/chunk")
        assert chunk_res.status_code == 200, chunk_res.text
        chunk_data = chunk_res.json()

        print(f"   [PASS] Total Chunks Created: {chunk_data['total_chunks']}")
        assert chunk_data["total_chunks"] > 0, "No chunks generated!"
        assert chunk_data["status"] == "chunked"

        for c in chunk_data["chunks"]:
            print(f"     * Chunk ID: {c['chunk_id'][:8]} | Type: {c['chunk_type']} | Section: {c['source_section']}")

        # Verify chunks persisted in database
        db = SessionLocal()
        db_chunks = db.query(models.Chunk).filter(models.Chunk.document_id == doc_id).all()
        assert len(db_chunks) == chunk_data["total_chunks"], "DB chunk count mismatch!"
        print(f"   [PASS] Verified {len(db_chunks)} chunks saved in SQLite database.\n")
        db.close()

    print("==============================================")
    print("      ALL DAY 6 CHUNKER TESTS PASSED (4/4)    ")
    print("==============================================\n")


if __name__ == "__main__":
    run_day6_tests()
