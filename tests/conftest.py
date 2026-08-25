"""
Pytest configuration for GitOnboard test suites.
Configures in-memory SQLite database, in-memory storage, and test environment isolation.
"""
import os
import pytest

# Default to in-memory SQLite and test mode for test runs
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STORAGE_TYPE", "memory")
os.environ.setdefault("DEPLOYMENT_TYPE", "TEST")

from backend.storage import InMemoryObjectStorage, set_storage
from backend.database import Base, SessionLocal, engine
from backend.dependencies.auth import get_current_user
from backend.main import app
from backend.models.user import User
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True, scope="session")
def configure_test_storage():
    """Ensure all tests use fast, deterministic InMemoryObjectStorage without Azurite/Azure timeouts."""
    storage = InMemoryObjectStorage()
    set_storage(storage)
    yield storage


@pytest.fixture(autouse=True)
def init_test_db():
    """Ensure database tables exist and a default test user (id=1) is present for all tests."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            user = User(id=1, github_id="gh_test_1", username="test_user", email="test@example.com")
            db.add(user)
            db.commit()
    yield


@pytest.fixture
def client():
    """Default authenticated TestClient fixture for test suites in tests/."""
    def override_get_current_user():
        with SessionLocal() as db:
            return db.query(User).filter(User.id == 1).first()

    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
