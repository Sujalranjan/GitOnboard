"""
Pytest configuration for Phase 2M tests.

Provides fixtures for database access and real repository testing.
"""
import pytest
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.repository import Analysis, Repository


@pytest.fixture
def db() -> Session:
    """Provide a database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def analysis_in_db(db: Session) -> Analysis:
    """Get or create a test analysis in the database."""
    analysis = db.query(Analysis).first()
    if not analysis:
        # Create a test repository and analysis
        repo = Repository(
            name="test-repository",
            url="file:///home/dheeraj/repository_intelligence_platform",
            platform="local",
        )
        db.add(repo)
        db.flush()

        analysis = Analysis(
            repository_id=repo.id,
            status="completed",
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
    return analysis
