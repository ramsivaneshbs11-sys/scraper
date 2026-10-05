"""
Test for Unified Document Ingestion Endpoint (POST /documents/ingest).

Tests the single-endpoint end-to-end execution:
Upload -> Extraction -> Preprocessing -> Chunking -> Filesystem JSON & SQLite DB
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def test_unified_ingestion():
    print("\n--- Testing Unified Ingestion Endpoint (POST /documents/ingest) ---")

    # Ensure a project exists
    db = SessionLocal()
    proj = db.query(models.Project).first()
    if not proj:
        user = models.User(id="u1", email="admin@test.com", name="Admin", role="admin")
        db.add(user)
        db.commit()
        proj = models.Project(id="p1", name="UPSC Ingest Test", created_by="u1")
        db.add(proj)
        db.commit()
    project_id = proj.id
    db.close()

    # Sample markdown document with table and noisy hyphens
    sample_content = """# UPSC Chatbot Mock Test Module

## 1. Exam Structure
| Stage | Questions | Duration | Marks |
| Prelims | 100 | 120 Mins | 200 |
| Mains | 9 Papers | 3 Hours Each | 1750 |

## 2. Evaluation Policy
System performs auto-\nmatic scoring and answers must cite official UPSC sources.
"""

    # Hit the single unified endpoint
    res = client.post(
        "/documents/ingest",
        data={"project_id": project_id, "max_chunk_size": 500},
        files={"file": ("upsc_mock_test.md", sample_content.encode("utf-8"), "text/markdown")}
    )

    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()

    print("   [PASS] Endpoint responded with HTTP 200 OK")
    print("          Document ID:", data["document_id"])
    print("          Filename   :", data["filename"])
    print("          Status     :", data["status"])
    print("          Completed  :", data["pipeline_stages_completed"])

    # 1. Verify extraction & preprocessing
    extracted_summary = data["extracted_summary"]
    assert extracted_summary["preprocessed"] is True
    assert extracted_summary["units_count"] >= 2
    assert os.path.exists(extracted_summary["extracted_file"])
    print(f"   [PASS] Extraction & Preprocessing confirmed (File: {extracted_summary['extracted_file']})")

    # 2. Verify dehyphenation worked during preprocessing
    with open(extracted_summary["extracted_file"], "r", encoding="utf-8") as f:
        extracted_json = f.read()
    assert "automatic scoring" in extracted_json
    print("   [PASS] Preprocessor cleaned broken line-break 'auto-\\nmatic' -> 'automatic'")

    # 3. Verify chunking
    chunking_summary = data["chunking_summary"]
    assert chunking_summary["total_chunks"] >= 2
    assert os.path.exists(chunking_summary["chunks_file"])
    print(f"   [PASS] Chunking confirmed ({chunking_summary['total_chunks']} chunks in {chunking_summary['chunks_file']})")

    # 4. Verify SQLite database persistence
    db = SessionLocal()
    db_chunks = db.query(models.Chunk).filter(models.Chunk.document_id == data["document_id"]).all()
    assert len(db_chunks) == chunking_summary["total_chunks"]
    print(f"   [PASS] Confirmed {len(db_chunks)} chunks persisted into SQLite database.")
    db.close()

    print("\n=======================================================")
    print(" UNIFIED INGESTION PIPELINE VERIFIED SUCCESSFULLY (4/4) ")
    print("=======================================================\n")


if __name__ == "__main__":
    test_unified_ingestion()
