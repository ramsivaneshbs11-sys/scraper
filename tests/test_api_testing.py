"""
Test Suite for Automated REST API Testing Lab (Option B).
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def test_api_testing_pipeline():
    print("\n--- Testing Automated REST API Testing Lab ---")

    # 1. Setup project
    db = SessionLocal()
    proj = db.query(models.Project).filter(models.Project.id == "p_api_lab").first()
    if not proj:
        user = db.query(models.User).filter(models.User.id == "u1").first()
        if not user:
            user = models.User(id="u1", email="tester@qa.com", name="QA Tester", role="tester")
            db.add(user)
            db.commit()
        proj = models.Project(id="p_api_lab", name="API Microservices Suite", created_by="u1")
        db.add(proj)
        db.commit()
    project_id = proj.id
    db.close()

    # 2. Test OpenAPI spec import & test generation
    print("1. Importing OpenAPI spec & generating tests...")
    sample_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Sample Auth API", "version": "1.0.0"},
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check endpoint",
                    "responses": {"200": {"description": "OK"}}
                }
            },
            "/api/v1/login": {
                "post": {
                    "summary": "User Authentication",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "email": {"type": "string", "format": "email"},
                                        "password": {"type": "string"}
                                    },
                                    "required": ["email", "password"]
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Authenticated"}}
                }
            }
        }
    }

    res = client.post(
        f"/projects/{project_id}/api/import-spec",
        json={"spec_json": sample_spec}
    )
    assert res.status_code == 200, f"Import failed: {res.text}"
    import_data = res.json()
    print(f"   [PASS] Generated {import_data['total_test_cases_generated']} API test cases.")
    assert import_data["total_test_cases_generated"] >= 3
    assert import_data["breakdown"]["positive"] >= 2
    assert import_data["breakdown"]["negative"] >= 1

    # 3. Test list API test cases endpoint
    print("2. Listing API test cases...")
    tc_res = client.get(f"/projects/{project_id}/api/test-cases")
    assert tc_res.status_code == 200
    tc_list = tc_res.json()
    assert len(tc_list) >= 3
    print(f"   [PASS] Successfully retrieved {len(tc_list)} API test cases.")

    # 4. Test Postman Collection export
    print("3. Exporting to Postman Collection v2.1...")
    postman_res = client.get(f"/projects/{project_id}/api/export/postman")
    assert postman_res.status_code == 200
    postman_data = postman_res.json()
    assert "info" in postman_data
    assert "item" in postman_data
    assert len(postman_data["item"]) >= 3
    print(f"   [PASS] Exported {len(postman_data['item'])} endpoints to Postman collection.")
