"""
RAG Endpoints Router — Day 9.

Exposes the RAG embedding & retrieval pipeline as REST API endpoints.

Endpoints:
  POST /rag/projects/{project_id}/index              — index all project docs
  POST /rag/documents/{document_id}/index            — index a single document
  GET  /rag/projects/{project_id}/status             — check index status
  POST /rag/projects/{project_id}/search             — semantic search
  DELETE /rag/projects/{project_id}/index            — reset the vector index
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.rag import RAGRetriever
from app.rag.qdrant_store import QdrantVectorStore

router = APIRouter(prefix="/rag", tags=["rag"])


# ------------------------------------------------------------------
# Request Models
# ------------------------------------------------------------------

class SearchRequest(BaseModel):
    """Request body for semantic search."""
    query: str
    top_k: int = 5
    score_threshold: float = 0.3
    document_id: Optional[str] = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/documents/{document_id}/index")
def index_document(document_id: str, db: Session = Depends(get_db)):
    """
    Embed and index all chunks for a single document into Qdrant.

    LEARN — this is the 'Indexing' phase of RAG:
      Each chunk's text is converted to a 768-dim vector and stored in
      Qdrant. Later, when we search, Qdrant finds the chunks whose
      vectors are closest to the query vector (semantic similarity).

    Returns:
      - indexed_count: how many chunks were newly embedded
      - qdrant_collection: the collection they were stored in
    """
    try:
        result = RAGRetriever.index_document(document_id, db)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=str(ce))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")


@router.post("/projects/{project_id}/index")
def index_project(project_id: str, db: Session = Depends(get_db)):
    """
    Embed and index all un-indexed chunks for every document in a project.

    Use this after uploading and chunking multiple documents to make
    the entire project searchable via semantic retrieval.
    """
    try:
        result = RAGRetriever.index_all_project_documents(project_id, db)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=str(ce))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project indexing failed: {e}")


@router.get("/projects/{project_id}/status")
def get_rag_status(project_id: str, db: Session = Depends(get_db)):
    """
    Returns the RAG readiness status for a project.

    Shows:
      - How many chunks are in SQLite (total vs. indexed)
      - Whether Qdrant collection exists and how many points it has
      - Whether the project is ready for semantic retrieval

    LEARN — check this before running test case generation to confirm
      your documents are properly indexed.
    """
    try:
        status = RAGRetriever.get_index_status(project_id, db)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/search")
def semantic_search(
    project_id: str,
    request: SearchRequest,
    db: Session = Depends(get_db)
):
    """
    Finds the most semantically relevant chunks for a query.

    LEARN — this demonstrates the full RAG retrieval loop:
      1. Your query text is embedded into a 768-dim vector.
      2. Qdrant finds the stored chunk vectors with highest cosine similarity.
      3. Results are returned with scores and source metadata.

    Example request body:
      {
        "query": "user must authenticate before accessing protected resources",
        "top_k": 5,
        "score_threshold": 0.3
      }

    Returns top-K chunks from your documents that are most relevant to the query.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        results = RAGRetriever.retrieve(
            project_id=project_id,
            query=request.query,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            document_id=request.document_id
        )
        return {
            "project_id": project_id,
            "query": request.query,
            "results_count": len(results),
            "results": results
        }
    except ConnectionError as ce:
        raise HTTPException(status_code=503, detail=str(ce))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@router.delete("/projects/{project_id}/index")
def reset_index(project_id: str):
    """
    Deletes the Qdrant collection for a project, resetting the vector index.
    """
    try:
        result = QdrantVectorStore.delete_collection(project_id)
        return {"status": "success", "detail": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")


# ------------------------------------------------------------------
# Interactive AI QA Copilot Chat & Dynamic Test Ingestion
# ------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    top_k: int = 4
    score_threshold: float = 0.2


@router.post("/projects/{project_id}/chat")
def rag_copilot_chat(
    project_id: str,
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    RAG-grounded AI QA Copilot Chat endpoint.

    Capabilities:
      1. Answers QA architecture & requirement questions grounded in RAG chunks.
      2. Dynamically creates & injects new test cases live into SQLite when requested!
    """
    import uuid
    import re
    from app import models

    msg_lower = request.message.strip().lower()
    if not msg_lower:
        raise HTTPException(status_code=400, detail="Chat message cannot be empty.")

    # 1. Retrieve RAG context chunks
    results = []
    try:
        results = RAGRetriever.retrieve(
            project_id=project_id,
            query=request.message,
            top_k=request.top_k,
            score_threshold=request.score_threshold
        )
    except Exception:
        # Fallback to SQLite chunks if Qdrant offline
        chunks = db.query(models.Chunk).filter(models.Chunk.project_id == project_id).limit(4).all()
        results = [{"chunk_id": c.chunk_id, "text": c.text, "section": c.source_section, "score": 0.8} for c in chunks]

    sources_summary = []
    chunk_ids = []
    for r in results:
        cid = r.get("chunk_id") or r.get("id")
        if cid:
            chunk_ids.append(cid)
            sources_summary.append(f"[{cid}] {r.get('text', '')[:100]}...")

    # 2. Check if intent is to create / add a new test case
    is_add_test = any(kw in msg_lower for kw in ["add test", "create test", "generate test", "add a test", "new scenario", "test case", "add scenario"])

    if is_add_test:
        # Infer test type
        test_type = "POSITIVE"
        if any(kw in msg_lower for kw in ["security", "auth", "token", "injection", "permission"]):
            test_type = "SECURITY"
        elif any(kw in msg_lower for kw in ["error", "fail", "invalid", "expire", "reject", "negative", "404", "422", "500"]):
            test_type = "NEGATIVE"
        elif any(kw in msg_lower for kw in ["boundary", "limit", "max", "min", "overflow"]):
            test_type = "BOUNDARY"
        elif any(kw in msg_lower for kw in ["performance", "latency", "load", "sla", "p95", "speed"]):
            test_type = "PERFORMANCE"

        # Find linked requirement or default
        reqs = db.query(models.Requirement).filter(models.Requirement.project_id == project_id).all()
        req_id = reqs[0].id if reqs else "REQ-CUSTOM-01"

        tc_id = str(uuid.uuid4())
        tc_title = f"[{test_type}] {request.message[:80]}"
        
        step_1 = f"1. Initiate scenario: {request.message}"
        step_2 = "2. Send test payload grounded in retrieved specification context."
        step_3 = "3. Verify system status code and acceptance criteria."
        crit = "System responds as specified without unhandled exceptions."
        if test_type == "NEGATIVE":
            crit = "System rejects request with HTTP 400/422 and clear error body."
        elif test_type == "SECURITY":
            crit = "Access is forbidden with HTTP 401/403 or path is safely sanitized."

        steps_json = [step_1, step_2, step_3, f"[ACCEPTANCE CRITERIA] {crit}"]
        if chunk_ids:
            steps_json.append(f"[RAG SOURCES] {', '.join(chunk_ids[:3])}")

        new_tc = models.TestCase(
            id=tc_id,
            project_id=project_id,
            title=tc_title,
            preconditions="Target application is running and accessible.",
            steps=steps_json,
            expected_result=f"Verified: {crit}",
            priority="P1",
            linked_requirement_ids=[req_id],
            status="approved"
        )
        db.add(new_tc)
        db.commit()

        reply_text = (
            f"✅ **New Test Case Dynamically Created & Injected!**\n\n"
            f"- **Title**: `{tc_title}`\n"
            f"- **Type**: `{test_type}` | **Priority**: `P1` | **Status**: `Approved`\n"
            f"- **Acceptance Criterion**: *{crit}*\n"
            f"- **RAG Grounding**: Grounded in {len(chunk_ids)} source chunks.\n\n"
            f"The test case is now live in your **Test Studio** workspace grid!"
        )

        return {
            "project_id": project_id,
            "user_message": request.message,
            "reply": reply_text,
            "action_taken": "test_case_added",
            "rag_sources": results,
            "created_test_case": {
                "id": tc_id,
                "title": tc_title,
                "test_type": test_type,
                "priority": "P1",
                "status": "approved",
                "linked_requirement_ids": [req_id]
            }
        }

    # 3. Standard RAG Knowledge QA Reply
    if results:
        snippet_text = "\n\n".join([f"• [{r.get('chunk_id','source')}] {r.get('text','')[:200]}..." for r in results[:3]])
        reply_text = (
            f"Based on your project documentation and vector store:\n\n"
            f"{snippet_text}\n\n"
            f"💡 *Tip: Type 'Add a negative test case for...' to dynamically inject new scenarios into your Test Studio grid!*"
        )
    else:
        reply_text = (
            f"I analyzed your request: '{request.message}'.\n\n"
            f"No direct vector match found, but I can dynamically create test cases for this scenario. "
            f"Try asking: *'Create a security test case for {request.message}'*."
        )

    return {
        "project_id": project_id,
        "user_message": request.message,
        "reply": reply_text,
        "action_taken": None,
        "rag_sources": results
    }

