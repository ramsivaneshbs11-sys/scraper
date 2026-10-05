"""
Automated Test Suite for Day 8: Admin Review UI & Human Actions.

Tests:
1. UI Console Endpoint (GET /review) returns HTTP 200 OK.
2. Human Action: Approve Requirement (PATCH /requirements/{id}/approve).
3. Human Action: Reject Requirement with Reason (PATCH /requirements/{id}/reject).
4. Human Action: Resolve Ambiguity with Clarification Note (PATCH /ambiguities/{id}/resolve).
5. Database validation of review timestamps, reviewer ID, and status updates.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def test_day8_admin_review():
    print("\n=======================================================")
    print("        RUNNING DAY 8 ADMIN REVIEW UI TEST SUITE       ")
    print("=======================================================\n")

    # 1. Test Admin Review UI endpoint
    print("1. Testing GET /review endpoint...")
    ui_res = client.get("/review")
    assert ui_res.status_code == 200, f"Expected 200, got {ui_res.status_code}"
    assert "Admin Review Console" in ui_res.text
    print("   [PASS] GET /review served interactive Admin Review UI console.")

    # 2. Setup a test requirement and ambiguity in DB
    db = SessionLocal()
    proj = db.query(models.Project).first()
    if not proj:
        user = models.User(id="u1", email="admin@test.com", name="Admin", role="admin")
        db.add(user)
        db.commit()
        proj = models.Project(id="p1", name="UPSC Day 8 Test", created_by="u1")
        db.add(proj)
        db.commit()
    project_id = proj.id

    req1 = models.Requirement(
        id="test-req-approve",
        project_id=project_id,
        text="Candidates must submit application before deadline.",
        confidence=0.95,
        status="proposed",
        linked_chunk_ids=["chunk-001"]
    )
    req2 = models.Requirement(
        id="test-req-reject",
        project_id=project_id,
        text="Application fees must be paid via postal stamp.",
        confidence=0.75,
        status="proposed",
        linked_chunk_ids=["chunk-002"]
    )
    amb1 = models.Ambiguity(
        id="test-amb-resolve",
        project_id=project_id,
        description="Unclear timeout duration for exam page.",
        suggested_clarification="What is the session inactivity timeout?",
        status="open"
    )

    db.merge(req1)
    db.merge(req2)
    db.merge(amb1)
    db.commit()
    db.close()

    # 3. Test Human Action: APPROVE
    print("\n2. Testing Human Action: Approve Requirement (PATCH /requirements/{id}/approve)...")
    app_res = client.patch(f"/requirements/{req1.id}/approve?reviewer_id=u1")
    assert app_res.status_code == 200, app_res.text
    app_data = app_res.json()
    assert app_data["status"] == "success"
    print(f"   [PASS] Requirement {req1.id} approved successfully.")

    # Verify DB update
    db = SessionLocal()
    updated_req1 = db.query(models.Requirement).filter(models.Requirement.id == req1.id).first()
    assert updated_req1.status == "approved"
    assert updated_req1.reviewed_by == "u1"
    assert updated_req1.reviewed_at is not None
    print(f"          Database verified: status='{updated_req1.status}', reviewed_by='{updated_req1.reviewed_by}'")
    db.close()

    # 4. Test Human Action: REJECT WITH REASON
    print("\n3. Testing Human Action: Reject Requirement with Reason (PATCH /requirements/{id}/reject)...")
    rej_reason = "Postal stamps are no longer accepted; online UPI only."
    rej_res = client.patch(f"/requirements/{req2.id}/reject?reason={rej_reason}&reviewer_id=u1")
    assert rej_res.status_code == 200, rej_res.text
    rej_data = rej_res.json()
    assert rej_data["status"] == "success"
    print(f"   [PASS] Requirement {req2.id} rejected successfully with reason.")

    # Verify DB update
    db = SessionLocal()
    updated_req2 = db.query(models.Requirement).filter(models.Requirement.id == req2.id).first()
    assert updated_req2.status == "rejected"
    assert updated_req2.rejection_reason == rej_reason
    assert updated_req2.reviewed_by == "u1"
    assert updated_req2.reviewed_at is not None
    print(f"          Database verified: status='{updated_req2.status}', reason='{updated_req2.rejection_reason}'")
    db.close()

    # 5. Test Human Action: RESOLVE AMBIGUITY
    print("\n4. Testing Human Action: Resolve Ambiguity (PATCH /ambiguities/{id}/resolve)...")
    res_note = "Session inactivity timeout is set to exactly 15 minutes."
    amb_res = client.patch(f"/ambiguities/{amb1.id}/resolve?resolution_note={res_note}")
    assert amb_res.status_code == 200, amb_res.text
    amb_data = amb_res.json()
    assert amb_data["status"] == "success"
    print(f"   [PASS] Ambiguity {amb1.id} marked as resolved with note.")

    # Verify DB update
    db = SessionLocal()
    updated_amb1 = db.query(models.Ambiguity).filter(models.Ambiguity.id == amb1.id).first()
    assert updated_amb1.status == "resolved"
    assert updated_amb1.resolution_note == res_note
    print(f"          Database verified: status='{updated_amb1.status}', note='{updated_amb1.resolution_note}'")
    db.close()

    print("\n=======================================================")
    print("      ALL DAY 8 ADMIN REVIEW UI TESTS PASSED (5/5)     ")
    print("=======================================================\n")


if __name__ == "__main__":
    test_day8_admin_review()
