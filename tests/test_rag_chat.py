"""
Test suite for RAG Chat & Dynamic Test Case Injection API endpoint.
"""

import sys
import os
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def test_rag_chat_and_dynamic_injection():
    db = SessionLocal()
    try:
        # Create test project
        proj = db.query(models.Project).filter(models.Project.id == "p_chat_test").first()
        if not proj:
            user = db.query(models.User).filter(models.User.id == "u1").first()
            if not user:
                user = models.User(id="u1", email="chat@qa.com", name="Chat Tester", role="admin")
                db.add(user)
                db.commit()

            proj = models.Project(id="p_chat_test", name="RAG Chat Project", created_by="u1")
            db.add(proj)
            db.commit()

        # 1. Standard Q&A RAG Chat
        res1 = client.post("/rag/projects/p_chat_test/chat", json={"message": "What authentication rules exist?"})
        assert res1.status_code == 200
        data1 = res1.json()
        assert "reply" in data1
        print(f"\n[PASS] RAG QA Chat reply received.")

        # 2. Dynamic Test Case Creation & Injection Intent
        res2 = client.post(
            "/rag/projects/p_chat_test/chat",
            json={"message": "Add a security test case for SQL injection in authorization header"}
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2.get("action_taken") == "test_case_added"
        assert "created_test_case" in data2
        created_tc = data2["created_test_case"]
        assert created_tc["test_type"] == "SECURITY"
        print(f"\n[PASS] Dynamic Test Injection successful: {created_tc['title']}")

        # Verify row exists in SQLite database
        db_tc = db.query(models.TestCase).filter(models.TestCase.id == created_tc["id"]).first()
        assert db_tc is not None
        assert "SQL injection" in db_tc.title
        print(f"[PASS] DB row verified for dynamic test case {db_tc.id}.")

    finally:
        db.close()
