"""
Day 9 Tests — RAG: Embedding Client + Qdrant Store + Retriever.

Tests are structured in layers so you can learn what each component does:

Layer 1: EmbeddingClient (pure Python, no I/O)
Layer 2: QdrantVectorStore (requires Qdrant running on Docker)
Layer 3: RAGRetriever (full integration with SQLite + Qdrant)
Layer 4: RAG API Endpoints (via FastAPI TestClient)

Run all tests:   pytest tests/test_day9.py -v
Run offline only: pytest tests/test_day9.py -v -m "not requires_qdrant"
"""

import pytest
import math
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

# -------------------------------------------------------------------
# Test DB Setup
# -------------------------------------------------------------------

TEST_DB_URL = "sqlite:///./test_day9.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


client = TestClient(app)


# -------------------------------------------------------------------
# LAYER 1: EmbeddingClient — offline tests (no API key needed)
# -------------------------------------------------------------------

class TestEmbeddingClientFallback:
    """
    Tests for the deterministic fallback vector.
    These run 100% offline — no Gemini API key needed.

    LEARN: The fallback uses MD5 hashing to map words to vector positions.
    Same text → same vector (deterministic).
    Similar texts → similar vectors (semantic proximity).
    """

    def test_fallback_produces_768_dim_vector(self):
        """Fallback must always return exactly 768 numbers."""
        from app.rag.embedding_client import EmbeddingClient
        vec = EmbeddingClient._fallback_vector("the user must login to access the system")
        assert len(vec) == 768, f"Expected 768 dimensions, got {len(vec)}"

    def test_fallback_vector_is_unit_length(self):
        """
        The fallback vector must be L2-normalized (unit length).
        LEARN: Normalizing ensures cosine similarity = dot product.
        An un-normalized vector would give wrong similarity scores.
        """
        from app.rag.embedding_client import EmbeddingClient
        vec = EmbeddingClient._fallback_vector("authentication and authorization requirements")
        magnitude = math.sqrt(sum(v * v for v in vec))
        assert abs(magnitude - 1.0) < 1e-6, f"Vector not normalized: magnitude = {magnitude}"

    def test_fallback_is_deterministic(self):
        """Same text must always produce exactly the same vector."""
        from app.rag.embedding_client import EmbeddingClient
        text = "The system shall validate user credentials before granting access."
        vec1 = EmbeddingClient._fallback_vector(text)
        vec2 = EmbeddingClient._fallback_vector(text)
        assert vec1 == vec2, "Fallback vector is non-deterministic!"

    def test_different_texts_produce_different_vectors(self):
        """Two semantically different texts must NOT produce identical vectors."""
        from app.rag.embedding_client import EmbeddingClient
        v1 = EmbeddingClient._fallback_vector("login authentication password")
        v2 = EmbeddingClient._fallback_vector("database migration schema alter")
        assert v1 != v2, "Different texts produced identical vectors — fallback is broken."

    def test_embed_uses_fallback_without_api_key(self):
        """
        EmbeddingClient.embed() must use fallback when GEMINI_API_KEY is absent.
        LEARN: This proves the pipeline is resilient to missing credentials.
        """
        from app.rag.embedding_client import EmbeddingClient
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            vec = EmbeddingClient.embed("test text without API key")
        assert len(vec) == 768
        assert all(isinstance(v, float) for v in vec)

    def test_embed_batch_returns_one_vector_per_text(self):
        """embed_batch must return exactly as many vectors as input texts."""
        from app.rag.embedding_client import EmbeddingClient
        texts = ["first chunk text", "second chunk text", "third chunk text"]
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            vecs = EmbeddingClient.embed_batch(texts)
        assert len(vecs) == 3
        for v in vecs:
            assert len(v) == 768


# -------------------------------------------------------------------
# LAYER 2: QdrantVectorStore — utility tests (no I/O)
# -------------------------------------------------------------------

class TestQdrantUtilities:
    """
    Tests for utility methods that don't need a running Qdrant instance.
    """

    def test_collection_name_from_project_id(self):
        """Collection names replace hyphens with underscores for Qdrant compatibility."""
        from app.rag.qdrant_store import QdrantVectorStore
        name = QdrantVectorStore.collection_name("proj-abc-123")
        assert name == "project_proj_abc_123"
        assert "-" not in name

    def test_chunk_id_to_int_is_stable(self):
        """
        The same chunk_id must always map to the same integer.
        LEARN: Qdrant needs integer IDs. We use MD5 to get a stable mapping.
        """
        from app.rag.qdrant_store import QdrantVectorStore
        id1 = QdrantVectorStore._chunk_id_to_int("chunk-abc-123")
        id2 = QdrantVectorStore._chunk_id_to_int("chunk-abc-123")
        assert id1 == id2

    def test_different_chunk_ids_produce_different_ints(self):
        """Two different chunk_ids must not collide to the same integer."""
        from app.rag.qdrant_store import QdrantVectorStore
        id1 = QdrantVectorStore._chunk_id_to_int("chunk-001")
        id2 = QdrantVectorStore._chunk_id_to_int("chunk-002")
        assert id1 != id2

    def test_chunk_id_int_fits_in_64_bits(self):
        """The integer ID must be a valid unsigned 64-bit value for Qdrant."""
        from app.rag.qdrant_store import QdrantVectorStore
        int_id = QdrantVectorStore._chunk_id_to_int("any-chunk-id")
        assert 0 <= int_id < (2 ** 64)


# -------------------------------------------------------------------
# LAYER 3: Qdrant Integration Tests (require Docker)
# -------------------------------------------------------------------

@pytest.mark.requires_qdrant
class TestQdrantIntegration:
    """
    Integration tests that require Qdrant running on Docker.

    Start Qdrant before running these:
      docker run -p 6333:6333 qdrant/qdrant

    Run: pytest tests/test_day9.py -v -m requires_qdrant
    """

    def test_create_collection(self):
        from app.rag.qdrant_store import QdrantVectorStore
        result = QdrantVectorStore.create_collection("test-project-day9")
        assert result.get("status") in ("created", "already_exists")

    def test_upsert_and_search(self):
        """
        Full round-trip: upsert a vector, then search for it.
        The search should return the same chunk we upserted.
        """
        from app.rag.embedding_client import EmbeddingClient
        from app.rag.qdrant_store import QdrantVectorStore

        project_id = "test-project-day9"
        QdrantVectorStore.create_collection(project_id)

        # Embed a test chunk
        text = "The user must authenticate with a valid password before accessing the dashboard."
        vector = EmbeddingClient.embed(text)
        chunk_id = "test-chunk-auth-001"

        QdrantVectorStore.upsert_chunk(
            project_id=project_id,
            chunk_id=chunk_id,
            vector=vector,
            payload={
                "text": text,
                "document_id": "doc-001",
                "source_section": "Authentication"
            }
        )

        # Search with a semantically similar query
        query_vector = EmbeddingClient.embed("login and password validation")
        results = QdrantVectorStore.search(project_id, query_vector, top_k=1)

        assert len(results) >= 1
        assert results[0]["chunk_id"] == chunk_id
        assert results[0]["score"] > 0.5

    def test_collection_info(self):
        from app.rag.qdrant_store import QdrantVectorStore
        info = QdrantVectorStore.get_collection_info("test-project-day9")
        assert info["exists"] is True
        assert info["points_count"] >= 1

    def test_delete_collection(self):
        from app.rag.qdrant_store import QdrantVectorStore
        result = QdrantVectorStore.delete_collection("test-project-day9")
        assert result["status"] == "deleted"


# -------------------------------------------------------------------
# LAYER 4: API Endpoint Tests (offline — mocks Qdrant)
# -------------------------------------------------------------------

class TestRAGEndpoints:
    """
    Tests for the RAG REST endpoints.

    We mock QdrantVectorStore and EmbeddingClient so these run
    without Docker or a real API key.
    """

    def test_get_rag_status_no_chunks(self):
        """
        GET /rag/projects/{project_id}/status returns 200 with index info.
        For a brand-new project with no chunks, all counts should be 0.
        """
        response = client.get("/rag/projects/nonexistent-proj/status")
        assert response.status_code == 200
        data = response.json()
        assert "sqlite_total_chunks" in data
        assert data["sqlite_total_chunks"] == 0
        assert data["ready_for_retrieval"] is False

    def test_semantic_search_empty_query(self):
        """POST /rag/projects/{project_id}/search with empty query should return 400."""
        response = client.post(
            "/rag/projects/p1/search",
            json={"query": "   ", "top_k": 5}
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    @patch("app.rag.retriever.QdrantVectorStore.search")
    @patch("app.rag.retriever.EmbeddingClient.embed")
    def test_semantic_search_returns_results(self, mock_embed, mock_search):
        """
        POST /rag/projects/{project_id}/search returns chunk results.
        LEARN: We mock embed() and search() so this test runs without
        any external services — this is called 'unit testing with mocks'.
        """
        # Mock returns: fake 768-dim vector
        mock_embed.return_value = [0.1] * 768

        # Mock Qdrant search returning two fake chunks
        mock_search.return_value = [
            {"chunk_id": "c1", "score": 0.92, "text": "Auth spec chunk", "document_id": "d1", "section": "Auth"},
            {"chunk_id": "c2", "score": 0.78, "text": "Login flow chunk", "document_id": "d1", "section": "Login"},
        ]

        response = client.post(
            "/rag/projects/p1/search",
            json={"query": "user authentication", "top_k": 5, "score_threshold": 0.3}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["results_count"] == 2
        assert data["results"][0]["score"] == 0.92
        assert data["results"][0]["chunk_id"] == "c1"

    @patch("app.rag.retriever.QdrantVectorStore.delete_collection")
    def test_reset_index(self, mock_delete):
        """DELETE /rag/projects/{project_id}/index resets the vector index."""
        mock_delete.return_value = {"status": "deleted", "collection": "project_p1"}
        response = client.delete("/rag/projects/p1/index")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("app.rag.retriever.RAGRetriever.index_document")
    def test_index_document_endpoint(self, mock_index):
        """POST /rag/documents/{document_id}/index returns indexed_count."""
        mock_index.return_value = {
            "status": "indexed",
            "document_id": "doc-123",
            "indexed_count": 10,
            "qdrant_collection": "project_p1"
        }
        response = client.post("/rag/documents/doc-123/index")
        assert response.status_code == 200
        data = response.json()
        assert data["indexed_count"] == 10
        assert data["status"] == "indexed"
