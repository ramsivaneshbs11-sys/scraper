"""
Requirement Analyzer Service (Day 7).

Coordinates LLM extraction, Pydantic validation against schemas.py,
database persistence into requirements & ambiguities tables, and file audit logs.
"""

import json
import os
import uuid
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app import models
from app.analyzers.llm_client import LLMClient
from schemas import Requirement as PydanticRequirement, Ambiguity as PydanticAmbiguity, RequirementStatus, AmbiguityStatus

ANALYSIS_DIR = os.path.join("storage", "analysis")
os.makedirs(ANALYSIS_DIR, exist_ok=True)


class RequirementAnalyzerService:

    @classmethod
    def analyze_document(
        cls,
        document_id: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Analyzes chunks for a given document:
        1. Fetches chunks from database or storage/chunks/<document_id>.json
        2. Calls LLM to extract testable requirements and ambiguities
        3. Validates every item with Pydantic schemas (schemas.py)
        4. Saves rows into SQLite requirements and ambiguities tables
        5. Saves audit file to storage/analysis/<document_id>.json
        """
        doc = db.query(models.Document).filter(models.Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found in database.")

        # 1. Fetch chunks
        chunks = db.query(models.Chunk).filter(models.Chunk.document_id == document_id).all()
        if not chunks:
            # Check chunks JSON on disk as backup
            chunk_file = os.path.join("storage", "chunks", f"{document_id}.json")
            if os.path.exists(chunk_file):
                with open(chunk_file, "r", encoding="utf-8") as f:
                    chunk_data = json.load(f)
                    chunks = chunk_data.get("chunks", [])

        if not chunks:
            raise ValueError(f"No chunks found for document {document_id}. Run chunking first.")

        # 2. Call LLM Client (Gemini API with fallback)
        raw_analysis = LLMClient.analyze_chunks(chunks)

        # 3. Pydantic Schema Validation & DB Mapping
        validated_requirements: List[models.Requirement] = []
        validated_ambiguities: List[models.Ambiguity] = []

        # Clear old analysis results for this document to allow clean re-analysis
        # (Requirements linked to this document's chunks)
        chunk_ids = {getattr(c, "chunk_id", None) or c.get("chunk_id") for c in chunks}

        # Clear old requirements for this document
        existing_reqs = db.query(models.Requirement).filter(models.Requirement.project_id == doc.project_id).all()
        for r in existing_reqs:
            if any(cid in (r.linked_chunk_ids or []) for cid in chunk_ids):
                db.delete(r)

        # Clear old ambiguities for this document
        db.query(models.Ambiguity).filter(models.Ambiguity.project_id == doc.project_id).delete()

        # Validate & Save Requirements
        for req_dict in raw_analysis.get("requirements", []):
            req_id = str(uuid.uuid4())
            req_text = req_dict.get("text", "").strip()
            linked_chunks = req_dict.get("linked_chunk_ids", [])
            confidence = float(req_dict.get("confidence", 0.90))

            # Filter valid linked chunks
            valid_chunk_ids = [cid for cid in linked_chunks if cid in chunk_ids] or list(chunk_ids)[:1]

            # Validate with Pydantic
            pydantic_req = PydanticRequirement(
                id=req_id,
                project_id=doc.project_id,
                text=req_text,
                linked_chunk_ids=valid_chunk_ids,
                status=RequirementStatus.PROPOSED,
                confidence=min(max(confidence, 0.0), 1.0)
            )

            db_req = models.Requirement(
                id=pydantic_req.id,
                project_id=pydantic_req.project_id,
                text=pydantic_req.text,
                linked_chunk_ids=pydantic_req.linked_chunk_ids,
                status=pydantic_req.status.value,
                confidence=pydantic_req.confidence
            )
            db.add(db_req)
            validated_requirements.append(db_req)

        # Validate & Save Ambiguities
        for amb_dict in raw_analysis.get("ambiguities", []):
            amb_id = str(uuid.uuid4())
            desc = amb_dict.get("description", "").strip()
            clarification = amb_dict.get("suggested_clarification", "").strip()
            if not desc or not clarification:
                continue

            # Validate with Pydantic
            pydantic_amb = PydanticAmbiguity(
                id=amb_id,
                project_id=doc.project_id,
                description=desc,
                related_requirement_ids=[r.id for r in validated_requirements[:1]],
                suggested_clarification=clarification,
                status=AmbiguityStatus.OPEN
            )

            db_amb = models.Ambiguity(
                id=pydantic_amb.id,
                project_id=pydantic_amb.project_id,
                description=pydantic_amb.description,
                related_requirement_ids=pydantic_amb.related_requirement_ids,
                suggested_clarification=pydantic_amb.suggested_clarification,
                status=pydantic_amb.status.value
            )
            db.add(db_amb)
            validated_ambiguities.append(db_amb)

        # Update document status to analyzed
        doc.status = "analyzed"
        db.commit()

        # 4. Save analysis JSON to storage/analysis/<document_id>.json
        analysis_result = {
            "document_id": doc.id,
            "project_id": doc.project_id,
            "filename": doc.filename,
            "total_chunks_analyzed": len(chunks),
            "requirements_count": len(validated_requirements),
            "ambiguities_count": len(validated_ambiguities),
            "requirements": [
                {
                    "id": r.id,
                    "text": r.text,
                    "confidence": r.confidence,
                    "status": r.status,
                    "linked_chunk_ids": r.linked_chunk_ids
                }
                for r in validated_requirements
            ],
            "ambiguities": [
                {
                    "id": a.id,
                    "description": a.description,
                    "suggested_clarification": a.suggested_clarification,
                    "status": a.status
                }
                for a in validated_ambiguities
            ]
        }

        audit_file_path = os.path.join(ANALYSIS_DIR, f"{doc.id}.json")
        with open(audit_file_path, "w", encoding="utf-8") as f:
            json.dump(analysis_result, f, indent=2, ensure_ascii=False)

        analysis_result["audit_file"] = audit_file_path
        return analysis_result
