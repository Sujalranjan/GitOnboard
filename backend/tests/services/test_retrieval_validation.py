"""
PART D Regression Tests: Stage 5 Retrieval Consistency

Tests for the validation fix that filters non-existent files from retrieval results.
Addresses A1 issue: Stage 5 was returning files that don't exist in FactStore.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.database import Base
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.models.fact_store import FactFile, FactSymbol
from backend.models.repository import Analysis, Repository
from backend.models.user import User


class TestRetrievalValidation:
    """Test that HybridRetriever filters invalid files after fusion."""

    @pytest.fixture
    def db(self) -> Session:
        """Create an in-memory SQLite database for testing."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()

    @pytest.fixture
    def setup_analysis(self, db: Session):
        """Create a test analysis with controlled FactStore entries."""
        # Create user
        user = User(
            github_id="test_user",
            username="test_user",
            email="test@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create repo
        repo = Repository(
            url="file:///test",
            user_id=user.id,
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

        # Create analysis
        analysis = Analysis(
            repository_id=repo.id,
            status="completed",
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        return analysis, db

    def test_valid_retrieved_file_passes_validation(self, setup_analysis):
        """Test that files that exist in FactStore pass validation."""
        analysis, db = setup_analysis

        # Add a valid file to FactStore
        valid_file = FactFile(
            id="file_1",
            analysis_id=analysis.id,
            path="backend/routers/auth.py",
            language="python",
            size=1024,
        )
        db.add(valid_file)
        db.commit()

        # Create retriever
        retriever = HybridRetriever(db=db, analysis_id=analysis.id)

        # Simulate candidates that include the valid file
        candidates = [
            {
                "id": "1",
                "file_path": "backend/routers/auth.py",
                "name": "github_login",
                "type": "symbol",
                "score_type": "lexical",
            }
        ]

        # Validate
        result = retriever._validate_file_existence(candidates)

        # Should pass through (not filtered)
        assert len(result) == 1
        assert result[0]["file_path"] == "backend/routers/auth.py"

    def test_nonexistent_file_filtered_out(self, setup_analysis):
        """Test that files not in FactStore are filtered out."""
        analysis, db = setup_analysis

        # Note: we don't add this file to FactStore
        missing_file_path = "backend/services/auth_service.py"

        # Create retriever
        retriever = HybridRetriever(db=db, analysis_id=analysis.id)

        # Simulate candidates that include a nonexistent file
        candidates = [
            {
                "id": "1",
                "file_path": missing_file_path,
                "name": "authenticate",
                "type": "symbol",
                "score_type": "lexical",
            }
        ]

        # Validate
        result = retriever._validate_file_existence(candidates)

        # Should be filtered out
        assert len(result) == 0

    def test_mixture_of_valid_and_invalid_files(self, setup_analysis):
        """Test that a mixture of valid and invalid files is properly filtered."""
        analysis, db = setup_analysis

        # Add one valid file
        valid_file = FactFile(
            id="file_auth",
            analysis_id=analysis.id,
            path="backend/routers/auth.py",
            language="python",
            size=1024,
        )
        db.add(valid_file)
        db.commit()

        # Create retriever
        retriever = HybridRetriever(db=db, analysis_id=analysis.id)

        # Simulate candidates with mix of valid and invalid files
        candidates = [
            {
                "id": "1",
                "file_path": "backend/routers/auth.py",
                "name": "github_login",
                "type": "symbol",
                "score_type": "lexical",
            },
            {
                "id": "2",
                "file_path": "backend/services/auth_service.py",  # Doesn't exist
                "name": "authenticate",
                "type": "symbol",
                "score_type": "lexical",
            },
            {
                "id": "3",
                "file_path": "backend/routers/auth.py",
                "name": "github_callback",
                "type": "symbol",
                "score_type": "exact_fact",
            },
        ]

        # Validate
        result = retriever._validate_file_existence(candidates)

        # Should have 2 results (both auth.py entries, the auth_service.py filtered out)
        assert len(result) == 2
        assert all(r["file_path"] == "backend/routers/auth.py" for r in result)

    def test_candidate_without_file_path_passes_through(self, setup_analysis):
        """Test that candidates without file_path are not filtered."""
        analysis, db = setup_analysis

        retriever = HybridRetriever(db=db, analysis_id=analysis.id)

        # Simulate candidate without file_path
        candidates = [
            {
                "id": "1",
                "file_path": "",  # Empty file path
                "name": "unknown",
                "type": "symbol",
            }
        ]

        # Validate
        result = retriever._validate_file_existence(candidates)

        # Should pass through (skip validation if no file_path)
        assert len(result) == 1

    def test_stale_metadata_filtered_correctly(self, setup_analysis):
        """Test that metadata from previous analysis versions is filtered."""
        analysis, db = setup_analysis

        # Add one file for current analysis
        current_file = FactFile(
            id="file_auth",
            analysis_id=analysis.id,
            path="backend/routers/auth.py",
            language="python",
            size=1024,
        )
        db.add(current_file)
        db.commit()

        # Create retriever
        retriever = HybridRetriever(db=db, analysis_id=analysis.id)

        # Simulate stale candidates (from previous analysis)
        stale_candidates = [
            {
                "id": "1",
                "file_path": "backend/routers/auth.py",
                "name": "github_login",
                "type": "symbol",
                "score_type": "lexical",
            },
            {
                "id": "2",
                "file_path": "backend/old_service.py",  # From previous version, no longer exists
                "name": "old_function",
                "type": "symbol",
                "score_type": "lexical",
            },
        ]

        # Validate
        result = retriever._validate_file_existence(stale_candidates)

        # Should keep only the current file
        assert len(result) == 1
        assert result[0]["file_path"] == "backend/routers/auth.py"

    def test_validation_with_no_analysis_id_returns_unchanged(self, db: Session):
        """Test that validation without analysis_id returns candidates unchanged."""
        # Create retriever without analysis_id
        retriever = HybridRetriever(db=db, analysis_id=None)

        candidates = [
            {"id": "1", "file_path": "some/file.py", "name": "test"},
        ]

        # Validate (should return unchanged because no analysis_id)
        result = retriever._validate_file_existence(candidates)

        assert len(result) == 1
        assert result[0]["file_path"] == "some/file.py"

    def test_validation_gracefully_handles_empty_file_list(self, setup_analysis):
        """Test that validation handles empty candidate list."""
        analysis, db = setup_analysis

        retriever = HybridRetriever(db=db, analysis_id=analysis.id)

        candidates = []

        # Validate
        result = retriever._validate_file_existence(candidates)

        assert len(result) == 0


class TestRetrievalFilteringIntegration:
    """Integration tests: verify filtering is applied in full retrieval flow."""

    @pytest.fixture
    def db(self) -> Session:
        """Create an in-memory SQLite database for testing."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()

    @pytest.fixture
    def setup_retrieval_test(self, db: Session):
        """Setup for integration tests."""
        # Create user
        user = User(
            github_id="test_user",
            username="test_user",
            email="test@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create repo with controlled FactStore
        repo = Repository(
            url="file:///test",
            user_id=user.id,
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

        analysis = Analysis(
            repository_id=repo.id,
            status="completed",
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        # Add a couple of valid files
        file1 = FactFile(
            id="file_auth",
            analysis_id=analysis.id,
            path="backend/routers/auth.py",
            language="python",
            size=1024,
        )
        file2 = FactFile(
            id="file_user",
            analysis_id=analysis.id,
            path="backend/models/user.py",
            language="python",
            size=512,
        )
        db.add_all([file1, file2])
        db.commit()

        return analysis, db

    def test_retrieval_filters_invalid_files_from_result(self, setup_retrieval_test):
        """Integration: invalid files are filtered from final retrieval results."""
        analysis, db = setup_retrieval_test

        # Create retriever
        retriever = HybridRetriever(
            db=db,
            analysis_id=analysis.id,
            enable_graph_expansion=False,
        )

        # Manually test the validation in context
        # (full retrieval test would require search indexes to be populated)
        candidates_before = [
            {"id": "1", "file_path": "backend/routers/auth.py", "name": "login"},
            {"id": "2", "file_path": "backend/services/auth_service.py", "name": "auth"},  # Doesn't exist
            {"id": "3", "file_path": "backend/models/user.py", "name": "User"},
        ]

        # Simulate the filtering
        candidates_after = retriever._validate_file_existence(candidates_before)

        # Verify filtering occurred
        assert len(candidates_before) == 3
        assert len(candidates_after) == 2
        assert all(
            c["file_path"] != "backend/services/auth_service.py"
            for c in candidates_after
        )
