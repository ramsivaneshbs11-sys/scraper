"""
Base data structures for document extractors.
Standardizes the output of PDF, Word, Code, and Text extraction.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ExtractedUnit:
    """A single logical segment of extracted content (e.g. a page, a section, or a function)."""
    text: str
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None


@dataclass
class ExtractionResult:
    """The complete extraction outcome for a document."""
    document_id: str
    file_type: str
    units: List[ExtractedUnit]
    total_characters: int
    metadata: Dict[str, Any] = field(default_factory=dict)
