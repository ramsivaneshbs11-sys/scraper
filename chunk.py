"""
CLI Document Chunker Tool (Day 6).

Usage:
    python chunk.py <path-to-file>
Examples:
    python chunk.py sample_test_documents/upsc_chatbot_service.py
    python chunk.py sample_test_documents/upsc_spec_with_tables.docx
    python chunk.py sample_test_documents/upsc_syllabus_spec.md
    python chunk.py sample_test_documents/upsc_spec_with_tables.pdf
"""

import sys
import os
import json
from app.extractors import ExtractionService
from app.chunkers import ChunkerService


def main():
    if len(sys.argv) < 2:
        print("Usage: python chunk.py <file_path>")
        print("Example: python chunk.py sample_test_documents/upsc_chatbot_service.py")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    file_ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    doc_id = os.path.basename(file_path).rsplit(".", 1)[0]

    print(f"\n{'=' * 70}")
    print(f"CHUNKING DOCUMENT: {file_path} (Format: .{file_ext})")
    print(f"{'=' * 70}")

    try:
        # Step 1: Extraction
        extraction_res = ExtractionService.extract_document(file_path, file_ext, doc_id)

        # Step 2: Smart Chunking
        chunks = ChunkerService.create_chunks(
            document_id=doc_id,
            project_id="p1",
            file_type=file_ext,
            extraction_result=extraction_res
        )

        print(f"Total Extracted Units : {len(extraction_res.units)}")
        print(f"Total Chunks Created  : {len(chunks)}")
        print(f"Chunk Type           : {ChunkerService.determine_chunk_type(file_ext).value}")
        print(f"{'-' * 70}")

        json_chunks = []
        for idx, c in enumerate(chunks, 1):
            sec = f" | Section: {c.source_section}" if c.source_section else ""
            pg = f" | Page: {c.source_page}" if c.source_page else ""
            lines = f" | Lines: {c.source_line_start}-{c.source_line_end}" if c.source_line_start else ""

            print(f"\n>>> [Chunk {idx}/{len(chunks)}]{sec}{pg}{lines}")
            print(f"Text ({len(c.text)} chars):\n{c.text.strip()}")

            json_chunks.append({
                "chunk_id": c.chunk_id,
                "chunk_type": c.chunk_type.value,
                "source_section": c.source_section,
                "source_page": c.source_page,
                "source_line_start": c.source_line_start,
                "source_line_end": c.source_line_end,
                "text_length": len(c.text),
                "text": c.text
            })

        # Export to chunked_output.json
        output_file = "chunked_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "file_path": file_path,
                "file_type": file_ext,
                "total_chunks": len(chunks),
                "chunks": json_chunks
            }, f, indent=2, ensure_ascii=False)

        print(f"\n{'=' * 70}")
        print(f"CHUNKING SUCCESSFUL! Results saved to: {output_file}")
        print(f"{'=' * 70}\n")

    except Exception as e:
        print(f"Error during chunking: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
