"""
Extraction Quality Inspection Test Suite.
Uploads realistic UPSC chatbot documents (.docx, .pdf, .py, .md) with tables,
extracts them through the FastAPI pipeline, and prints the exact outputs for visual review.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)
SAMPLE_DIR = r"c:\Users\Sivanesh\Downloads\generator\sample_test_documents"

def test_quality():
    files_to_test = [
        ("upsc_spec_with_tables.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("upsc_spec_with_tables.pdf", "application/pdf"),
        ("upsc_chatbot_service.py", "text/x-python"),
        ("upsc_syllabus_spec.md", "text/markdown"),
    ]

    for fname, mime in files_to_test:
        fpath = os.path.join(SAMPLE_DIR, fname)
        print("\n" + "=" * 70)
        print(f"DOCUMENT: {fname}")
        print("=" * 70)

        # 1. Upload
        with open(fpath, "rb") as f:
            upload_res = client.post(
                "/documents/upload",
                data={"project_id": "UPSC Chatbot"},
                files={"file": (fname, f, mime)}
            )
        assert upload_res.status_code == 200, upload_res.text
        doc_id = upload_res.json()["id"]

        # 2. Extract
        ext_res = client.post(f"/documents/{doc_id}/extract")
        assert ext_res.status_code == 200, ext_res.text
        data = ext_res.json()

        print(f"Total Characters: {data['total_characters']} | Total Extracted Units: {data['units_count']}")
        print(f"Metadata: {data['metadata']}")
        print("-" * 50)

        for idx, unit in enumerate(data["units"], 1):
            title = unit.get("section_title") or f"Unit {idx}"
            pg = f" (Page {unit['page_number']})" if unit.get("page_number") else ""
            lines = f" (Lines {unit['line_start']}-{unit['line_end']})" if unit.get("line_start") else ""
            print(f"\n>>> SECTION [{idx}]: {title}{pg}{lines}")
            print(unit["text"].strip())

    print("\n" + "=" * 70)
    print("EXTRACTION QUALITY EVALUATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    test_quality()
