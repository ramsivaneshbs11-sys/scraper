"""
Automated Test Suite for Day 7: Requirement Analyzer (LLM + Validation).

Tests:
1. Ingesting test specifications with clear rules and ambiguous terms.
2. Triggering AI Analysis via POST /documents/{id}/analyze.
3. Pydantic validation of requirements (confidence, linked chunks, status).
4. Ambiguity detection and clarification suggestions.
5. Database persistence in requirements and ambiguities tables.
6. Retrieval via GET /documents/{id}/requirements and GET /documents/{id}/ambiguities.
7. Verification of audit log at storage/analysis/{id}.json.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def test_day7_requirement_analysis():
    print("\n=======================================================")
    print("      RUNNING DAY 7 REQUIREMENT ANALYZER TEST SUITE    ")
    print("=======================================================\n")

    # Ensure clean isolated project for Day 7 tests
    db = SessionLocal()
    project_id = "p_day7_isolated"
    user = db.query(models.User).filter(models.User.id == "u1").first()
    if not user:
        user = models.User(id="u1", email="admin@test.com", name="Admin", role="admin")
        db.add(user)
        db.commit()

    proj = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not proj:
        proj = models.Project(id=project_id, name="UPSC Day 7 Test", created_by="u1")
        db.add(proj)
        db.commit()

    # Clear old test data for this isolated project
    db.query(models.Requirement).filter(models.Requirement.project_id == project_id).delete()
    db.query(models.Ambiguity).filter(models.Ambiguity.project_id == project_id).delete()
    db.commit()
    db.close()


    # Document content with clear requirements AND ambiguous statements
    spec_content = """# UPSC Chatbot Mock Test Specification

## 1. Candidate Eligibility and Scoring
Candidates must score at least 33% (66 marks) in CSAT Paper 2 to qualify for Mains evaluation.
The system shall calculate total scores within 2 seconds of test submission.

## 2. Security and Performance
The application must be completely secure and provide fast response times for all users.
Pass-fail results will be emailed to registered candidates upon exam completion.
"""

    print("1. Ingesting test document via POST /documents/ingest...")
    ingest_res = client.post(
        "/documents/ingest",
        data={"project_id": project_id, "max_chunk_size": 400},
        files={"file": ("day7_spec.md", spec_content.encode("utf-8"), "text/markdown")}
    )
    assert ingest_res.status_code == 200, ingest_res.text
    doc_id = ingest_res.json()["document_id"]
    print(f"   [PASS] Ingested document: {doc_id}")

    print("\n2. Triggering AI Analysis via POST /documents/{id}/analyze...")
    analyze_res = client.post(f"/documents/{doc_id}/analyze")
    assert analyze_res.status_code == 200, analyze_res.text
    analysis_data = analyze_res.json()

    print(f"   [PASS] Analysis completed!")
    print(f"          Requirements Extracted : {analysis_data['requirements_count']}")
    print(f"          Ambiguities Flagged    : {analysis_data['ambiguities_count']}")
    print(f"          Audit File             : {analysis_data['audit_file']}")

    assert analysis_data["requirements_count"] > 0, "No requirements extracted!"
    assert analysis_data["ambiguities_count"] > 0, "No ambiguities flagged!"

    # Verify requirements have valid fields and chunk trace
    print("\n3. Verifying extracted requirements:")
    for req in analysis_data["requirements"]:
        print(f"     * [{req['confidence']:.2f}] {req['text'][:70]}... (Status: {req['status']})")
        assert len(req["linked_chunk_ids"]) > 0, "Requirement missing chunk citation!"
        assert 0.0 <= req["confidence"] <= 1.0, "Invalid confidence value!"

    # Verify ambiguities have description and clarification suggestion
    print("\n4. Verifying flagged ambiguities:")
    for amb in analysis_data["ambiguities"]:
        print(f"     * Flag: {amb['description'][:60]}...")
        print(f"       Clarification: {amb['suggested_clarification'][:60]}...")
        assert len(amb["description"]) > 0
        assert len(amb["suggested_clarification"]) > 0

    # 5. Verify database persistence
    print("\n5. Verifying SQLite database persistence...")
    db = SessionLocal()
    db_reqs = db.query(models.Requirement).filter(models.Requirement.project_id == project_id).all()
    db_ambs = db.query(models.Ambiguity).filter(models.Ambiguity.project_id == project_id).all()
    assert len(db_reqs) == analysis_data["requirements_count"]
    assert len(db_ambs) == analysis_data["ambiguities_count"]
    print(f"   [PASS] Verified {len(db_reqs)} requirements and {len(db_ambs)} ambiguities stored in database.")
    db.close()

    # 6. Verify GET endpoints
    print("\n6. Testing GET endpoints:")
    get_reqs_res = client.get(f"/documents/{doc_id}/requirements")
    assert get_reqs_res.status_code == 200
    assert get_reqs_res.json()["requirements_count"] == analysis_data["requirements_count"]
    print("   [PASS] GET /documents/{id}/requirements returned matching count.")

    get_ambs_res = client.get(f"/documents/{doc_id}/ambiguities")
    assert get_ambs_res.status_code == 200
    assert get_ambs_res.json()["ambiguities_count"] == analysis_data["ambiguities_count"]
    print("   [PASS] GET /documents/{id}/ambiguities returned matching count.")

    # 7. Verify audit file on disk
    print("\n7. Verifying physical audit file in storage/analysis/...")
    assert os.path.exists(analysis_data["audit_file"])
    print(f"   [PASS] Audit file confirmed on disk: {analysis_data['audit_file']}")

    print("\n=======================================================")
    print("      ALL DAY 7 REQUIREMENT ANALYZER TESTS PASSED      ")
    print("=======================================================\n")


if __name__ == "__main__":
    test_day7_requirement_analysis()
