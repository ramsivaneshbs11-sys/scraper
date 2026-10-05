"""
Database engine + session setup.

SQLite for local/V1 development. Swapping to PostgreSQL later only
requires changing DATABASE_URL - the rest of the code stays the same,
because SQLAlchemy abstracts the actual SQL dialect.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./test_case_generator.db"

# check_same_thread=False is needed only for SQLite when used with FastAPI,
# since FastAPI can use multiple threads for a single request.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class that all SQLAlchemy models (in models.py) inherit from.
Base = declarative_base()


def get_db():
    """FastAPI dependency: gives each request its own DB session, and
    always closes it afterward, even if the request fails."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
