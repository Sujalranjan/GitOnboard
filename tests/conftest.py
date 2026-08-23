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


@pytest.fixture(autouse=True, scope="session")
def configure_test_storage():
    """Ensure all tests use fast, deterministic InMemoryObjectStorage without Azurite/Azure timeouts."""
    storage = InMemoryObjectStorage()
    set_storage(storage)
    yield storage
