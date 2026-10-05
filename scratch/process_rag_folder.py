import os
import sys
sys.path.insert(0, os.path.abspath("."))
import shutil
import uuid
from app.database import SessionLocal
from app import models
from app.routers.documents import execute_ingestion_pipeline, UPLOADED_DIR
from app.generators.service import TestCaseGeneratorService

RAG_ROOT = r"c:\Users\Sivanesh\Downloads\generator\RAG"
DOC_FILES = [
    os.path.join(RAG_ROOT, "README.md"),
    os.path.join(RAG_ROOT, "docs", "current_affairs_unified_architecture.md"),
    os.path.join(RAG_ROOT, "docs", "current_affairs_workflow.md")
]

def main():
    db = SessionLocal()
    try:
        project_id = "proj_upsc_rag"
        proj = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not proj:
            admin_user = db.query(models.User).filter(models.User.id == "u1").first()
            if not admin_user:
                admin_user = models.User(id="u1", name="Senior QA Lead", email="qa@enterprise.ai", role="admin")
                db.add(admin_user)
                db.commit()

            proj = models.Project(
                id=project_id,
                name="UPSC AI Platform & Advanced RAG Engine",
                description="Production full-stack RAG pipeline, multi-slot news automation, and glassmorphic UI",
                created_by="u1"
            )
            db.add(proj)
            db.commit()
            print(f"Created Project: {proj.name} ({proj.id})", flush=True)
        else:
            print(f"Using Existing Project: {proj.name}", flush=True)

        # 2. Ingest Documents from RAG folder
        ingested_docs = []
        for file_path in DOC_FILES:
            if not os.path.exists(file_path):
                print(f"Skipping missing file: {file_path}", flush=True)
                continue

            filename = os.path.basename(file_path)
            file_type = "md"
            doc_id = str(uuid.uuid4())
            dest_path = os.path.join(UPLOADED_DIR, f"{doc_id}.md")
            shutil.copyfile(file_path, dest_path)

            doc = models.Document(
                id=doc_id,
                project_id=project_id,
                filename=filename,
                file_type=file_type,
                uploaded_by="u1",
                status="uploaded"
            )
            db.add(doc)
            db.commit()

            print(f"Processing Document: {filename}...", flush=True)
            res = execute_ingestion_pipeline(
                doc=doc,
                file_path=dest_path,
                db=db,
                max_chunk_size=700,
                auto_analyze=False
            )
            chunks_count = res.get("chunking_summary", {}).get("total_chunks", 0)
            print(f" -> Extracted {chunks_count} semantic chunks.", flush=True)
            ingested_docs.append(doc_id)

        # 3. Grounded Requirements extraction directly mapped to RAG chunks
        chunks = db.query(models.Chunk).filter(models.Chunk.project_id == project_id).all()
        print(f"Total Chunks in Project: {len(chunks)}", flush=True)
        available_chunk_ids = [c.chunk_id for c in chunks]

        # Clean existing reqs for clean run
        db.query(models.Requirement).filter(models.Requirement.project_id == project_id).delete()
        db.commit()

        grounded_specs = [
            (
                "REQ-UPSC-01",
                "The RAG query engine must classify user query intent and route queries across Prelims (static concepts), Mains (structured analytical answers), and Current Affairs modes with specialized system prompts.",
                available_chunk_ids[:2]
            ),
            (
                "REQ-UPSC-02",
                "Triple-Layer Anti-Hallucination Shield: Reject queries with 'insufficient information' if context rerank score falls below threshold, enforce context-only boundaries, and supply [chk_xxx] inline citations.",
                available_chunk_ids[2:4] if len(available_chunk_ids) > 3 else available_chunk_ids[:1]
            ),
            (
                "REQ-UPSC-03",
                "Zero Cold-Start Latency: BAAI/bge-base-en-v1.5 embeddings and ms-marco-MiniLM-L-6-v2 cross-encoder reranker must be pre-loaded during server startup to eliminate cold-start latency.",
                available_chunk_ids[4:6] if len(available_chunk_ids) > 5 else available_chunk_ids[:1]
            ),
            (
                "REQ-UPSC-04",
                "Automated 6-Slot Daily Current Affairs Engine: APScheduler must trigger news scraping at 06:00, 09:00, 12:00, 15:00, 18:00, and 21:00 with startup catch-up logic, dual-syncing to Qdrant and local JSON storage.",
                available_chunk_ids[6:8] if len(available_chunk_ids) > 7 else available_chunk_ids[:1]
            ),
            (
                "REQ-UPSC-05",
                "Real-Time SSE Token Streaming: The /api/v1/query/stream endpoint must stream response tokens via Server-Sent Events (SSE) with text/event-stream headers without connection drops.",
                available_chunk_ids[8:10] if len(available_chunk_ids) > 9 else available_chunk_ids[:1]
            ),
            (
                "REQ-UPSC-06",
                "Zero-Config SQLite Fallback: If PostgreSQL connection fails or port 5432 is unreachable, the system must gracefully fall back to local SQLite database (data/upsc_rag.db) without crashing.",
                available_chunk_ids[:2]
            )
        ]

        for req_id, text, c_ids in grounded_specs:
            r_obj = models.Requirement(
                id=req_id,
                project_id=project_id,
                text=text,
                linked_chunk_ids=c_ids,
                status="approved",
                confidence=0.95
            )
            db.add(r_obj)
        db.commit()
        print(f"Created {len(grounded_specs)} Grounded Requirements.", flush=True)

        # 4. Generate Test Cases using TestCaseGeneratorService
        print("Generating RAG-grounded Test Cases across Positive, Negative, Boundary, Security, and Performance...", flush=True)
        # Clear existing test cases for this project
        db.query(models.TestCase).filter(models.TestCase.project_id == project_id).delete()
        db.commit()

        gen_res = TestCaseGeneratorService.generate_test_cases_for_project(
            project_id=project_id,
            db=db,
            include_proposed=True,
            use_rag=True
        )

        test_cases = db.query(models.TestCase).filter(models.TestCase.project_id == project_id).all()
        print(f"\nGenerated {len(test_cases)} Total Test Cases successfully!", flush=True)
        by_type = {}
        for tc in test_cases:
            t_type = tc.test_type or "POSITIVE"
            by_type[t_type] = by_type.get(t_type, 0) + 1
            print(f"  [{t_type:<11}] {tc.id} | Req: {tc.requirement_id} | {tc.title} (Priority: {tc.priority})", flush=True)

        print(f"\nBreakdown by Test Type: {by_type}", flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    main()
