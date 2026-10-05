"""
Plain text and Markdown extractor.
Splits markdown files by headings, and plain text files by paragraphs.
"""

from typing import List
from app.extractors.base import ExtractedUnit, ExtractionResult


class TextExtractor:
    @staticmethod
    def extract(file_path: str, document_id: str, file_type: str = "txt") -> ExtractionResult:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        units: List[ExtractedUnit] = []
        lines = content.splitlines()

        if file_type == "md":
            # Heading-aware splitting for Markdown
            current_section = "Overview"
            current_buffer: List[str] = []

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    if current_buffer:
                        units.append(
                            ExtractedUnit(
                                text="\n".join(current_buffer).strip(),
                                section_title=current_section,
                            )
                        )
                        current_buffer = []
                    current_section = stripped.lstrip("#").strip()
                else:
                    current_buffer.append(line)

            if current_buffer:
                units.append(
                    ExtractedUnit(
                        text="\n".join(current_buffer).strip(),
                        section_title=current_section,
                    )
                )
        else:
            # Plain text splitting by double newlines (paragraphs)
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            for idx, p in enumerate(paragraphs):
                units.append(
                    ExtractedUnit(
                        text=p,
                        section_title=f"Paragraph {idx + 1}",
                    )
                )

        if not units and content.strip():
            units.append(ExtractedUnit(text=content.strip(), section_title="Content"))

        return ExtractionResult(
            document_id=document_id,
            file_type=file_type,
            units=units,
            total_characters=len(content),
            metadata={"sections_count": len(units)},
        )
