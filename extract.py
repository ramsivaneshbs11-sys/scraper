"""
Simple CLI Document Extractor.
Usage:
    python extract.py <path-to-file>
Examples:
    python extract.py sample_test_documents/upsc_spec_with_tables.docx
    python extract.py sample_test_documents/upsc_spec_with_tables.pdf
    python extract.py sample_test_documents/upsc_chatbot_service.py
    python extract.py sample_test_documents/upsc_syllabus_spec.md
"""

import sys
import os
from app.extractors.service import ExtractionService

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract.py <file_path>")
        print("Example: python extract.py sample_test_documents/upsc_spec_with_tables.docx")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    file_ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    doc_id = os.path.basename(file_path).rsplit(".", 1)[0]

    print(f"\n{'=' * 65}")
    print(f"EXTRACTING: {file_path} (Format: .{file_ext})")
    print(f"{'=' * 65}")

    try:
        res = ExtractionService.extract_document(file_path, file_ext, doc_id)
        print(f"Total Characters : {res.total_characters}")
        print(f"Total Sections   : {len(res.units)}")
        print(f"Metadata         : {res.metadata}")
        print(f"{'-' * 65}")

        output_data = {
            "file_path": file_path,
            "file_type": file_ext,
            "total_characters": res.total_characters,
            "total_sections": len(res.units),
            "metadata": res.metadata,
            "units": []
        }

        for idx, u in enumerate(res.units, 1):
            title = u.section_title or f"Section {idx}"
            pg = f" | Page {u.page_number}" if u.page_number else ""
            lines = f" | Lines {u.line_start}-{u.line_end}" if u.line_start else ""
            print(f"\n>>> [{idx}] {title}{pg}{lines}")
            print(u.text.strip())

            output_data["units"].append({
                "index": idx,
                "section_title": u.section_title,
                "page_number": u.page_number,
                "line_start": u.line_start,
                "line_end": u.line_end,
                "text": u.text.strip()
            })

        # Save to extracted_output.json for easy viewing
        import json
        json_file = "extracted_output.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"\n{'=' * 65}")
        print(f"EXTRACTION SUCCESSFUL! Extracted JSON saved to: {json_file}")
        print(f"{'=' * 65}\n")

    except Exception as e:
        print(f"Error during extraction: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

