"""
Test suite for Unified QA Copilot Workflow:
1. Document Ingestion (POST /documents/ingest)
2. Requirements & Ambiguities Extraction
3. One-Click Approval (POST /projects/{project_id}/requirements/approve-all)
4. RAG Test Case Generation (POST /projects/{project_id}/generate-test-cases)
5. Test Case Verification (GET /projects/{project_id}/test-cases)
6. Export to CSV (GET /projects/{project_id}/test-cases/export)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def test_unified_qa_copilot_pipeline():
    print("\n--- Testing Unified QA Copilot Complete Pipeline ---")

    # 1. Setup user & project
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.id == "u1").first()
    if not user:
        user = models.User(id="u1", email="tester@qa.com", name="QA Tester", role="tester")
        db.add(user)
        db.commit()

    proj = db.query(models.Project).filter(models.Project.id == "p_copilot").first()
    if not proj:
        proj = models.Project(id="p_copilot", name="Payment Gateway Module", created_by="u1")
        db.add(proj)
        db.commit()
    project_id = proj.id
    db.close()

    # 2. Ingest document
    spec_content = """# Payment Gateway & Wallet Specification

## 1. Wallet Top-Up Limits
The wallet top-up amount must be between 100 and 10000 rupees.
Transactions below 100 or above 10000 must be rejected with an invalid amount error.

## 2. Bank Retry & Timeout
If the bank server is unresponsive, the system must retry 3 times before failing the transaction.
The system response should be fast and secure.
"""

    print("1. Ingesting specification document...")
    res = client.post(
        "/documents/ingest",
        data={"project_id": project_id, "auto_analyze": "true"},
        files={"file": ("payment_specs.md", spec_content.encode("utf-8"), "text/markdown")}
    )
    assert res.status_code == 200, f"Ingestion failed: {res.text}"
    doc_id = res.json()["document_id"]
    print(f"   [PASS] Ingested document: {doc_id}")

    # 3. Verify requirements & ambiguities were extracted
    print("2. Verifying requirements & ambiguities...")
    req_res = client.get(f"/projects/{project_id}/requirements")
    assert req_res.status_code == 200
    reqs = req_res.json()["requirements"]
    assert len(reqs) >= 1, "Expected at least 1 requirement extracted"
    print(f"   [PASS] Extracted {len(reqs)} requirements.")

    amb_res = client.get(f"/projects/{project_id}/ambiguities")
    assert amb_res.status_code == 200
    ambs = amb_res.json()["ambiguities"]
    print(f"   [PASS] Extracted {len(ambs)} ambiguities.")

    # 4. One-click approve all requirements
    print("3. One-click approving all requirements...")
    approve_res = client.post(f"/projects/{project_id}/requirements/approve-all")
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "success"
    print(f"   [PASS] Approved {approve_res.json()['approved_count']} requirements.")

    # 5. Generate Grounded Test Cases (RAG-Powered)
    print("4. Generating grounded test cases...")
    gen_res = client.post(f"/projects/{project_id}/generate-test-cases?include_proposed=true")
    assert gen_res.status_code == 200, f"Generation failed: {gen_res.text}"
    tc_data = gen_res.json()
    assert tc_data["total_test_cases"] > 0
    print(f"   [PASS] Successfully generated {tc_data['total_test_cases']} test cases.")

    # 6. Fetch test cases from API
    print("5. Fetching test cases from project...")
    list_res = client.get(f"/projects/{project_id}/test-cases")
    assert list_res.status_code == 200
    test_cases = list_res.json()["test_cases"]
    assert len(test_cases) == tc_data["total_test_cases"]
    for tc in test_cases:
        assert tc["title"]
        assert tc["expected_result"]
        assert len(tc["steps"]) > 0
        assert tc["priority"] in ["P0", "P1", "P2", "P3"]
    print(f"   [PASS] All {len(test_cases)} test cases validated with valid Pydantic fields.")

    # 7. Export to CSV
    print("6. Testing CSV / Excel Export...")
    export_res = client.get(f"/projects/{project_id}/test-cases/export")
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    csv_text = export_res.text
    assert "Test Case ID,Title,Priority" in csv_text
    print(f"   [PASS] CSV Export validated with {len(csv_text.splitlines())} lines.")

    print("\n=======================================================")
    print(" UNIFIED QA COPILOT END-TO-END PIPELINE VERIFIED (6/6) ")
    print("=======================================================\n")


if __name__ == "__main__":
    test_unified_qa_copilot_pipeline()
