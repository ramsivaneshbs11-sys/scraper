"""
Automated verification test suite for Day 4 document upload endpoints.
Tests:
1. Valid file upload (POST /documents/upload)
2. File physically saved on disk with correct content
3. Fetch document by ID (GET /documents/{id})
4. List documents by project (GET /documents?project_id=...)
5. Disallowed file type rejection (HTTP 400)
6. Non-existent project rejection (HTTP 404)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_day4_pipeline():
    print("--- Starting Day 4 Verification ---")

    # 1. Test invalid project
    print("\n1. Testing upload with non-existent project...")
    res = client.post(
        "/documents/upload",
        data={"project_id": "nonexistent_proj", "uploaded_by": "u1"},
        files={"file": ("spec.txt", b"System requirements content", "text/plain")}
    )
    assert res.status_code == 404, f"Expected 404, got {res.status_code}"
    print("   [PASS] Non-existent project returned 404")

    # 2. Test disallowed file extension (.exe)
    print("\n2. Testing upload with disallowed extension (.exe)...")
    res = client.post(
        "/documents/upload",
        data={"project_id": "p1", "uploaded_by": "u1"},
        files={"file": ("malware.exe", b"binary content", "application/octet-stream")}
    )
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    print("   [PASS] Disallowed extension returned 400:", res.json()["detail"])

    # 3. Test valid file upload (.txt)
    print("\n3. Testing valid file upload (requirements.txt)...")
    file_bytes = b"# UPSC Chatbot Requirements\n1. User must be able to ask syllabus questions.\n2. Answers must cite official UPSC sources."
    res = client.post(
        "/documents/upload",
        data={"project_id": "p1", "uploaded_by": "u1"},
        files={"file": ("syllabus_spec.txt", file_bytes, "text/plain")}
    )
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    doc_data = res.json()
    doc_id = doc_data["id"]
    print("   [PASS] Upload successful. Document ID:", doc_id)
    print("          Filename:", doc_data["filename"])
    print("          File Type:", doc_data["file_type"])
    print("          Status:", doc_data["status"])

    # 4. Verify physical file on disk
    print("\n4. Verifying physical file in storage directory...")
    expected_disk_path = os.path.join("storage", "uploaded", f"{doc_id}.txt")
    assert os.path.exists(expected_disk_path), f"File not found on disk at {expected_disk_path}"
    with open(expected_disk_path, "rb") as f:
        disk_bytes = f.read()
    assert disk_bytes == file_bytes, "File content on disk does not match uploaded content!"
    print(f"   [PASS] File confirmed on disk: {expected_disk_path} ({len(disk_bytes)} bytes)")

    # 5. Test fetch by ID
    print(f"\n5. Testing fetch document by ID (GET /documents/{doc_id})...")
    res = client.get(f"/documents/{doc_id}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    fetched = res.json()
    assert fetched["id"] == doc_id
    assert fetched["filename"] == "syllabus_spec.txt"
    print("   [PASS] Fetch by ID returned matching document metadata.")

    # 6. Test list by project
    print("\n6. Testing list documents for project 'p1' (GET /documents?project_id=p1)...")
    res = client.get("/documents?project_id=p1")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    docs_list = res.json()
    assert any(d["id"] == doc_id for d in docs_list), "Uploaded document not found in project listing"
    print(f"   [PASS] Project listing returned {len(docs_list)} document(s).")

    print("\n==========================================")
    print(" ALL DAY 4 VERIFICATIONS PASSED (6/6)     ")
    print("==========================================")

if __name__ == "__main__":
    test_day4_pipeline()
