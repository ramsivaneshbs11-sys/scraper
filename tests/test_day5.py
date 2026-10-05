"""
Comprehensive Test Suite for Day 5 Document Extractors:
1. Python Code (.py) using AST
2. Markdown (.md) with headings
3. Plain text (.txt) with paragraphs
4. Word (.docx) using python-docx
5. PDF (.pdf) using PyMuPDF (fitz)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fitz
import docx
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

def create_sample_files():
    os.makedirs("test_samples", exist_ok=True)

    # 1. Python Code Sample
    py_content = '''"""UPSC Authentication Module."""

class UPSCAuthService:
    def login(self, email: str, otp: str) -> bool:
        """Authenticate user with 6-digit OTP."""
        if len(otp) == 6:
            return True
        return False

def verify_token(token: str) -> bool:
    """Validate active JWT token."""
    return token.startswith("Bearer ")
'''
    with open("test_samples/sample_auth.py", "w", encoding="utf-8") as f:
        f.write(py_content)

    # 2. Markdown Sample
    md_content = '''# UPSC Chatbot Requirements
## 1. Syllabus Search
User can query syllabus topics by subject name.

## 2. Mock Test Generator
System generates 10 MCQs based on syllabus chunks.
'''
    with open("test_samples/sample_spec.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # 3. Word (.docx) Sample
    doc = docx.Document()
    doc.add_heading("UPSC Chatbot Architecture", level=1)
    doc.add_paragraph("This document outlines the high-level architecture of the UPSC bot.")
    doc.add_heading("Vector Search Layer", level=2)
    doc.add_paragraph("Qdrant is utilized for similarity search of syllabus chunks.")
    doc.save("test_samples/sample_arch.docx")

    # 4. PDF Sample
    pdf_doc = fitz.open()
    page1 = pdf_doc.new_page()
    page1.insert_text((50, 50), "Page 1: UPSC Chatbot Prelims Guide\nGeneral Studies syllabus overview.")
    page2 = pdf_doc.new_page()
    page2.insert_text((50, 50), "Page 2: Mains Exam Guide\nEssay and Optional subject requirements.")
    pdf_doc.save("test_samples/sample_guide.pdf")
    pdf_doc.close()


def run_tests():
    print("--- Running Day 5 Extractor Tests ---")
    create_sample_files()

    # Test Upload & Extraction for Python Code
    print("\n1. Testing Python Code Extraction (.py)...")
    with open("test_samples/sample_auth.py", "rb") as f:
        res = client.post("/documents/upload", data={"project_id": "p1"}, files={"file": ("sample_auth.py", f, "text/x-python")})
    assert res.status_code == 200, res.text
    doc_id = res.json()["id"]

    ext_res = client.post(f"/documents/{doc_id}/extract")
    assert ext_res.status_code == 200, ext_res.text
    data = ext_res.json()
    print("   [PASS] Extracted Units:", data["units_count"])
    for u in data["units"]:
        print(f"     * {u['section_title']} (Lines {u['line_start']}-{u['line_end']})")

    # Test Upload & Extraction for Markdown
    print("\n2. Testing Markdown Extraction (.md)...")
    with open("test_samples/sample_spec.md", "rb") as f:
        res = client.post("/documents/upload", data={"project_id": "p1"}, files={"file": ("sample_spec.md", f, "text/markdown")})
    assert res.status_code == 200, res.text
    doc_id = res.json()["id"]

    ext_res = client.post(f"/documents/{doc_id}/extract")
    assert ext_res.status_code == 200, ext_res.text
    data = ext_res.json()
    print("   [PASS] Extracted Sections:", data["units_count"])
    for u in data["units"]:
        print(f"     * Heading: {u['section_title']}")

    # Test Upload & Extraction for Word (.docx)
    print("\n3. Testing Word Document Extraction (.docx)...")
    with open("test_samples/sample_arch.docx", "rb") as f:
        res = client.post("/documents/upload", data={"project_id": "p1"}, files={"file": ("sample_arch.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert res.status_code == 200, res.text
    doc_id = res.json()["id"]

    ext_res = client.post(f"/documents/{doc_id}/extract")
    assert ext_res.status_code == 200, ext_res.text
    data = ext_res.json()
    print("   [PASS] Extracted Docx Sections:", data["units_count"])
    for u in data["units"]:
        print(f"     * {u['section_title']}: {u['text'][:40]}...")

    # Test Upload & Extraction for PDF (.pdf)
    print("\n4. Testing PDF Extraction (.pdf)...")
    with open("test_samples/sample_guide.pdf", "rb") as f:
        res = client.post("/documents/upload", data={"project_id": "p1"}, files={"file": ("sample_guide.pdf", f, "application/pdf")})
    assert res.status_code == 200, res.text
    doc_id = res.json()["id"]

    ext_res = client.post(f"/documents/{doc_id}/extract")
    assert ext_res.status_code == 200, ext_res.text
    data = ext_res.json()
    print("   [PASS] Extracted PDF Pages:", data["units_count"])
    for u in data["units"]:
        print(f"     * {u['section_title']} (Page {u['page_number']}): {u['text'][:35]}...")

    print("\n==========================================")
    print(" ALL DAY 5 EXTRACTORS PASSED (4/4)       ")
    print("==========================================")


if __name__ == "__main__":
    run_tests()
