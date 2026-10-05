"""
FastAPI app entry point.

Day 3 goal: app boots, empty DB tables exist, health-check endpoint works.
No real business logic yet - that starts on Day 4 (upload endpoint).
"""

from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import engine, Base, get_db
from app import models  # noqa: F401 - imported so Base knows about all tables
from app.routers import documents, projects, requirements, test_cases, rag, executions, api_testing, recorder

# Creates all tables defined in models.py if they don't already exist.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Test Case Generator — QA Copilot")
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(requirements.router)
app.include_router(test_cases.router)
app.include_router(rag.router)
app.include_router(executions.router)
app.include_router(api_testing.router)
app.include_router(recorder.router)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Confirms the app is running AND the database connection works."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.get("/")
@app.get("/review")
def get_unified_qa_ui():
    """Serves the Unified QA Copilot Workspace."""
    import os
    from fastapi.responses import FileResponse
    html_path = os.path.join(os.path.dirname(__file__), "static", "review.html")
    return FileResponse(html_path)


