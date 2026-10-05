"""
Python code extractor using the standard library `ast` module.

Safely parses Python code as inert text without executing it.
Extracts functions, classes, and module docstrings along with line numbers.
"""

import ast
from typing import List
from app.extractors.base import ExtractedUnit, ExtractionResult


class CodeExtractor:
    @staticmethod
    def extract(file_path: str, document_id: str) -> ExtractionResult:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            code_text = f.read()

        lines = code_text.splitlines()
        units: List[ExtractedUnit] = []
        total_chars = 0

        try:
            tree = ast.parse(code_text, filename=file_path)
        except SyntaxError as e:
            # If code has syntax errors, fall back to extracting the whole file as text
            return ExtractionResult(
                document_id=document_id,
                file_type="py",
                units=[
                    ExtractedUnit(
                        text=code_text,
                        section_title="Raw Source (Syntax Error)",
                        line_start=1,
                        line_end=len(lines),
                    )
                ],
                total_characters=len(code_text),
                metadata={"error": f"Syntax error on line {e.lineno}"},
            )

        # 1. Module Docstring if present
        module_doc = ast.get_docstring(tree)
        if module_doc:
            total_chars += len(module_doc)
            units.append(
                ExtractedUnit(
                    text=f"Module Documentation:\n{module_doc}",
                    section_title="Module Docstring",
                    line_start=1,
                    line_end=len(module_doc.splitlines()),
                )
            )

        # 2. Extract top-level Functions and Classes
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = node.lineno
                end = getattr(node, "end_lineno", start)
                snippet = "\n".join(lines[start - 1 : end])
                kind = "Class" if isinstance(node, ast.ClassDef) else "Function"
                title = f"{kind}: {node.name}"
                
                total_chars += len(snippet)
                units.append(
                    ExtractedUnit(
                        text=snippet,
                        section_title=title,
                        line_start=start,
                        line_end=end,
                    )
                )

        # If no functions/classes found (e.g. script with only top-level code)
        if not units:
            total_chars = len(code_text)
            units.append(
                ExtractedUnit(
                    text=code_text,
                    section_title="Main Script",
                    line_start=1,
                    line_end=len(lines),
                )
            )

        return ExtractionResult(
            document_id=document_id,
            file_type="py",
            units=units,
            total_characters=total_chars,
            metadata={"total_lines": len(lines), "definitions_count": len(units)},
        )
