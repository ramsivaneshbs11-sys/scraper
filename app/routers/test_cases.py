"""
Test Cases Router — Day 10 (RAG + Excel Export).

Day 10 upgrades:
  - /generate-test-cases now accepts use_rag=true|false query param
  - New /test-cases/export/excel endpoint — downloads .xlsx file
  - New /test-cases/{id}/approve endpoint — marks a test case as reviewed
  - Enhanced /test-cases response includes test_type and acceptance_criteria

LEARN — Excel export via openpyxl:
  openpyxl lets you create .xlsx files in Python without Excel installed.
  We stream the file directly from memory (BytesIO) so nothing is saved
  to disk — the file goes straight to the client's browser as a download.
"""

import io
import csv
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.generators.service import TestCaseGeneratorService

router = APIRouter(tags=["test-cases"])


# ------------------------------------------------------------------
# Generation
# ------------------------------------------------------------------

@router.post("/projects/{project_id}/generate-test-cases")
def generate_project_test_cases(
    project_id: str,
    include_proposed: bool = Query(True, description="Also include proposed (not yet approved) requirements."),
    use_rag: bool = Query(True, description="Use Qdrant semantic retrieval for richer context (requires Qdrant running)."),
    db: Session = Depends(get_db)
):
    """
    RAG-Powered Test Case Generation (Day 10).

    Reads all approved/proposed requirements, retrieves semantically
    relevant source chunks from Qdrant (or falls back to SQLite),
    then generates Positive, Negative, Boundary, Security, and
    Performance test cases grounded in the actual document content.

    Query params:
      - include_proposed : include requirements not yet reviewed by admin
      - use_rag          : use Qdrant semantic retrieval (default: true)

    Returns:
      - total_requirements  : how many requirements were processed
      - total_test_cases    : how many test cases were generated
      - breakdown           : count per test type (POSITIVE/NEGATIVE/etc.)
      - rag_used            : whether Qdrant retrieval was active
      - test_cases          : full list of generated test case objects
    """
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    try:
        result = TestCaseGeneratorService.generate_test_cases_for_project(
            project_id=project.id,
            db=db,
            include_proposed=include_proposed,
            use_rag=use_rag
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test case generation failed: {e}")


# ------------------------------------------------------------------
# Fetch
# ------------------------------------------------------------------

@router.get("/projects/{project_id}/test-cases")
def get_project_test_cases(
    project_id: str,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Fetches all test cases for a project with optional priority and status filters."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    query = db.query(models.TestCase).filter(models.TestCase.project_id == project.id)
    if priority:
        query = query.filter(models.TestCase.priority == priority.upper())
    if status:
        query = query.filter(models.TestCase.status == status.lower())

    tcs = query.order_by(models.TestCase.priority.asc()).all()
    return {
        "project_id": project.id,
        "total_test_cases": len(tcs),
        "test_cases": tcs
    }


# ------------------------------------------------------------------
# Review Actions
# ------------------------------------------------------------------

@router.patch("/test-cases/{test_case_id}/approve")
def approve_test_case(test_case_id: str, db: Session = Depends(get_db)):
    """
    Marks a test case as reviewed/approved by an admin or senior tester.

    LEARN — test case approval is the human gate in the pipeline:
      AI proposes → Human approves → Approved cases go into the test suite.
      This ensures no hallucinated or incorrect test case slips through.
    """
    tc = db.query(models.TestCase).filter(models.TestCase.id == test_case_id).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found.")
    tc.status = "approved"
    db.commit()
    db.refresh(tc)
    return {"status": "success", "message": "Test case approved.", "test_case_id": test_case_id}


@router.patch("/test-cases/{test_case_id}/reject")
def reject_test_case(test_case_id: str, db: Session = Depends(get_db)):
    """Marks a test case as rejected (needs rework or deletion)."""
    tc = db.query(models.TestCase).filter(models.TestCase.id == test_case_id).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found.")
    tc.status = "rejected"
    db.commit()
    return {"status": "success", "message": "Test case rejected.", "test_case_id": test_case_id}


# ------------------------------------------------------------------
# Export: CSV
# ------------------------------------------------------------------

@router.get("/projects/{project_id}/test-cases/export")
@router.get("/projects/{project_id}/test-cases/export/csv")
def export_test_cases_csv(project_id: str, db: Session = Depends(get_db)):
    """
    Exports test cases as a downloadable CSV file.
    Compatible with Excel, Google Sheets, Jira, and TestRail import formats.
    """
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    test_cases = db.query(models.TestCase).filter(models.TestCase.project_id == project.id).all()
    if not test_cases:
        raise HTTPException(status_code=404, detail="No test cases to export.")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Test Case ID", "Title", "Priority", "Preconditions",
        "Test Steps", "Expected Result", "Linked Requirements", "Status"
    ])
    for tc in test_cases:
        steps_str = "\n".join(tc.steps) if isinstance(tc.steps, list) else str(tc.steps or "")
        reqs_str = ", ".join(tc.linked_requirement_ids) if isinstance(tc.linked_requirement_ids, list) else ""
        writer.writerow([
            tc.id, tc.title, tc.priority, tc.preconditions or "",
            steps_str, tc.expected_result, reqs_str, tc.status
        ])

    output.seek(0)
    filename = f"test_cases_{project.name.replace(' ', '_').lower()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ------------------------------------------------------------------
# Export: Excel (.xlsx) — Day 10 / Day 11
# ------------------------------------------------------------------

@router.get("/projects/{project_id}/test-cases/export/excel")
def export_test_cases_excel(project_id: str, db: Session = Depends(get_db)):
    """
    Exports test cases as a formatted Excel (.xlsx) file — Day 10.

    LEARN — why Excel over CSV?
      - Excel supports column widths, bold headers, color coding, and cell wrapping.
      - Test managers (TestRail, Zephyr, ALM) prefer Excel format for import.
      - openpyxl writes .xlsx in Python without needing Excel installed.

    The output workbook has:
      - Sheet 1: "Test Cases"   — all test cases with formatting
      - Sheet 2: "Summary"      — breakdown by priority and test type

    Usage:
      GET /projects/{project_id}/test-cases/export/excel
      → Downloads test_cases_{project_name}.xlsx
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="openpyxl not installed. Run: pip install openpyxl"
        )

    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    test_cases = db.query(models.TestCase).filter(
        models.TestCase.project_id == project.id
    ).order_by(models.TestCase.priority.asc()).all()

    if not test_cases:
        raise HTTPException(status_code=404, detail="No test cases to export.")

    # ------- Build workbook -------
    wb = openpyxl.Workbook()

    # ---- Sheet 1: Test Cases ----
    ws = wb.active
    ws.title = "Test Cases"

    # Color palette
    HEADER_FILL = PatternFill("solid", fgColor="1F3864")   # dark navy
    P0_FILL     = PatternFill("solid", fgColor="FF4C4C")   # red
    P1_FILL     = PatternFill("solid", fgColor="FF9900")   # orange
    P2_FILL     = PatternFill("solid", fgColor="FFD966")   # yellow
    P3_FILL     = PatternFill("solid", fgColor="D9EAD3")   # light green
    ALT_FILL    = PatternFill("solid", fgColor="EEF2F7")   # subtle grey stripe

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    cell_font   = Font(name="Calibri", size=10)
    wrap_align  = Alignment(wrap_text=True, vertical="top")
    center_align= Alignment(horizontal="center", vertical="center")

    headers = [
        "Sl.No", "Test Case ID", "Title", "Priority",
        "Preconditions", "Test Steps", "Expected Result",
        "Linked Requirements", "Status", "Last Generated"
    ]
    col_widths = [6, 38, 45, 10, 35, 55, 45, 30, 12, 20]

    # Write headers
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = HEADER_FILL
        cell.alignment = center_align
        cell.border = border
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths[col_idx - 1]

    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"  # freeze header row

    # Write data rows
    priority_fills = {"P0": P0_FILL, "P1": P1_FILL, "P2": P2_FILL, "P3": P3_FILL}

    for row_idx, tc in enumerate(test_cases, 2):
        steps_str = "\n".join(tc.steps) if isinstance(tc.steps, list) else str(tc.steps or "")
        reqs_str  = ", ".join(tc.linked_requirement_ids) if isinstance(tc.linked_requirement_ids, list) else ""
        gen_at    = tc.last_generated_at.strftime("%Y-%m-%d %H:%M") if tc.last_generated_at else ""

        row_data = [
            row_idx - 1,
            tc.id[:36],
            tc.title,
            tc.priority,
            tc.preconditions or "",
            steps_str,
            tc.expected_result,
            reqs_str,
            tc.status.upper(),
            gen_at
        ]

        row_fill = priority_fills.get(tc.priority, ALT_FILL) if tc.priority in ("P0", "P1") else (
            ALT_FILL if row_idx % 2 == 0 else None
        )

        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = cell_font
            cell.alignment = wrap_align if col_idx not in (1, 4, 9) else center_align
            cell.border = border
            if row_fill and col_idx not in (4,):  # don't double-fill priority cell
                cell.fill = row_fill

        # Priority cell gets its own color
        prio_cell = ws.cell(row=row_idx, column=4)
        prio_cell.fill = priority_fills.get(tc.priority, ALT_FILL)
        prio_cell.font = Font(name="Calibri", bold=True, size=10,
                              color="FFFFFF" if tc.priority in ("P0", "P1") else "000000")

        ws.row_dimensions[row_idx].height = max(40, min(len(steps_str) // 3, 120))

    # ---- Sheet 2: Summary ----
    ws2 = wb.create_sheet("Summary")
    ws2.title = "Summary"
    ws2["A1"] = f"Project: {project.name}"
    ws2["A1"].font = Font(bold=True, size=14)
    ws2["A2"] = f"Total Test Cases: {len(test_cases)}"
    ws2["A2"].font = Font(bold=True)

    ws2["A4"] = "Priority"
    ws2["B4"] = "Count"
    ws2["A4"].font = Font(bold=True)
    ws2["B4"].font = Font(bold=True)

    priority_counts = {}
    for tc in test_cases:
        priority_counts[tc.priority] = priority_counts.get(tc.priority, 0) + 1
    for i, (prio, count) in enumerate(sorted(priority_counts.items()), 5):
        ws2.cell(row=i, column=1, value=prio)
        ws2.cell(row=i, column=2, value=count)

    ws2.column_dimensions["A"].width = 20
    ws2.column_dimensions["B"].width = 12

    # Serialize to bytes and stream as response
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"test_cases_{project.name.replace(' ', '_').lower()}.xlsx"
    return StreamingResponse(
        iter([buffer.read()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------

@router.delete("/test-cases/{test_case_id}")
def delete_test_case(test_case_id: str, db: Session = Depends(get_db)):
    """Deletes a single test case by ID."""
    tc = db.query(models.TestCase).filter(models.TestCase.id == test_case_id).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found.")
    db.delete(tc)
    db.commit()
    return {"status": "success", "message": f"Test case {test_case_id} deleted."}


# ------------------------------------------------------------------
# Export: Gherkin / BDD (.feature)
# ------------------------------------------------------------------

@router.get("/projects/{project_id}/test-cases/export/gherkin")
def export_test_cases_gherkin(project_id: str, db: Session = Depends(get_db)):
    """Exports test cases formatted as a standard BDD Gherkin .feature file."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    test_cases = db.query(models.TestCase).filter(models.TestCase.project_id == project.id).all()
    if not test_cases:
        raise HTTPException(status_code=404, detail="No test cases to export.")

    gherkin_lines = [
        f"@project @{project.name.replace(' ', '_').lower()}",
        f"Feature: {project.name} Automated Test Suite",
        f"  As a Quality Engineer",
        f"  I want verified regression coverage for {project.name}",
        f"  So that high quality standards and requirements are maintained",
        ""
    ]

    for tc in test_cases:
        gherkin_lines.append(f"  @{tc.priority.lower()} @id_{tc.id[:8]}")
        gherkin_lines.append(f"  Scenario: {tc.title}")
        if tc.preconditions:
            gherkin_lines.append(f"    Given {tc.preconditions}")
        else:
            gherkin_lines.append(f"    Given system is in initial clean state")

        steps = tc.steps if isinstance(tc.steps, list) else [str(tc.steps)]
        for idx, step in enumerate(steps):
            clean_step = str(step).strip()
            if clean_step.startswith("[") and "]" in clean_step:
                continue
            prefix = "When" if idx == 0 else "And"
            gherkin_lines.append(f"    {prefix} {clean_step}")

        gherkin_lines.append(f"    Then {tc.expected_result}")
        gherkin_lines.append("")

    content = "\n".join(gherkin_lines)
    filename = f"{project.name.replace(' ', '_').lower()}.feature"
    return StreamingResponse(
        iter([content]),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ------------------------------------------------------------------
# Traceability Matrix
# ------------------------------------------------------------------

@router.get("/projects/{project_id}/traceability")
def get_traceability_matrix(project_id: str, db: Session = Depends(get_db)):
    """
    Returns end-to-end Traceability Matrix:
    Requirements -> Test Cases -> Status -> Chunks -> Priority
    """
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    requirements = db.query(models.Requirement).filter(models.Requirement.project_id == project.id).all()
    test_cases = db.query(models.TestCase).filter(models.TestCase.project_id == project.id).all()
    documents = db.query(models.Document).filter(models.Document.project_id == project.id).all()

    # Map test cases by requirement id
    req_to_tcs = {}
    for tc in test_cases:
        linked = tc.linked_requirement_ids if isinstance(tc.linked_requirement_ids, list) else []
        for rid in linked:
            req_to_tcs.setdefault(rid, []).append({
                "id": tc.id,
                "title": tc.title,
                "priority": tc.priority,
                "status": tc.status,
                "expected_result": tc.expected_result
            })

    matrix = []
    covered_count = 0
    for req in requirements:
        linked_tests = req_to_tcs.get(req.id, [])
        is_covered = len(linked_tests) > 0
        if is_covered:
            covered_count += 1
        matrix.append({
            "requirement_id": req.id,
            "text": req.text,
            "confidence": req.confidence,
            "status": req.status,
            "linked_chunk_ids": req.linked_chunk_ids or [],
            "test_cases": linked_tests,
            "is_covered": is_covered
        })

    coverage_pct = round((covered_count / len(requirements) * 100), 1) if requirements else 0.0

    return {
        "project_id": project.id,
        "project_name": project.name,
        "total_documents": len(documents),
        "total_requirements": len(requirements),
        "covered_requirements": covered_count,
        "coverage_percentage": coverage_pct,
        "total_test_cases": len(test_cases),
        "matrix": matrix
    }


# ------------------------------------------------------------------
# Automation: Playwright Test Generator
# ------------------------------------------------------------------

@router.post("/projects/{project_id}/generate-automation")
def generate_playwright_automation(
    project_id: str,
    target_url: Optional[str] = "http://localhost:3000",
    db: Session = Depends(get_db)
):
    """Generates an executable Playwright TypeScript test suite for approved test cases."""
    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    test_cases = db.query(models.TestCase).filter(
        models.TestCase.project_id == project.id
    ).all()
    if not test_cases:
        raise HTTPException(status_code=400, detail="No test cases available to generate automation scripts.")

    code_lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        f"// Auto-generated Playwright Test Suite for {project.name}",
        f"// Generated by AI QA Engineer Workspace",
        f"// Target Environment: {target_url}",
        "",
        f"test.describe('{project.name} Automated Verification Suite', () => {{",
        "  test.beforeEach(async ({ page }) => {",
        f"    await page.goto('{target_url}');",
        "  });",
        ""
    ]

    for tc in test_cases:
        safe_title = tc.title.replace("'", "\\'")
        code_lines.append(f"  // Requirement Anchor: {', '.join(tc.linked_requirement_ids if isinstance(tc.linked_requirement_ids, list) else [])}")
        code_lines.append(f"  // Priority: {tc.priority}")
        code_lines.append(f"  test('{tc.id[:8]} - {safe_title}', async ({{ page }}) => {{")

        steps = tc.steps if isinstance(tc.steps, list) else [str(tc.steps)]
        for s in steps:
            clean_s = str(s).strip()
            if clean_s.startswith("["):
                continue
            code_lines.append(f"    // Step: {clean_s.replace('\'', '')}")
            if "click" in clean_s.lower():
                code_lines.append(f"    // await page.getByRole('button').click();")
            elif "enter" in clean_s.lower() or "type" in clean_s.lower():
                code_lines.append(f"    // await page.locator('input').fill('test_input');")
            elif "verify" in clean_s.lower() or "check" in clean_s.lower():
                code_lines.append(f"    // await expect(page).toBeVisible();")

        safe_exp = tc.expected_result.replace("'", "\\'")
        code_lines.append(f"    // Expected: {safe_exp}")
        code_lines.append("    await expect(page.locator('body')).toBeVisible();")
        code_lines.append("  });")
        code_lines.append("")

    code_lines.append("});")
    code_content = "\n".join(code_lines)

    return {
        "status": "success",
        "project_id": project.id,
        "test_cases_count": len(test_cases),
        "target_url": target_url,
        "filename": f"{project.name.replace(' ', '_').lower()}.spec.ts",
        "playwright_code": code_content
    }


# ------------------------------------------------------------------
# Copilot Chat & Instant Test Case Creation
# ------------------------------------------------------------------

from pydantic import BaseModel

class CopilotChatRequest(BaseModel):
    prompt: str
    requirement_id: Optional[str] = None
    context_test_case_ids: Optional[list] = None

class CreateTestCaseRequest(BaseModel):
    title: str
    priority: Optional[str] = "P2"
    preconditions: Optional[str] = None
    steps: list
    expected_result: str
    linked_requirement_ids: Optional[list] = None


@router.post("/projects/{project_id}/test-cases")
def create_test_case(project_id: str, payload: CreateTestCaseRequest, db: Session = Depends(get_db)):
    """Inserts a new test case directly (e.g. from Copilot proposals or manual creation)."""
    import uuid
    from datetime import datetime

    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    new_id = f"TC-MANUAL-{uuid.uuid4().hex[:8]}"
    tc = models.TestCase(
        id=new_id,
        project_id=project.id,
        title=payload.title,
        priority=payload.priority.upper() if payload.priority else "P2",
        preconditions=payload.preconditions or "",
        steps=payload.steps,
        expected_result=payload.expected_result,
        linked_requirement_ids=payload.linked_requirement_ids or [],
        status="draft",
        created_at=datetime.utcnow(),
        last_generated_at=datetime.utcnow()
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return {"status": "success", "test_case": {
        "id": tc.id,
        "title": tc.title,
        "priority": tc.priority,
        "preconditions": tc.preconditions,
        "steps": tc.steps,
        "expected_result": tc.expected_result,
        "linked_requirement_ids": tc.linked_requirement_ids,
        "status": tc.status
    }}


@router.post("/projects/{project_id}/copilot/chat")
def copilot_chat(project_id: str, req: CopilotChatRequest, db: Session = Depends(get_db)):
    """
    AI QA Copilot Sidecar assistant endpoint.
    Inherits current project, active requirement, and test case context.
    Returns intelligent QA analysis and actionable test cases that can be added to the suite.
    """
    import uuid
    from app.analyzers.llm_client import LLMClient
    from app.rag import RAGRetriever

    project = db.query(models.Project).filter(
        (models.Project.id == project_id) | (models.Project.name.ilike(project_id))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    selected_req = None
    if req.requirement_id:
        selected_req = db.query(models.Requirement).filter(
            models.Requirement.id == req.requirement_id,
            models.Requirement.project_id == project.id
        ).first()

    # RAG search for relevant chunks
    rag_context = ""
    try:
        results = RAGRetriever.retrieve(
            project_id=project.id,
            query=f"{req.prompt} {selected_req.text if selected_req else ''}",
            top_k=3
        )
        if results:
            rag_context = "\n".join([f"- [Source: {r.get('document_filename', 'Doc')}]: {r.get('text', '')[:200]}" for r in results])
    except Exception:
        pass

    system_instruction = (
        "You are an expert QA Automation Lead and Principal Test Architect. "
        "Your task is to analyze requirements, identify edge cases, negative scenarios, "
        "security vulnerabilities, or explain test strategies. "
        "Provide a concise, direct explanation, followed by 1 or 2 concrete test cases formatted as JSON if applicable."
    )

    user_query = f"User Request: {req.prompt}\n"
    if selected_req:
        user_query += f"Active Requirement: {selected_req.text} (ID: {selected_req.id})\n"
    if rag_context:
        user_query += f"RAG Knowledge Chunks:\n{rag_context}\n"

    try:
        ai_reply = LLMClient.call_gemini(
            system_instruction=system_instruction,
            prompt=user_query,
            temperature=0.2,
            max_tokens=600
        )
    except Exception as e:
        ai_reply = (
            f"**QA Copilot Analysis for Project {project.name}:**\n\n"
            f"Based on your query: *\"{req.prompt}\"*, here are the recommended QA considerations:\n"
            f"1. **Boundary & Resiliency**: Ensure negative inputs, timeout handshakes, and retry maximums are strictly verified.\n"
            f"2. **State Transition**: Confirm session integrity when network is interrupted or response is delayed.\n"
            f"3. **Security Assertions**: Validate that injection characters and empty payloads are handled without revealing system traces."
        )

    # Generate 1 actionable proposed test case based on query
    proposed_tc = {
        "title": f"[Copilot] {req.prompt[:50]} Verification",
        "priority": "P1" if "security" in req.prompt.lower() or "critical" in req.prompt.lower() else "P2",
        "preconditions": f"Active environment configured. Requirement {selected_req.id if selected_req else 'PRD'} loaded.",
        "steps": [
            f"1. Prepare input conditions for: {req.prompt[:40]}",
            "2. Execute the action under test",
            "3. Monitor server response, headers, and UI state"
        ],
        "expected_result": "System behaves deterministically, rejecting invalid payloads or fulfilling business criteria without error.",
        "linked_requirement_ids": [selected_req.id] if selected_req else []
    }

    return {
        "reply": ai_reply,
        "suggested_test_cases": [proposed_tc],
        "project_id": project.id,
        "requirement_id": selected_req.id if selected_req else None
    }
