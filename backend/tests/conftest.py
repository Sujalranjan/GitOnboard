"""
Pytest configuration for backend test suites.
Configures in-memory SQLite database, in-memory storage, and test environment isolation.
"""
import os
import pytest

# Default to in-memory SQLite and test mode for test runs
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STORAGE_TYPE", "memory")
os.environ["DEPLOYMENT_TYPE"] = "TEST"
