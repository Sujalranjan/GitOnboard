"""
Pytest configuration for backend test suites.
Configures in-memory SQLite database, in-memory storage, and test environment isolation.
"""
import os
import pytest
from sqlalchemy.orm import Session

# Default to in-memory SQLite and test mode for test runs
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STORAGE_TYPE", "memory")
# NOTE: Only set DEPLOYMENT_TYPE if not already set via command line or env
# This allows DEPLOYMENT_TYPE=LOCAL for real LLM testing with pytest
os.environ.setdefault("DEPLOYMENT_TYPE", "TEST")

from backend.database import Base, SessionLocal, engine


@pytest.fixture(scope="session", autouse=True)
def init_test_db_session():
    """Initialize test database schema for entire test session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Session:
    """Provide a database session for individual tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
