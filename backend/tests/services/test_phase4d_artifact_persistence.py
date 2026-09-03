"""
Phase 4-D: Artifact Persistence Tests

Verify that rebuilt BM25 artifacts are persisted correctly and can be
loaded fresh on subsequent retriever initializations without rebuilding.
"""

import pytest
import uuid
from backend.intelligence.retrieval.artifact_persistence import (
    persist_rebuilt_bm25, get_bm25_artifact
)


def test_persistence_requires_version():
    """Test that persistence fails if fact_store_version is missing from BM25 data."""
    # BM25 data without fact_store_version should fail
    bm25_data = {
        "documents": [],
        "idf": {},
        "doc_len": [],
        "corpus_size": 0,
        "avg_doc_len": 0.0,
        # Missing: "fact_store_version"
    }

    # Mock database and analysis
    class MockDB:
        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return None
        def commit(self):
            pass
        def rollback(self):
            pass

    current_version = str(uuid.uuid4())
    result = persist_rebuilt_bm25(
        db=MockDB(),
        analysis_id=1,
        bm25_data=bm25_data,
        current_fact_store_version=current_version,
    )

    assert result is False


def test_persistence_version_mismatch():
    """Test that persistence fails if BM25 version doesn't match current FactStore version."""
    version_a = str(uuid.uuid4())
    version_b = str(uuid.uuid4())

    bm25_data = {
        "documents": [],
        "idf": {},
        "doc_len": [],
        "corpus_size": 0,
        "avg_doc_len": 0.0,
        "fact_store_version": version_a,  # Mismatch!
    }

    class MockDB:
        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return None
        def commit(self):
            pass
        def rollback(self):
            pass

    result = persist_rebuilt_bm25(
        db=MockDB(),
        analysis_id=1,
        bm25_data=bm25_data,
        current_fact_store_version=version_b,  # Different version
    )

    assert result is False


def test_persistence_with_matching_versions():
    """Test that persistence succeeds with matching versions."""
    version = str(uuid.uuid4())

    bm25_data = {
        "documents": [{"id": "1", "text": "test"}],
        "idf": {"test": 0.5},
        "doc_len": [1],
        "corpus_size": 1,
        "avg_doc_len": 1.0,
        "fact_store_version": version,
    }

    class MockDB:
        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return None
        def add(self, obj):
            self.added_obj = obj
        def flush(self):
            pass
        def commit(self):
            pass
        def rollback(self):
            pass

    db = MockDB()
    result = persist_rebuilt_bm25(
        db=db,
        analysis_id=1,
        bm25_data=bm25_data,
        current_fact_store_version=version,
    )

    assert result is True


def test_persistence_updates_existing_artifact():
    """Test that persistence updates existing artifact instead of creating new one."""
    version_old = str(uuid.uuid4())
    version_new = str(uuid.uuid4())

    old_data = {
        "documents": [{"id": "old", "text": "old"}],
        "idf": {"old": 0.5},
        "doc_len": [1],
        "corpus_size": 1,
        "avg_doc_len": 1.0,
        "fact_store_version": version_old,
    }

    new_data = {
        "documents": [{"id": "new", "text": "new"}],
        "idf": {"new": 0.5},
        "doc_len": [1],
        "corpus_size": 1,
        "avg_doc_len": 1.0,
        "fact_store_version": version_new,
    }

    class MockArtifact:
        def __init__(self):
            self.data = old_data
            self.updated = False

    class MockDB:
        def __init__(self):
            self.artifact = MockArtifact()

        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return self.artifact
        def flush(self):
            pass
        def commit(self):
            self.artifact.updated = True
        def rollback(self):
            pass

    db = MockDB()
    result = persist_rebuilt_bm25(
        db=db,
        analysis_id=1,
        bm25_data=new_data,
        current_fact_store_version=version_new,
    )

    assert result is True
    assert db.artifact.data == new_data  # Data should be updated
    assert db.artifact.updated is True


def test_persistence_creates_new_artifact_if_none_exists():
    """Test that persistence creates new artifact if none exists."""
    version = str(uuid.uuid4())

    bm25_data = {
        "documents": [{"id": "1", "text": "test"}],
        "idf": {"test": 0.5},
        "doc_len": [1],
        "corpus_size": 1,
        "avg_doc_len": 1.0,
        "fact_store_version": version,
    }

    class MockDB:
        def __init__(self):
            self.added = None

        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return None  # No existing artifact
        def add(self, obj):
            self.added = obj
        def flush(self):
            pass
        def commit(self):
            pass
        def rollback(self):
            pass

    db = MockDB()
    result = persist_rebuilt_bm25(
        db=db,
        analysis_id=1,
        bm25_data=bm25_data,
        current_fact_store_version=version,
    )

    assert result is True
    assert db.added is not None  # Should have created new artifact


def test_rollback_on_failure():
    """Test that database is rolled back if persistence fails."""
    version = str(uuid.uuid4())

    bm25_data = {
        "documents": [{"id": "1", "text": "test"}],
        "idf": {"test": 0.5},
        "doc_len": [1],
        "corpus_size": 1,
        "avg_doc_len": 1.0,
        "fact_store_version": version,
    }

    class MockDB:
        def __init__(self):
            self.rolled_back = False

        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return None
        def add(self, obj):
            pass
        def flush(self):
            pass
        def commit(self):
            raise Exception("Database error")
        def rollback(self):
            self.rolled_back = True

    db = MockDB()
    result = persist_rebuilt_bm25(
        db=db,
        analysis_id=1,
        bm25_data=bm25_data,
        current_fact_store_version=version,
    )

    assert result is False
    assert db.rolled_back is True  # Should have rolled back


def test_bm25_data_must_have_document_count():
    """Test that persisted BM25 includes document count."""
    version = str(uuid.uuid4())

    bm25_data = {
        "documents": [
            {"id": "1", "text": "test1"},
            {"id": "2", "text": "test2"},
        ],
        "idf": {"test": 0.5},
        "doc_len": [1, 1],
        "corpus_size": 2,  # Must match document count
        "avg_doc_len": 1.0,
        "fact_store_version": version,
    }

    class MockDB:
        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return None
        def add(self, obj):
            self.added_data = obj.data
        def flush(self):
            pass
        def commit(self):
            pass
        def rollback(self):
            pass

    db = MockDB()
    result = persist_rebuilt_bm25(
        db=db,
        analysis_id=1,
        bm25_data=bm25_data,
        current_fact_store_version=version,
    )

    assert result is True
    assert db.added_data["corpus_size"] == 2


def test_get_bm25_artifact():
    """Test retrieval of BM25 artifact."""
    class MockArtifact:
        def __init__(self):
            self.type = "bm25_index"
            self.data = {"test": "data"}

    class MockDB:
        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return MockArtifact()

    db = MockDB()
    artifact = get_bm25_artifact(db, analysis_id=1)

    assert artifact is not None
    assert artifact.type == "bm25_index"
    assert artifact.data == {"test": "data"}


def test_get_bm25_artifact_not_found():
    """Test retrieval when BM25 artifact doesn't exist."""
    class MockDB:
        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return None

    db = MockDB()
    artifact = get_bm25_artifact(db, analysis_id=1)

    assert artifact is None


def test_persistence_preserves_factstore_version_after_rebuild():
    """
    Test 4-D lifecycle: Fresh BM25 persisted contains FactStore version.

    After rebuilding stale BM25 and persisting, the artifact must have
    the current FactStore version so future loads are FRESH.
    """
    version_fresh = str(uuid.uuid4())

    rebuilt_data = {
        "documents": [{"id": "1", "name": "login"}],
        "idf": {"login": 0.5},
        "doc_len": [1],
        "corpus_size": 1,
        "avg_doc_len": 1.0,
        "fact_store_version": version_fresh,
    }

    class MockDB:
        def query(self, model):
            return self
        def filter(self, *args):
            return self
        def first(self):
            return None
        def add(self, obj):
            self.persisted_data = obj.data
        def flush(self):
            pass
        def commit(self):
            pass
        def rollback(self):
            pass

    db = MockDB()
    result = persist_rebuilt_bm25(
        db=db,
        analysis_id=1,
        bm25_data=rebuilt_data,
        current_fact_store_version=version_fresh,
    )

    assert result is True
    # Persisted data must have version for future freshness check
    assert db.persisted_data["fact_store_version"] == version_fresh
