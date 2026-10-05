"""
PDF text extractor using PyMuPDF (fitz).
Extracts text and detects tables page-by-page, converting tables into Markdown tables.
"""

from typing import List
import fitz  # PyMuPDF
from app.extractors.base import ExtractedUnit, ExtractionResult


class PDFExtractor:
    @staticmethod
    def _table_to_markdown(rows: List[List[str]]) -> str:
        """Convert a 2D list of table cells into a clean Markdown table."""
        if not rows:
            return ""

        headers = [str(c or "").strip().replace("\n", " ") for c in rows[0]]
        col_count = len(headers)
        
        md_lines = []
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * col_count) + " |")

        for r in rows[1:]:
            clean_cells = [str(c or "").strip().replace("\n", " ") for c in r]
            padded = clean_cells + [""] * (col_count - len(clean_cells))
            md_lines.append("| " + " | ".join(padded[:col_count]) + " |")

        return "\n".join(md_lines)

    @classmethod
    def extract(cls, file_path: str, document_id: str) -> ExtractionResult:
        doc = fitz.open(file_path)
        units: List[ExtractedUnit] = []
        total_chars = 0
        total_tables = 0

        try:
            for page_index, page in enumerate(doc):
                page_number = page_index + 1
                page_content_parts = []

                # 1. Detect and extract structured tables
                tabs = page.find_tables()
                if tabs.tables:
                    for table in tabs:
                        table_data = table.extract()
                        if table_data:
                            total_tables += 1
                            md_table = cls._table_to_markdown(table_data)
                            page_content_parts.append(f"\n[Table Content]:\n{md_table}\n")

                # 2. Extract standard text
                text = page.get_text("text").strip()
                if text:
                    page_content_parts.insert(0, text)

                if not page_content_parts:
                    continue

                full_page_text = "\n\n".join(page_content_parts)
                total_chars += len(full_page_text)
                units.append(
                    ExtractedUnit(
                        text=full_page_text,
                        page_number=page_number,
                        section_title=f"Page {page_number}",
                    )
                )

            return ExtractionResult(
                document_id=document_id,
                file_type="pdf",
                units=units,
                total_characters=total_chars,
                metadata={"page_count": len(doc), "tables_detected": total_tables},
            )
        finally:
            doc.close()
