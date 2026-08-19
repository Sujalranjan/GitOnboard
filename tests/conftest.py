"""
Pytest configuration for GitOnboard test suites.
Configures in-memory SQLite database and test environment isolation.
"""
import os

# Default to in-memory SQLite for test runs if DATABASE_URL is not explicitly set
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STORAGE_TYPE", "local")
os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
