"""
Pytest configuration for backend test suites.
Configures in-memory SQLite database, in-memory storage, and test environment isolation.
"""
import os
import pytest

# Default to in-memory SQLite and test mode for test runs
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STORAGE_TYPE", "memory")
# NOTE: Only set DEPLOYMENT_TYPE if not already set via command line or env
# This allows DEPLOYMENT_TYPE=LOCAL for real LLM testing with pytest
os.environ.setdefault("DEPLOYMENT_TYPE", "TEST")
