"""
Test Case Generator Service — Day 10 (RAG-Powered Upgrade).

Day 10 upgrades over the Day 7 version:
  1. Uses Qdrant semantic retrieval (Day 9 RAGRetriever) to find the MOST
     RELEVANT source chunks for each requirement, rather than only the
     chunk_ids already stored in the requirements table.
  2. Passes richer RAG context (with similarity scores) to the LLM prompt.
  3. Persists two new fields per test case:
       - test_type        : POSITIVE / NEGATIVE / BOUNDARY / SECURITY / PERFORMANCE
       - acceptance_criteria : one-line measurable criterion
  4. Falls back gracefully if Qdrant is not running (uses SQLite chunk IDs).
  5. Tags each test case with its source rag_chunk_ids for full traceability.

LEARN — why RAG makes test generation better:
  Without RAG:
    Requirement: "User must authenticate before accessing resources."
    LLM Output: "Verify that user authentication works." (too generic)

  With RAG (chunks retrieved from your actual spec):
    Chunk 1: "Authentication uses JWT tokens with 1-hour expiry."
    Chunk 2: "Failed logins are rate-limited to 5 attempts per minute."
    LLM Output:
      POSITIVE  → "Verify JWT token is returned on valid login"
      NEGATIVE  → "Verify 401 is returned with wrong password"
      BOUNDARY  → "Verify 5th failed login succeeds, 6th returns 429 Too Many Requests"
  The RAG chunks tell the LLM the specific domain rules → grounded test cases.
"""

import os
import json
import uuid
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.orm import Session

from app import models
from app.analyzers.llm_client import LLMClient
from app.generators.prompt import TEST_CASE_GENERATOR_SYSTEM_PROMPT, build_test_case_prompt
from schemas import TestCase as PydanticTestCase, TestCasePriority, TestCaseStatus

TEST_CASES_DIR = os.path.join("storage", "test_cases")
os.makedirs(TEST_CASES_DIR, exist_ok=True)

# Valid test types — used for Pydantic-like validation
VALID_TEST_TYPES = {"POSITIVE", "NEGATIVE", "BOUNDARY", "SECURITY", "PERFORMANCE"}

# How many RAG chunks to retrieve per requirement.
# More chunks = richer context but bigger prompts.
RAG_TOP_K_PER_REQUIREMENT = 3


class TestCaseGeneratorService:

    @classmethod
    def generate_test_cases_for_project(
        cls,
        project_id: str,
        db: Session,
        include_proposed: bool = True,
        use_rag: bool = True
    ) -> Dict[str, Any]:
        """
        Main entry point — generates test cases for all requirements in a project.

        Day 10 RAG Workflow:
          1. Fetch requirements from SQLite.
          2. For each requirement, retrieve top-K semantically relevant chunks
             from Qdrant (or fall back to SQLite chunk IDs if Qdrant is down).
          3. Build a rich prompt with requirement text + RAG context.
          4. Call LLM (or heuristic fallback) to generate test cases.
          5. Validate with Pydantic and persist to SQLite.
          6. Save audit JSON to storage/test_cases/{project_id}.json.

        Args:
            project_id       : project to generate test cases for
            db               : SQLAlchemy session
            include_proposed : also include proposed (not yet approved) requirements
            use_rag          : if True (default), use Qdrant semantic retrieval;
                               if False, use only SQLite chunk_ids (Day 7 behavior)

        Returns:
            Summary dict with total count and all test case dicts.
        """
        # 1. Fetch requirements
        query = db.query(models.Requirement).filter(models.Requirement.project_id == project_id)
        if not include_proposed:
            query = query.filter(models.Requirement.status == "approved")
        else:
            query = query.filter(models.Requirement.status.in_(["approved", "proposed"]))
        requirements = query.all()

        if not requirements:
            raise ValueError(
                f"No requirements found for project {project_id}. "
                "Upload and analyze a document first."
            )

        # 2. Build RAG context for each requirement
        req_contexts = cls._build_rag_contexts(requirements, project_id, db, use_rag)

        # 3. Generate test cases via LLM or heuristic
        raw_test_cases = cls._call_generation_engine(req_contexts)

        # 4. Clear old test cases for this project (clean regeneration)
        db.query(models.TestCase).filter(models.TestCase.project_id == project_id).delete()

        # 5. Validate with Pydantic and persist
        persisted = cls._validate_and_persist(raw_test_cases, project_id, db)

        db.commit()

        # 6. Save audit JSON
        audit_data = cls._build_audit_record(project_id, persisted)
        audit_file = os.path.join(TEST_CASES_DIR, f"{project_id}.json")
        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump(audit_data, f, indent=2, ensure_ascii=False)

        return {
            "project_id": project_id,
            "total_requirements": len(requirements),
            "total_test_cases": len(persisted),
            "rag_used": use_rag,
            "breakdown": audit_data["breakdown"],
            "audit_file": audit_file,
            "test_cases": audit_data["test_cases"]
        }

    # ------------------------------------------------------------------
    # Step 2 — RAG Context Builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_rag_contexts(
        cls,
        requirements: list,
        project_id: str,
        db: Session,
        use_rag: bool
    ) -> List[Dict[str, Any]]:
        """
        For each requirement, fetch the most relevant chunks using one of:
          A) Qdrant semantic retrieval (use_rag=True, Qdrant running)  ← preferred
          B) SQLite chunk_id lookup (fallback when Qdrant is offline)

        LEARN — why A is better than B:
          B fetches only the chunks the LLM originally linked to the requirement.
          A searches the entire project's chunk index for semantically related
          sentences — it finds relevant context the LLM may have missed in step B.
        """
        req_contexts = []

        for r in requirements:
            context_chunks = []

            if use_rag:
                # Try Qdrant semantic retrieval first
                try:
                    from app.rag.retriever import RAGRetriever
                    rag_chunks = RAGRetriever.retrieve_for_requirement(
                        requirement_text=r.text,
                        project_id=project_id,
                        top_k=RAG_TOP_K_PER_REQUIREMENT
                    )
                    if rag_chunks:
                        context_chunks = rag_chunks
                        print(f"[Day10] RAG: retrieved {len(rag_chunks)} chunks for req {r.id[:8]}...")
                    else:
                        # Qdrant returned nothing — fall back to SQLite
                        context_chunks = cls._sqlite_chunk_lookup(r, db)
                except ConnectionError:
                    print(f"[Day10] Qdrant offline — falling back to SQLite for req {r.id[:8]}...")
                    context_chunks = cls._sqlite_chunk_lookup(r, db)
                except Exception as e:
                    print(f"[Day10] RAG retrieval failed ({e}) — falling back to SQLite.")
                    context_chunks = cls._sqlite_chunk_lookup(r, db)
            else:
                # use_rag=False: use original SQLite chunk_id lookup
                context_chunks = cls._sqlite_chunk_lookup(r, db)

            req_contexts.append({
                "id": r.id,
                "text": r.text,
                "confidence": r.confidence,
                "status": r.status,
                "context_chunks": context_chunks
            })

        return req_contexts

    @classmethod
    def _sqlite_chunk_lookup(cls, requirement: models.Requirement, db: Session) -> List[Dict[str, Any]]:
        """
        Fallback: fetch only the chunks already linked to this requirement in SQLite.
        Used when Qdrant is offline or use_rag=False.
        """
        chunk_ids = requirement.linked_chunk_ids or []
        if not chunk_ids:
            return []
        chunks = db.query(models.Chunk).filter(models.Chunk.chunk_id.in_(chunk_ids)).all()
        return [
            {
                "chunk_id": c.chunk_id,
                "id": c.chunk_id,
                "text": c.text,
                "section": c.source_section,
                "score": None  # no similarity score in SQLite fallback
            }
            for c in chunks
        ]

    # ------------------------------------------------------------------
    # Step 3 — LLM / Heuristic Generation Engine
    # ------------------------------------------------------------------

    @classmethod
    def _call_generation_engine(cls, req_contexts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Tries Gemini LLM first; falls back to comprehensive heuristic generator.

        LEARN — why we keep a heuristic fallback:
          LLM APIs can be slow, rate-limited, or unavailable. The heuristic
          ensures the pipeline always produces useful test cases, even offline.
          In production, you'd remove the fallback and enforce the LLM.
        """
        api_key = LLMClient.get_api_key()
        if api_key and not api_key.startswith("mock_"):
            try:
                user_prompt = build_test_case_prompt(req_contexts)
                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": f"{TEST_CASE_GENERATOR_SYSTEM_PROMPT}\n\n{user_prompt}"}]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.15,   # lower = more deterministic output
                        "responseMimeType": "application/json"
                    }
                }
                for model in LLMClient.GEMINI_MODELS:
                    url = LLMClient.DEFAULT_API_URL.format(model=model, api_key=api_key)
                    try:
                        resp = httpx.post(url, json=payload, timeout=45.0)
                        if resp.status_code == 200:
                            data = resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                text_resp = candidates[0]["content"]["parts"][0]["text"].strip()
                                clean_json = re.sub(r"^```json\s*", "", text_resp)
                                clean_json = re.sub(r"\s*```$", "", clean_json)
                                parsed = json.loads(clean_json)
                                tcs = parsed.get("test_cases", [])
                                if tcs:
                                    print(f"[Day10] LLM generated {len(tcs)} test cases via {model}.")
                                    return tcs
                    except Exception as err:
                        print(f"[Day10] LLM {model} error: {err}")
            except Exception as e:
                print(f"[Day10] LLM call failed: {e}. Using heuristic generator.")

        return cls._heuristic_generator(req_contexts)

    @classmethod
    def _heuristic_generator(cls, req_contexts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deterministic test case generator — produces Positive, Negative, Boundary,
        and Security test cases from requirement text patterns.

        Day 10 upgrades over Day 7:
          - Adds test_type field on every test case
          - Adds acceptance_criteria field
          - Adds rag_chunk_ids field listing which chunks informed the test
          - Detects auth/security patterns for SECURITY test cases
          - Detects performance keywords for PERFORMANCE test cases

        LEARN — this heuristic is a good example of deterministic engineering:
          It doesn't rely on an LLM to be smart. Instead it applies pattern
          matching rules that always produce the same output for the same input.
          This is predictable, testable, and never hallucinates.
        """
        test_cases = []
        for r in req_contexts:
            req_id = r["id"]
            text = r["text"]
            text_lower = text.lower()
            chunk_ids = [c.get("chunk_id") or c.get("id", "") for c in r.get("context_chunks", [])]
            has_numbers = bool(re.search(r"\d+", text))

            # --- 1. POSITIVE test case ---
            test_cases.append({
                "title": f"[POSITIVE] Verify: {text[:80]}",
                "test_type": "POSITIVE",
                "preconditions": "System is initialized with valid configuration and test data.",
                "steps": [
                    f"1. Set up prerequisite conditions for: {text[:60]}.",
                    "2. Submit valid inputs matching the specification.",
                    "3. Execute the operation and observe system response."
                ],
                "expected_result": f"System processes the request successfully as per: '{text[:120]}'.",
                "acceptance_criteria": "Operation completes without errors within expected response time.",
                "priority": "P0" if any(k in text_lower for k in ["must", "shall", "critical", "security"]) else "P1",
                "linked_requirement_ids": [req_id],
                "rag_chunk_ids": chunk_ids
            })

            # --- 2. NEGATIVE test case ---
            test_cases.append({
                "title": f"[NEGATIVE] Verify error handling: {text[:80]}",
                "test_type": "NEGATIVE",
                "preconditions": "Application server and error monitoring are active.",
                "steps": [
                    "1. Provide malformed, empty, or out-of-range input parameters.",
                    "2. Omit one or more required fields.",
                    "3. Submit the request and check system response and logs."
                ],
                "expected_result": "System rejects invalid inputs with a clear error message and does not crash or leak sensitive data.",
                "acceptance_criteria": "Error response returned within 200ms with correct HTTP status code.",
                "priority": "P1",
                "linked_requirement_ids": [req_id],
                "rag_chunk_ids": chunk_ids
            })

            # --- 3. BOUNDARY test case (only if requirement mentions numbers/limits) ---
            if has_numbers:
                test_cases.append({
                    "title": f"[BOUNDARY] Verify threshold limits: {text[:80]}",
                    "test_type": "BOUNDARY",
                    "preconditions": "Test harness prepared with boundary edge-case datasets.",
                    "steps": [
                        "1. Submit input at the exact minimum valid threshold value.",
                        "2. Submit input at the exact maximum valid threshold value.",
                        "3. Submit input immediately below the minimum (min - 1).",
                        "4. Submit input immediately above the maximum (max + 1)."
                    ],
                    "expected_result": "Values at exact boundaries are accepted. Values outside the boundary are rejected with a precise validation error.",
                    "acceptance_criteria": "All boundary values handled correctly without system error or data corruption.",
                    "priority": "P1",
                    "linked_requirement_ids": [req_id],
                    "rag_chunk_ids": chunk_ids
                })

            # --- 4. SECURITY test case (if auth/security keywords detected) ---
            security_keywords = ["auth", "login", "password", "token", "role", "permission", "access", "jwt", "admin", "secure"]
            if any(kw in text_lower for kw in security_keywords):
                test_cases.append({
                    "title": f"[SECURITY] Verify access control: {text[:80]}",
                    "test_type": "SECURITY",
                    "preconditions": "Security testing tools configured. Unauthorized user account available.",
                    "steps": [
                        "1. Attempt the operation without any authentication credentials.",
                        "2. Attempt the operation with an expired or tampered token.",
                        "3. Attempt privilege escalation with a lower-privileged user account.",
                        "4. Try SQL injection / XSS payloads in input fields if applicable."
                    ],
                    "expected_result": "All unauthorized access attempts are rejected with 401/403. No sensitive data is leaked. Injection payloads are sanitized.",
                    "acceptance_criteria": "Zero unauthorized access granted. Security headers (Content-Security-Policy, X-Frame-Options) present in responses.",
                    "priority": "P0",
                    "linked_requirement_ids": [req_id],
                    "rag_chunk_ids": chunk_ids
                })

            # --- 5. PERFORMANCE test case (if performance keywords detected) ---
            perf_keywords = ["response time", "latency", "throughput", "concurrent", "load", "timeout", "retry", "millisecond", "second", "ms", "tps", "rps"]
            if any(kw in text_lower for kw in perf_keywords):
                test_cases.append({
                    "title": f"[PERFORMANCE] Verify response time/throughput: {text[:80]}",
                    "test_type": "PERFORMANCE",
                    "preconditions": "Load testing environment configured. Monitoring and metrics collection active.",
                    "steps": [
                        "1. Configure load testing tool (e.g. k6, JMeter) for the target endpoint.",
                        "2. Execute requests at specified load (concurrent users / requests per second).",
                        "3. Record P50, P95, P99 response times and error rate.",
                        "4. Compare against the performance requirement thresholds."
                    ],
                    "expected_result": "All performance metrics meet or exceed the stated requirement thresholds under specified load conditions.",
                    "acceptance_criteria": "P95 response time within stated SLA. Error rate < 0.1% under normal load.",
                    "priority": "P1",
                    "linked_requirement_ids": [req_id],
                    "rag_chunk_ids": chunk_ids
                })

        return test_cases

    # ------------------------------------------------------------------
    # Step 5 — Pydantic Validation & SQLite Persistence
    # ------------------------------------------------------------------

    @classmethod
    def _validate_and_persist(
        cls,
        raw_test_cases: List[Dict[str, Any]],
        project_id: str,
        db: Session
    ) -> List[models.TestCase]:
        """
        Validates each raw test case dict against Pydantic schemas and
        saves a SQLAlchemy ORM row to the test_cases SQLite table.

        LEARN — why we validate before persisting:
          The LLM can return slightly malformed JSON or wrong field types.
          Pydantic catches these errors BEFORE they hit the database.
          This is called "schema-first design" — define the shape, enforce it.
        """
        persisted = []
        for tc_dict in raw_test_cases:
            tc_id = str(uuid.uuid4())

            # Normalize priority to enum value
            prio_raw = str(tc_dict.get("priority", "P2")).upper()
            priority_enum = TestCasePriority.P2
            if prio_raw in ("P0", "P1", "P2", "P3"):
                priority_enum = TestCasePriority(prio_raw)

            # Normalize steps: accept list or newline-separated string
            steps = tc_dict.get("steps", [])
            if isinstance(steps, str):
                steps = [s.strip() for s in steps.split("\n") if s.strip()]

            # Validate with Pydantic
            pydantic_tc = PydanticTestCase(
                id=tc_id,
                project_id=project_id,
                title=tc_dict.get("title", "Untitled Test Case").strip()[:500],
                preconditions=tc_dict.get("preconditions", "Standard environment ready."),
                steps=steps if steps else ["1. Execute action per requirement."],
                expected_result=tc_dict.get("expected_result", "System functions correctly.").strip(),
                priority=priority_enum,
                linked_requirement_ids=tc_dict.get("linked_requirement_ids", []),
                status=TestCaseStatus.DRAFT,
                created_at=datetime.utcnow(),
                last_generated_at=datetime.utcnow()
            )

            # Build the DB row — includes extra Day 10 fields stored as JSON
            # (test_type and acceptance_criteria go into the steps JSON as structured notes
            #  since the models.py TestCase table doesn't have those columns yet —
            #  Day 11 migration will add them. For now we prefix the title.)
            test_type = str(tc_dict.get("test_type", "POSITIVE")).upper()
            if test_type not in VALID_TEST_TYPES:
                test_type = "POSITIVE"

            acceptance_criteria = tc_dict.get("acceptance_criteria", "")
            rag_chunk_ids = tc_dict.get("rag_chunk_ids", [])

            # Encode test_type and acceptance_criteria into steps list as metadata lines
            # (This is a temporary approach until the DB migration in Day 11 adds the columns)
            augmented_steps = list(pydantic_tc.steps)
            if acceptance_criteria:
                augmented_steps.append(f"[ACCEPTANCE CRITERIA] {acceptance_criteria}")
            if rag_chunk_ids:
                augmented_steps.append(f"[RAG SOURCES] {', '.join(rag_chunk_ids[:5])}")

            db_tc = models.TestCase(
                id=pydantic_tc.id,
                project_id=pydantic_tc.project_id,
                title=f"[{test_type}] {pydantic_tc.title}" if not pydantic_tc.title.startswith("[") else pydantic_tc.title,
                preconditions=pydantic_tc.preconditions,
                steps=augmented_steps,
                expected_result=pydantic_tc.expected_result,
                priority=pydantic_tc.priority.value,
                linked_requirement_ids=pydantic_tc.linked_requirement_ids,
                status=pydantic_tc.status.value,
                created_at=pydantic_tc.created_at,
                last_generated_at=pydantic_tc.last_generated_at
            )
            db.add(db_tc)
            persisted.append((db_tc, test_type, acceptance_criteria, rag_chunk_ids))

        return persisted

    # ------------------------------------------------------------------
    # Step 6 — Audit Record Builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_audit_record(cls, project_id: str, persisted: list) -> Dict[str, Any]:
        """
        Builds the audit JSON that's saved to storage/test_cases/{project_id}.json.

        LEARN — audit files are important in AI pipelines:
          They let you trace exactly what was generated, when, with what context.
          If a test case turns out to be wrong, you can open the audit file and
          see exactly which RAG chunks and requirement drove the generation.
        """
        test_case_records = []
        for item in persisted:
            db_tc, test_type, acceptance_criteria, rag_chunk_ids = item
            test_case_records.append({
                "id": db_tc.id,
                "title": db_tc.title,
                "test_type": test_type,
                "priority": db_tc.priority,
                "preconditions": db_tc.preconditions,
                "steps": db_tc.steps,
                "expected_result": db_tc.expected_result,
                "acceptance_criteria": acceptance_criteria,
                "linked_requirement_ids": db_tc.linked_requirement_ids,
                "rag_chunk_ids": rag_chunk_ids,
                "status": db_tc.status
            })

        return {
            "project_id": project_id,
            "generated_at": datetime.utcnow().isoformat(),
            "total_test_cases": len(test_case_records),
            "breakdown": {
                t: sum(1 for r in test_case_records if r["test_type"] == t)
                for t in VALID_TEST_TYPES
            },
            "test_cases": test_case_records
        }
