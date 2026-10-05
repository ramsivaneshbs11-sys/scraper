"""
Unified Document Extraction Service.
Routes uploaded files to the correct extractor based on file_type.
"""

import os
from app.extractors.base import ExtractionResult
from app.extractors.pdf_extractor import PDFExtractor
from app.extractors.docx_extractor import DocxExtractor
from app.extractors.code_extractor import CodeExtractor
from app.extractors.text_extractor import TextExtractor
from app.extractors.preprocessor import TextPreprocessor


class ExtractionService:
    @classmethod
    def extract_document(cls, file_path: str, file_type: str, document_id: str) -> ExtractionResult:
        """Route to appropriate extractor based on file extension, then sanitize via TextPreprocessor."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found on disk: {file_path}")

        file_type = file_type.lower().lstrip(".")
        is_code = (file_type == "py")

        if file_type == "pdf":
            raw_result = PDFExtractor.extract(file_path, document_id)
        elif file_type == "docx":
            raw_result = DocxExtractor.extract(file_path, document_id)
        elif file_type == "py":
            raw_result = CodeExtractor.extract(file_path, document_id)
        elif file_type in ("txt", "md"):
            raw_result = TextExtractor.extract(file_path, document_id, file_type=file_type)
        else:
            raise ValueError(f"Unsupported file type for extraction: {file_type}")

        # Automatically clean and normalize extracted text before downstream chunking
        cleaned_result = TextPreprocessor.preprocess_result(raw_result, is_code=is_code)
        return cleaned_result

