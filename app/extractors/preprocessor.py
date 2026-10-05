"""
Text Preprocessing & Sanitization Engine.

Cleans and standardizes extracted text before it is saved to JSON
and passed into the chunker.

Operations performed:
1. Unicode normalization (NFKC: converts ligatures, non-breaking spaces \xa0, curly quotes).
2. Line-break dehyphenation (e.g. "re-\nquirement" -> "requirement" common in PDFs).
3. Excessive whitespace & newline collapsing (\n\n\n+ -> \n\n).
4. Null bytes and control character stripping.
5. Code-aware formatting preservation (maintains indentation for Python files).
"""

import re
import unicodedata
from app.extractors.base import ExtractionResult, ExtractedUnit


class TextPreprocessor:

    # Replace smart quotes and dashes with standard ASCII equivalents
    CHAR_REPLACEMENTS = {
        "\u2018": "'",   # left single quotation mark
        "\u2019": "'",   # right single quotation mark
        "\u201c": '"',   # left double quotation mark
        "\u201d": '"',   # right double quotation mark
        "\u2013": "-",   # en dash
        "\u2014": "-",   # em dash
        "\u2026": "...", # ellipsis
        "\u00a0": " ",   # non-breaking space
        "\ufeff": "",    # BOM
    }

    @classmethod
    def clean_text(cls, text: str, is_code: bool = False) -> str:
        """
        Cleans and normalizes text.
        If is_code=True, preserves indentation strictly.
        """
        if not text:
            return ""

        # 1. Strip null bytes and non-printable control chars (except \n, \t)
        text = text.replace("\x00", "").replace("\x0c", "").replace("\r\n", "\n").replace("\r", "\n")

        # 2. Normalize Unicode using NFKC
        text = unicodedata.normalize("NFKC", text)

        # 3. Standardize smart quotes and typographic dashes
        for old, new in cls.CHAR_REPLACEMENTS.items():
            text = text.replace(old, new)

        if is_code:
            # For code, only strip trailing whitespace per line and ensure clean EOF
            lines = [line.rstrip() for line in text.split("\n")]
            cleaned_code = "\n".join(lines).strip()
            return cleaned_code

        # --- Text / Document-specific preprocessing ---

        # 4. De-hyphenate words broken across line breaks (e.g., "imple-\nment" -> "implement")
        text = re.sub(r"(\b[a-zA-Z]{2,})-\n([a-zA-Z]{2,}\b)", r"\1\2", text)

        # 5. Clean up each line: trim leading/trailing whitespace per line
        cleaned_lines = []
        for line in text.split("\n"):
            stripped = line.strip()
            cleaned_lines.append(stripped)

        reconstructed = "\n".join(cleaned_lines)

        # 6. Collapse 3+ consecutive newlines into 2 newlines (preserves paragraph boundaries)
        reconstructed = re.sub(r"\n{3,}", "\n\n", reconstructed)

        # 7. Collapse multiple inline spaces (except within table or list formatting)
        # Replaces sequences of spaces with a single space on lines that are not markdown table lines
        final_lines = []
        for line in reconstructed.split("\n"):
            if not line.startswith("|"):
                line = re.sub(r"[ \t]{2,}", " ", line)
            final_lines.append(line)

        return "\n".join(final_lines).strip()

    @classmethod
    def preprocess_result(cls, result: ExtractionResult, is_code: bool = False) -> ExtractionResult:
        """
        Processes all units inside an ExtractionResult, sanitizing text
        and updating total character counts.
        """
        cleaned_units = []
        total_chars = 0

        for unit in result.units:
            cleaned_text = cls.clean_text(unit.text, is_code=is_code)
            if not cleaned_text:
                continue

            cleaned_units.append(
                ExtractedUnit(
                    text=cleaned_text,
                    page_number=unit.page_number,
                    section_title=unit.section_title,
                    line_start=unit.line_start,
                    line_end=unit.line_end,
                )
            )
            total_chars += len(cleaned_text)

        result.units = cleaned_units
        result.total_characters = total_chars
        result.metadata["preprocessed"] = True
        return result
