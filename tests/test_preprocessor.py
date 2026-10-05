"""
Unit tests for TextPreprocessor.
Verifies unicode normalization, dehyphenation, newline collapsing, and code preservation.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.extractors.preprocessor import TextPreprocessor
from app.extractors.base import ExtractionResult, ExtractedUnit


def test_text_cleaning():
    print("\n--- Testing TextPreprocessor ---")

    # 1. Unicode & Smart Quote Normalization
    raw_quote = "“Hello World” ‘test’ \u00a0 spaced—dash"
    cleaned = TextPreprocessor.clean_text(raw_quote, is_code=False)
    assert '“' not in cleaned and '”' not in cleaned
    assert '"Hello World"' in cleaned
    assert "'test'" in cleaned
    assert "\u00a0" not in cleaned
    print("   [PASS] Unicode & quote normalization")

    # 2. De-hyphenation across line breaks
    raw_hyphen = "This is a requi-\nrement document for sys-\ntem testing."
    cleaned = TextPreprocessor.clean_text(raw_hyphen, is_code=False)
    assert "requirement" in cleaned, f"Expected 'requirement', got {cleaned}"
    assert "system" in cleaned, f"Expected 'system', got {cleaned}"
    print("   [PASS] Dehyphenation across line breaks")

    # 3. Excessive newline collapsing
    raw_newlines = "Paragraph 1\n\n\n\n\n\nParagraph 2"
    cleaned = TextPreprocessor.clean_text(raw_newlines, is_code=False)
    assert "\n\n\n" not in cleaned
    assert "Paragraph 1\n\nParagraph 2" == cleaned
    print("   [PASS] Collapsing excessive newlines")

    # 4. Code indentation preservation
    raw_code = "class Test:\n    def run(self):\n        pass\n"
    cleaned = TextPreprocessor.clean_text(raw_code, is_code=True)
    assert "    def run(self):" in cleaned
    assert "        pass" in cleaned
    print("   [PASS] Python code indentation preservation")

    # 5. ExtractionResult preprocessing
    result = ExtractionResult(
        document_id="doc1",
        file_type="md",
        units=[ExtractedUnit(text="Exam\u00a0Guide\n\n\n\nSection\u2014One")],
        total_characters=30
    )
    processed = TextPreprocessor.preprocess_result(result, is_code=False)
    assert processed.metadata["preprocessed"] is True
    assert "\u00a0" not in processed.units[0].text
    assert "\n\n\n" not in processed.units[0].text
    print("   [PASS] ExtractionResult batch processing")

    print("\n==========================================")
    print(" ALL PREPROCESSOR TESTS PASSED (5/5)      ")
    print("==========================================\n")


if __name__ == "__main__":
    test_text_cleaning()
