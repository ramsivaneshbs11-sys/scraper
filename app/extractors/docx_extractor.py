"""
Word (.docx) extractor using python-docx.
Extracts text while preserving document section hierarchy based on headings,
and converts Word tables into formatted Markdown tables.
"""

from typing import List
import docx
from docx.text.paragraph import Paragraph
from docx.table import Table
from app.extractors.base import ExtractedUnit, ExtractionResult


class DocxExtractor:
    @staticmethod
    def _table_to_markdown(table: Table) -> str:
        """Convert a python-docx Table into a clean Markdown table string."""
        raw_rows = []
        for row in table.rows:
            row_data = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            # Avoid duplicate merged cell values in row representation
            raw_rows.append(row_data)

        if not raw_rows:
            return ""

        headers = raw_rows[0]
        col_count = len(headers)
        
        md_lines = []
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * col_count) + " |")
        
        for r in raw_rows[1:]:
            # Pad row if fewer cells
            padded = r + [""] * (col_count - len(r))
            md_lines.append("| " + " | ".join(padded[:col_count]) + " |")

        return "\n".join(md_lines)

    @classmethod
    def extract(cls, file_path: str, document_id: str) -> ExtractionResult:
        doc = docx.Document(file_path)
        units: List[ExtractedUnit] = []
        
        current_section = "General"
        current_buffer: List[str] = []
        total_chars = 0
        table_count = 0

        for block in doc.element.body:
            # Paragraph element
            if block.tag.endswith('p'):
                para = Paragraph(block, doc)
                text = para.text.strip()
                if not text:
                    continue

                style_name = para.style.name.lower() if para.style else ""
                if "heading" in style_name:
                    # Flush previous section buffer
                    if current_buffer:
                        section_text = "\n\n".join(current_buffer)
                        total_chars += len(section_text)
                        units.append(
                            ExtractedUnit(
                                text=section_text,
                                section_title=current_section,
                            )
                        )
                        current_buffer = []
                    current_section = text
                else:
                    current_buffer.append(text)

            # Table element
            elif block.tag.endswith('tbl'):
                table = Table(block, doc)
                table_md = cls._table_to_markdown(table)
                if table_md:
                    table_count += 1
                    current_buffer.append(f"\n[Table Content]:\n{table_md}\n")

        # Flush any remaining buffer
        if current_buffer:
            section_text = "\n\n".join(current_buffer)
            total_chars += len(section_text)
            units.append(
                ExtractedUnit(
                    text=section_text,
                    section_title=current_section,
                )
            )

        return ExtractionResult(
            document_id=document_id,
            file_type="docx",
            units=units,
            total_characters=total_chars,
            metadata={"paragraph_count": len(doc.paragraphs), "tables_extracted": table_count},
        )
