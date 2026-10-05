"""
Seed initial sample project and user into SQLite database.
Allows testing document uploads via FastAPI Swagger docs or automated tests.
"""

from app.database import SessionLocal
from app.models import User, Project

def seed():
    db = SessionLocal()
    try:
        # Create default admin user if not exists
        user = db.query(User).filter(User.id == "u1").first()
        if not user:
            user = User(
                id="u1",
                email="admin@example.com",
                name="Admin User",
                role="admin"
            )
            db.add(user)
            db.commit()
            print("Created user: u1 (admin@example.com)")
        else:
            print("User u1 already exists.")

        # Create default project if not exists
        project = db.query(Project).filter(Project.id == "p1").first()
        if not project:
            project = Project(
                id="p1",
                name="UPSC Chatbot",
                description="AI Chatbot for UPSC exam prep",
                created_by="u1"
            )
            db.add(project)
            db.commit()
            print("Created project: p1 (UPSC Chatbot)")
        else:
            print("Project p1 already exists.")

    finally:
        db.close()

if __name__ == "__main__":
    seed()
