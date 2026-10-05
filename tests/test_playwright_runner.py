"""
Test Playwright Automation Runner & Evidence Generation (Layer 4 & 5).
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def test_playwright_execution_and_evidence():
    print("\n--- Testing Playwright Execution & Evidence Engine ---")

    # 1. Setup Project & Test Cases in DB
    db = SessionLocal()
    proj = db.query(models.Project).filter(models.Project.id == "p_pw_test").first()
    if not proj:
        user = db.query(models.User).filter(models.User.id == "u1").first()
        if not user:
            user = models.User(id="u1", email="tester@qa.com", name="QA Tester", role="tester")
            db.add(user)
            db.commit()

        proj = models.Project(id="p_pw_test", name="E2E Automation Project", created_by="u1")
        db.add(proj)
        db.commit()

    tc1 = db.query(models.TestCase).filter(models.TestCase.id == "TC-PW-001").first()
    if not tc1:
        tc1 = models.TestCase(
            id="TC-PW-001",
            project_id=proj.id,
            title="[POSITIVE] Verify Portal Health & Navigation",
            preconditions="Browser is launched",
            steps=["1. Open portal", "2. Check for button or headers", "3. Assert page loaded"],
            expected_result="Portal loads cleanly with 200 OK",
            priority="P1",
            status="approved"
        )
        db.add(tc1)
        db.commit()
    project_id = proj.id
    db.close()

    # 2. Trigger Playwright execution with file:// or localhost url
    print("1. Running Playwright test suite...")
    html_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static", "review.html"))
    target_url = f"file:///{html_file.replace(os.sep, '/')}"

    res = client.post(
        f"/projects/{project_id}/execute",
        json={"target_url": target_url, "test_case_ids": ["TC-PW-001"]}
    )
    assert res.status_code == 200, f"Execution failed: {res.text}"
    data = res.json()

    print(f"   [PASS] Run ID: {data['run_id']}")
    print(f"   [PASS] Passed tests: {data['passed_tests']}/{data['total_tests']}")
    print(f"   [PASS] Duration: {data['total_duration_ms']}ms")
    assert data["status"] == "completed"
    assert data["total_tests"] >= 1
    assert len(data["evidence"]) >= 1

    ev = data["evidence"][0]
    assert ev["status"] == "PASSED"
    assert ev["has_screenshot"] is True

    # 3. Check Runs list endpoint
    print("2. Verifying runs history...")
    runs_res = client.get(f"/projects/{project_id}/runs")
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 1
    print(f"   [PASS] Found {len(runs)} historical run(s).")

    # 4. Check Screenshot fetch endpoint
    evidence_id = ev["evidence_id"]
    print(f"3. Verifying screenshot evidence endpoint for {evidence_id}...")
    shot_res = client.get(f"/evidence/{evidence_id}/screenshot")
    assert shot_res.status_code == 200
    assert shot_res.headers["content-type"] == "image/png"
    assert len(shot_res.content) > 1000
    print(f"   [PASS] Screenshot retrieved successfully ({len(shot_res.content)} bytes).")
