"""
Pytest configuration for Phase 2M tests.

Initializes test database with proper schema and fixtures for repository testing.
"""
import os
import pytest
from sqlalchemy.orm import Session

# Ensure test mode before importing database
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ["DEPLOYMENT_TYPE"] = "TEST"

from backend.database import Base, SessionLocal, engine
from backend.models.repository import Analysis, Repository
from backend.models.user import User
from backend.ai.service import LLMService
from backend.ai.providers.mock_tool_calling import ToolCallingMockProvider


@pytest.fixture(scope="session", autouse=True)
def init_test_db_session():
    """
    Initialize test database schema for entire test session.
    Creates all SQLAlchemy tables using metadata.
    This is session-scoped to run once at the start of all tests.
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup (optional - in-memory DB is destroyed anyway)
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Session:
    """Provide a database session for individual tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db: Session) -> User:
    """Get or create a test user for repository ownership."""
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(
            id=1,
            github_id="gh_test_1",
            username="test_user",
            email="test@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def test_repository(db: Session, test_user: User) -> Repository:
    """Create a test repository for Phase 2M testing."""
    repo = Repository(
        url="file:///home/dheeraj/repository_intelligence_platform",
        user_id=test_user.id,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@pytest.fixture
def test_analysis(db: Session, test_repository: Repository) -> Analysis:
    """Create a test analysis linked to test repository."""
    analysis = Analysis(
        repository_id=test_repository.id,
        status="completed",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@pytest.fixture(autouse=True)
def use_tool_calling_mock():
    """
    Use ToolCallingMockProvider for all Phase 2M tests.

    This allows validating the tool-calling pipeline without requiring
    a real LLM provider that supports the JSON protocol.
    """
    import backend.ai.service

    # Save original service instance
    original_service = backend.ai.service._service_instance

    # Create new service with ToolCallingMockProvider
    tool_calling_provider = ToolCallingMockProvider()
    mock_service = LLMService(providers=[tool_calling_provider])
    backend.ai.service._service_instance = mock_service

    yield

    # Restore original service
    backend.ai.service._service_instance = original_service
