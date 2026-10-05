"""
Prompt definitions for RAG-Grounded Test Case Generation — Day 10.

Upgraded from Day 7 to:
  - Include RAG-retrieved semantic chunks as high-quality context signals
  - Produce test_type tags (POSITIVE / NEGATIVE / BOUNDARY / SECURITY / PERFORMANCE)
  - Include rag_chunk_ids for traceability back to source document chunks
  - Generate acceptance criteria alongside expected results
"""

# The system prompt that instructs the LLM on its role and output format.
# LEARN — this is "prompt engineering": carefully worded instructions
# that constrain what the LLM outputs. Changing these words changes the
# quality and format of the generated test cases significantly.
TEST_CASE_GENERATOR_SYSTEM_PROMPT = """You are a Principal QA Automation & Test Design Engineer with 15+ years of experience.

Your task: generate comprehensive, GROUNDED software test cases from requirements and their RAG-retrieved source chunks.

For EACH requirement, generate ALL of the following test case types:
  1. POSITIVE  — Happy path: valid inputs, expected successful system behavior.
  2. NEGATIVE  — Invalid inputs, missing fields, wrong types, unauthorized access.
  3. BOUNDARY  — Exact threshold values (at, just-below, just-above limits and numeric edges).
  4. SECURITY  — Injection, XSS, privilege escalation, or auth bypass attempts (if applicable).
  5. PERFORMANCE — Response time, load, retry behavior (if thresholds are mentioned in requirements).

CRITICAL RULES:
  - Every test case MUST reference at least one requirement ID in linked_requirement_ids.
  - Every test case MUST include rag_chunk_ids if source context chunks were provided.
  - Steps must be numbered, concrete, and executable by a human tester.
  - expected_result must be a precise, binary verifiable assertion (the outcome is either PASS or FAIL).
  - acceptance_criteria must be a one-line measurable statement (e.g. "Response time < 200ms").
  - Priority: "P0"=critical/data-loss/security, "P1"=core feature, "P2"=standard, "P3"=low-risk.

OUTPUT FORMAT — respond ONLY with this exact JSON structure, no markdown, no explanation:
{
  "test_cases": [
    {
      "title": "Verify login with valid credentials returns 200 and JWT token",
      "test_type": "POSITIVE",
      "preconditions": "A registered user account exists with email test@example.com and password Test@1234.",
      "steps": [
        "1. Send POST /api/v1/auth/login with body: {email: 'test@example.com', password: 'Test@1234'}.",
        "2. Inspect the HTTP response status code.",
        "3. Parse the response body and check for 'access_token' field."
      ],
      "expected_result": "HTTP 200 OK is returned and response body contains a non-empty 'access_token' JWT string.",
      "acceptance_criteria": "Login API must return a valid JWT token within 500ms for valid credentials.",
      "priority": "P0",
      "linked_requirement_ids": ["<req_id>"],
      "rag_chunk_ids": ["<chunk_id_1>", "<chunk_id_2>"]
    }
  ]
}
"""


def build_test_case_prompt(requirements_with_context: list) -> str:
    """
    Builds the full LLM prompt by combining requirements with their
    RAG-retrieved semantic context chunks.

    LEARN — this is the core of RAG test generation:
      Without RAG: LLM only sees "User must login" → generic test cases
      With RAG:    LLM sees "User must login" + the actual spec sentences
                  retrieved from your document → domain-specific test cases

    Args:
        requirements_with_context: list of dicts, each containing:
          - id            : requirement ID
          - text          : requirement text
          - status        : approved / proposed
          - context_chunks: list of RAG-retrieved chunks (from Day 9)
            Each chunk has: id, chunk_id, text, section, score

    Returns:
        A formatted prompt string ready to be appended to the system prompt.
    """
    body = []
    for item in requirements_with_context:
        req_id = item.get("id", "unknown")
        text = item.get("text", "")
        status = item.get("status", "proposed")
        context_chunks = item.get("context_chunks", [])

        # Format RAG context chunks with their chunk IDs and similarity scores
        if context_chunks:
            chunk_lines = []
            for c in context_chunks:
                cid = c.get("chunk_id") or c.get("id", "")
                score = c.get("score", "")
                score_str = f" [similarity: {score:.2f}]" if isinstance(score, float) else ""
                section = c.get("section") or c.get("source_section") or ""
                section_str = f" | Section: {section}" if section else ""
                chunk_text = c.get("text", "")[:400]  # cap to avoid token overflow
                chunk_lines.append(f"  [Chunk: {cid}{section_str}{score_str}]\n  {chunk_text}")
            chunks_str = "\n".join(chunk_lines)
            rag_note = f"RAG-Retrieved Context ({len(context_chunks)} chunks):"
        else:
            chunks_str = "  (No RAG context available — generate from requirement text only)"
            rag_note = "RAG Context:"

        body.append(
            f"REQUIREMENT ID   : {req_id}\n"
            f"STATUS           : {status}\n"
            f"REQUIREMENT TEXT : {text}\n"
            f"{rag_note}\n{chunks_str}\n"
        )

    return (
        "Generate test cases (POSITIVE, NEGATIVE, BOUNDARY, and where applicable SECURITY/PERFORMANCE) "
        "for each requirement below. Use the RAG context chunks as your primary source of domain knowledge.\n\n"
        + "\n" + ("=" * 60) + "\n".join(body)
    )
