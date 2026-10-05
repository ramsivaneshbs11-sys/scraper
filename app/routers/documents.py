"""
Document upload endpoint.

Day 4 scope: accept a file, validate its type, save it to disk, and create
a row in the `documents` table. No text extraction yet (that's Day 5).
"""

import json
import os
import uuid
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models
from app.api_schemas import DocumentResponse
from app.extractors import ExtractionService
from app.chunkers import ChunkerService

router = APIRouter(prefix="/documents", tags=["documents"])

STORAGE_DIR = "storage"
UPLOADED_DIR = os.path.join(STORAGE_DIR, "uploaded")
EXTRACTED_DIR = os.path.join(STORAGE_DIR, "extracted")
CHUNKS_DIR = os.path.join(STORAGE_DIR, "chunks")

for d in [STORAGE_DIR, UPLOADED_DIR, EXTRACTED_DIR, CHUNKS_DIR]:
    os.makedirs(d, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "docx", "py", "txt", "md"}


def get_uploaded_file_path(doc_id: str, file_type: str) -> str:
    """Returns path in uploaded/ with fallback to root storage/ for backward compatibility."""
    path = os.path.join(UPLOADED_DIR, f"{doc_id}.{file_type}")
    if os.path.exists(path):
        return path
    legacy_path = os.path.join(STORAGE_DIR, f"{doc_id}.{file_type}")
    return legacy_path


def execute_ingestion_pipeline(
    doc: models.Document,
    file_path: str,
    db: Session,
    max_chunk_size: int = 800,
    auto_analyze: bool = True
) -> dict:

    """
    Unified end-to-end ingestion:
    1. Text & Table Extraction
    2. Text Preprocessing & Sanitization (Unicode, dehyphenation, newline compaction)
    3. Semantic Chunking (Output of Extraction is the direct Input to Chunker)
    4. Save to storage/extracted/<id>.json & storage/chunks/<id>.json
    5. Persist Chunks into SQLite DB and update document status to 'chunked'
    """
    doc.status = "processing"
    db.commit()

    # Step 1 & 2: Extraction & Preprocessing
    extraction_res = ExtractionService.extract_document(file_path, doc.file_type, doc.id)

    # Save preprocessed JSON to storage/extracted/<doc_id>.json
    extracted_data = {
        "document_id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "total_characters": extraction_res.total_characters,
        "units_count": len(extraction_res.units),
        "metadata": extraction_res.metadata,
        "units": [
            {
                "section_title": u.section_title,
                "page_number": u.page_number,
                "line_start": u.line_start,
                "line_end": u.line_end,
                "text": u.text,
            }
            for u in extraction_res.units
        ],
    }
    extracted_file_path = os.path.join(EXTRACTED_DIR, f"{doc.id}.json")
    with open(extracted_file_path, "w", encoding="utf-8") as f:
        json.dump(extracted_data, f, indent=2, ensure_ascii=False)

    # Step 3: Chunking (Extraction output directly feeds Chunker input)
    chunk_metadatas = ChunkerService.create_chunks(
        document_id=doc.id,
        project_id=doc.project_id,
        file_type=doc.file_type,
        extraction_result=extraction_res,
        max_chunk_size=max_chunk_size
    )

    # Save chunked JSON to storage/chunks/<doc_id>.json
    chunks_data = {
        "document_id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "total_chunks": len(chunk_metadatas),
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "project_id": c.project_id,
                "document_id": c.document_id,
                "chunk_type": c.chunk_type.value,
                "source_section": c.source_section,
                "source_page": c.source_page,
                "source_line_start": c.source_line_start,
                "source_line_end": c.source_line_end,
                "text_length": len(c.text),
                "text": c.text,
                "embedding_status": c.embedding_status,
            }
            for c in chunk_metadatas
        ],
    }
    chunks_file_path = os.path.join(CHUNKS_DIR, f"{doc.id}.json")
    with open(chunks_file_path, "w", encoding="utf-8") as f:
        json.dump(chunks_data, f, indent=2, ensure_ascii=False)

    # Step 4: Persist chunks to SQLite database
    db.query(models.Chunk).filter(models.Chunk.document_id == doc.id).delete()
    db_chunks = []
    for c in chunk_metadatas:
        db_chunk = models.Chunk(
            chunk_id=c.chunk_id,
            project_id=c.project_id,
            document_id=c.document_id,
            chunk_type=c.chunk_type.value,
            text=c.text,
            source_page=c.source_page,
            source_section=c.source_section,
            source_line_start=c.source_line_start,
            source_line_end=c.source_line_end,
            embedding_status=c.embedding_status
        )
        db.add(db_chunk)
        db_chunks.append(db_chunk)

    doc.status = "chunked"
    db.commit()

    # Step 5: Continuous AI Requirement & Ambiguity Analysis
    stages = ["extraction", "preprocessing", "chunking", "database_save"]
    analysis_res = None
    if auto_analyze:
        try:
            from app.analyzers import RequirementAnalyzerService
            analysis_res = RequirementAnalyzerService.analyze_document(doc.id, db)
            doc.status = "analyzed"
            db.commit()
            stages.append("requirement_analysis")
        except Exception as e:
            print(f"Auto-analysis warning: {e}")

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "status": doc.status,
        "pipeline_stages_completed": stages,
        "extracted_summary": {
            "total_characters": extraction_res.total_characters,
            "units_count": len(extraction_res.units),
            "preprocessed": True,
            "metadata": extraction_res.metadata,
            "extracted_file": extracted_file_path,
        },
        "chunking_summary": {
            "total_chunks": len(db_chunks),
            "chunks_file": chunks_file_path,
        },
        "requirements_summary": {
            "total_requirements": analysis_res.get("requirements_count", 0) if analysis_res else 0,
            "total_ambiguities": analysis_res.get("ambiguities_count", 0) if analysis_res else 0,
            "audit_file": analysis_res.get("audit_file") if analysis_res else None,
            "requirements": analysis_res.get("requirements", []) if analysis_res else [],
            "ambiguities": analysis_res.get("ambiguities", []) if analysis_res else []
        },
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "chunk_type": c.chunk_type,
                "source_section": c.source_section,
                "source_page": c.source_page,
                "source_line_start": c.source_line_start,
                "source_line_end": c.source_line_end,
                "text_length": len(c.text),
                "preview": c.text[:120] + "..." if len(c.text) > 120 else c.text
            }
            for c in db_chunks
        ]
    }



def run_background_extraction(document_id: str, file_path: str, file_type: str):
    """Background runner for unified ingestion."""
    db = SessionLocal()
    try:
        doc = db.query(models.Document).filter(models.Document.id == document_id).first()
        if not doc:
            return
        execute_ingestion_pipeline(doc, file_path, db)
    except Exception as e:
        if doc:
            doc.status = "failed"
            db.commit()
        print(f"Background ingestion failed for document {document_id}: {e}")
    finally:
        db.close()





@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    project_id: str = Form(...),
    uploaded_by: Optional[str] = Form(None),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    # 1. Match project by ID OR by Name (case-insensitive)
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()

    # If placeholder 'string' or empty, default to the first available project
    if not project and project_id in ("string", "", "default"):
        project = db.query(models.Project).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found. Please provide an existing project ID or name.",
        )

    # Resolve uploaded_by automatically if not provided or placeholder
    if not uploaded_by or uploaded_by in ("string", ""):
        if project.created_by:
            uploaded_by = project.created_by
        else:
            default_user = db.query(models.User).first()
            if not default_user:
                default_user = models.User(
                    id=str(uuid.uuid4()),
                    email="admin@example.com",
                    name="Admin User",
                    role="admin"
                )
                db.add(default_user)
                db.commit()
                db.refresh(default_user)
            uploaded_by = default_user.id
    else:
        # If specified user doesn't exist, safely fallback to project owner
        user = db.query(models.User).filter(models.User.id == uploaded_by).first()
        if not user:
            uploaded_by = project.created_by

    # 2. Validate file extension
    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{file_ext}' not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    # 3. Save the file to disk in storage/uploaded/ under a unique name
    document_id = str(uuid.uuid4())
    saved_filename = f"{document_id}.{file_ext}"
    saved_path = os.path.join(UPLOADED_DIR, saved_filename)

    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    # 4. Create the DB row
    doc = models.Document(
        id=document_id,
        project_id=project.id,
        filename=file.filename,       # original name, for display
        file_type=file_ext,
        uploaded_by=uploaded_by,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Automatically trigger background extraction & chunking
    background_tasks.add_task(run_background_extraction, doc.id, saved_path, doc.file_type)

    return doc


@router.post("/ingest")
async def ingest_document(
    project_id: str = Form(...),
    uploaded_by: Optional[str] = Form(None),
    max_chunk_size: int = Form(800),
    auto_analyze: bool = Form(True),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):

    """
    ONE UNIFIED ENDPOINT for Complete Document Ingestion:
    Upload -> Extraction -> Preprocessing -> Chunking -> Filesystem & DB Persistence.
    All stages execute sequentially where the output of each stage feeds the next.
    """
    # 1. Match project by ID OR by Name
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project and project_id in ("string", "", "default"):
        project = db.query(models.Project).first()
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found.",
        )

    # 2. Match or fallback uploaded_by
    if not uploaded_by or uploaded_by in ("string", ""):
        uploaded_by = project.created_by or "u1"

    # 3. Validate file extension
    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{file_ext}' not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    # 4. Save raw file to storage/uploaded/
    document_id = str(uuid.uuid4())
    saved_filename = f"{document_id}.{file_ext}"
    saved_path = os.path.join(UPLOADED_DIR, saved_filename)
    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    # 5. Create initial DB document record
    doc = models.Document(
        id=document_id,
        project_id=project.id,
        filename=file.filename,
        file_type=file_ext,
        uploaded_by=uploaded_by,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 6. Execute Extraction -> Preprocessing -> Chunking -> DB Persistence in one single flow
    try:
        pipeline_result = execute_ingestion_pipeline(
            doc, saved_path, db, max_chunk_size=max_chunk_size, auto_analyze=auto_analyze
        )
        return pipeline_result

    except Exception as e:
        doc.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Ingestion pipeline failed: {str(e)}")


@router.post("/{document_id}/process")
def process_existing_document(
    document_id: str,
    max_chunk_size: int = 800,
    db: Session = Depends(get_db)
):
    """
    Re-run the complete pipeline (Extraction -> Preprocessing -> Chunking -> DB)
    for an existing document in a single call.
    """
    doc = db.query(models.Document).filter(
        (models.Document.id == document_id) | (models.Document.filename == document_id)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = get_uploaded_file_path(doc.id, doc.file_type)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Physical file missing on disk")

    try:
        return execute_ingestion_pipeline(doc, file_path, db, max_chunk_size=max_chunk_size)
    except Exception as e:
        doc.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Processing pipeline failed: {str(e)}")


@router.post("/{document_id}/extract")
def extract_document_endpoint(document_id: str, db: Session = Depends(get_db)):

    """Extract text from an uploaded document, save to storage/extracted/<doc_id>.json and return units."""
    doc = db.query(models.Document).filter(
        (models.Document.id == document_id) | (models.Document.filename == document_id)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = get_uploaded_file_path(doc.id, doc.file_type)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Physical file missing on disk")

    try:
        result = ExtractionService.extract_document(file_path, doc.file_type, doc.id)
        doc.status = "extracted"
        db.commit()

        # Save JSON to storage/extracted/<doc.id>.json
        extracted_data = {
            "document_id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "status": doc.status,
            "total_characters": result.total_characters,
            "units_count": len(result.units),
            "units": [
                {
                    "section_title": u.section_title,
                    "page_number": u.page_number,
                    "line_start": u.line_start,
                    "line_end": u.line_end,
                    "text": u.text,
                }
                for u in result.units
            ],
            "metadata": result.metadata,
        }
        extracted_file_path = os.path.join(EXTRACTED_DIR, f"{doc.id}.json")
        with open(extracted_file_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        return extracted_data
    except Exception as e:
        doc.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Extraction error: {str(e)}")


@router.post("/{document_id}/chunk")
def chunk_document_endpoint(
    document_id: str,
    max_chunk_size: int = 800,
    db: Session = Depends(get_db)
):
    """
    Extracts and chunks an uploaded document, saves to storage/chunks/<doc_id>.json,
    and persists Chunk rows into SQLite database.
    """
    doc = db.query(models.Document).filter(
        (models.Document.id == document_id) | (models.Document.filename == document_id)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = get_uploaded_file_path(doc.id, doc.file_type)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Physical file missing on disk")

    try:
        # 1. Run extraction
        extraction_res = ExtractionService.extract_document(file_path, doc.file_type, doc.id)

        # 2. Save extracted JSON
        extracted_data = {
            "document_id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "total_characters": extraction_res.total_characters,
            "units_count": len(extraction_res.units),
            "metadata": extraction_res.metadata,
            "units": [
                {
                    "section_title": u.section_title,
                    "page_number": u.page_number,
                    "line_start": u.line_start,
                    "line_end": u.line_end,
                    "text": u.text,
                }
                for u in extraction_res.units
            ],
        }
        with open(os.path.join(EXTRACTED_DIR, f"{doc.id}.json"), "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        # 3. Run chunking
        chunk_metadatas = ChunkerService.create_chunks(
            document_id=doc.id,
            project_id=doc.project_id,
            file_type=doc.file_type,
            extraction_result=extraction_res,
            max_chunk_size=max_chunk_size
        )

        # 4. Clear old chunks for this document if re-chunking
        db.query(models.Chunk).filter(models.Chunk.document_id == doc.id).delete()

        # 5. Save new chunk rows to DB
        db_chunks = []
        for c in chunk_metadatas:
            db_chunk = models.Chunk(
                chunk_id=c.chunk_id,
                project_id=c.project_id,
                document_id=c.document_id,
                chunk_type=c.chunk_type.value,
                text=c.text,
                source_page=c.source_page,
                source_section=c.source_section,
                source_line_start=c.source_line_start,
                source_line_end=c.source_line_end,
                embedding_status=c.embedding_status
            )
            db.add(db_chunk)
            db_chunks.append(db_chunk)

        # 6. Save chunked JSON to storage/chunks/<doc.id>.json
        chunks_json_data = {
            "document_id": doc.id,
            "filename": doc.filename,
            "status": "chunked",
            "total_chunks": len(db_chunks),
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "chunk_type": c.chunk_type,
                    "source_section": c.source_section,
                    "source_page": c.source_page,
                    "source_line_start": c.source_line_start,
                    "source_line_end": c.source_line_end,
                    "text_length": len(c.text),
                    "text": c.text,
                }
                for c in db_chunks
            ]
        }
        with open(os.path.join(CHUNKS_DIR, f"{doc.id}.json"), "w", encoding="utf-8") as f:
            json.dump(chunks_json_data, f, indent=2, ensure_ascii=False)

        doc.status = "chunked"
        db.commit()

        return {
            "document_id": doc.id,
            "filename": doc.filename,
            "status": doc.status,
            "total_chunks": len(db_chunks),
            "chunks_file": f"storage/chunks/{doc.id}.json",
            "extracted_file": f"storage/extracted/{doc.id}.json",
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "chunk_type": c.chunk_type,
                    "source_section": c.source_section,
                    "source_page": c.source_page,
                    "source_line_start": c.source_line_start,
                    "source_line_end": c.source_line_end,
                    "text_length": len(c.text),
                    "preview": c.text[:100] + "..." if len(c.text) > 100 else c.text
                }
                for c in db_chunks
            ]
        }

    except Exception as e:
        doc.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Chunking error: {str(e)}")


@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: str, db: Session = Depends(get_db)):
    """Fetch all saved database chunks for a specific document."""
    doc = db.query(models.Document).filter(
        (models.Document.id == document_id) | (models.Document.filename == document_id)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = db.query(models.Chunk).filter(models.Chunk.document_id == doc.id).all()
    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "chunks_count": len(chunks),
        "chunks": chunks
    }



@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    """Fetch document by document UUID or by original filename."""
    doc = db.query(models.Document).filter(
        (models.Document.id == document_id) | (models.Document.filename == document_id)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("", response_model=list[DocumentResponse])
@router.get("/", response_model=list[DocumentResponse], include_in_schema=False)
def list_documents(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    """List documents. If project_id or project name is provided, filter by it. Otherwise, return all documents."""
    if not project_id or project_id in ("string", ""):
        return db.query(models.Document).all()

    # Search projects by ID or Name
    matched_projects = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).all()

    if matched_projects:
        p_ids = [p.id for p in matched_projects]
    return db.query(models.Document).filter(models.Document.project_id == project_id).all()


@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: str, db: Session = Depends(get_db)):
    """Fetch all chunks for a document to inspect in the Knowledge Hub."""
    doc = db.query(models.Document).filter(
        (models.Document.id == document_id) | (models.Document.filename == document_id)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = db.query(models.Chunk).filter(models.Chunk.document_id == doc.id).all()
    return [
        {
            "chunk_id": c.chunk_id,
            "document_id": c.document_id,
            "project_id": c.project_id,
            "chunk_type": c.chunk_type,
            "text": c.text,
            "source_page": c.source_page,
            "source_section": c.source_section,
            "source_line_start": c.source_line_start,
            "source_line_end": c.source_line_end,
            "embedding_status": c.embedding_status,
        }
        for c in chunks
    ]


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """Delete a document by UUID or filename, and remove all files (uploaded, extracted, chunks) from disk."""
    doc = db.query(models.Document).filter(
        (models.Document.id == document_id) | (models.Document.filename == document_id)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 1. Remove raw file from uploaded/
    for folder in [UPLOADED_DIR, STORAGE_DIR]:
        fpath = os.path.join(folder, f"{doc.id}.{doc.file_type}")
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except OSError:
                pass

    # 2. Remove extracted JSON from extracted/
    extracted_path = os.path.join(EXTRACTED_DIR, f"{doc.id}.json")
    if os.path.exists(extracted_path):
        try:
            os.remove(extracted_path)
        except OSError:
            pass

    # 3. Remove chunks JSON from chunks/
    chunks_path = os.path.join(CHUNKS_DIR, f"{doc.id}.json")
    if os.path.exists(chunks_path):
        try:
            os.remove(chunks_path)
        except OSError:
            pass

    # 4. Remove chunks from DB
    db.query(models.Chunk).filter(models.Chunk.document_id == doc.id).delete()

    db.delete(doc)
    db.commit()
    return {"status": "success", "message": f"Document '{doc.filename}' ({doc.id}) and all associated files deleted successfully."}

