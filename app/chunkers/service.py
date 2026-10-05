"""
Smart Chunker Service (Day 6).

Transforms raw extracted units (from PDF, Word, Code, Markdown, Text) into
optimally sized, metadata-enriched chunks ready for vector embedding (Qdrant)
and SQLite database storage.
"""

import uuid
from typing import List, Optional
from app.extractors.base import ExtractionResult, ExtractedUnit
from schemas import ChunkMetadata, ChunkType


class ChunkerService:
    DEFAULT_MAX_CHUNK_SIZE = 800   # maximum characters per chunk
    DEFAULT_OVERLAP = 100          # overlap characters for large text splits

    @classmethod
    def determine_chunk_type(cls, file_type: str) -> ChunkType:
        """Map file format to domain chunk type."""
        ext = file_type.lower().strip(".")
        if ext == "py":
            return ChunkType.CODE
        elif ext in ["md", "docx"]:
            return ChunkType.REQUIREMENT_DOC
        elif ext == "pdf":
            return ChunkType.ARCHITECTURE_DOC
        else:
            return ChunkType.REQUIREMENT_DOC

    @classmethod
    def split_large_text(cls, text: str, max_size: int = DEFAULT_MAX_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[str]:
        """
        Recursively split large text blocks by paragraph or sentence boundaries
        to ensure no single chunk exceeds max_size while retaining overlap context.
        """
        text = text.strip()
        if not text:
            return []
        if len(text) <= max_size:
            return [text]

        sub_chunks = []
        # Try splitting by double newline (paragraphs) first
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 <= max_size:
                current_chunk += ("\n\n" + para) if current_chunk else para
            else:
                if current_chunk:
                    sub_chunks.append(current_chunk)
                # If paragraph itself is too large, split by sentences or sliding window
                if len(para) > max_size:
                    start = 0
                    while start < len(para):
                        end = min(start + max_size, len(para))
                        sub_chunks.append(para[start:end])
                        start += (max_size - overlap)
                    current_chunk = ""
                else:
                    current_chunk = para

        if current_chunk:
            sub_chunks.append(current_chunk)

        return sub_chunks

    @classmethod
    def create_chunks(
        cls,
        document_id: str,
        project_id: str,
        file_type: str,
        extraction_result: ExtractionResult,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
    ) -> List[ChunkMetadata]:
        """
        Converts an ExtractionResult into a list of ChunkMetadata instances.
        Preserves page numbers, section titles, and line numbers.
        """
        chunk_type = cls.determine_chunk_type(file_type)
        chunks: List[ChunkMetadata] = []

        for unit in extraction_result.units:
            text = unit.text.strip()
            if not text:
                continue

            # Split oversized units into manageable chunks
            text_blocks = cls.split_large_text(text, max_size=max_chunk_size)

            for i, block in enumerate(text_blocks):
                # Annotate sub-chunks if a unit was split
                section_title = unit.section_title
                if len(text_blocks) > 1 and section_title:
                    section_title = f"{section_title} (Part {i + 1})"

                chunk = ChunkMetadata(
                    chunk_id=str(uuid.uuid4()),
                    project_id=project_id,
                    document_id=document_id,
                    chunk_type=chunk_type,
                    text=block,
                    source_page=unit.page_number,
                    source_section=section_title,
                    source_line_start=unit.line_start,
                    source_line_end=unit.line_end,
                    embedding_status=False
                )
                chunks.append(chunk)

        return chunks
