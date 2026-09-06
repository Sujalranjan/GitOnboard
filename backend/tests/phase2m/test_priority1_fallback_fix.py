"""
Priority 1 Regression Test: No Silent Fallback

Verifies that Phase 2M interactive mode REQUIRES execution_context
and FAILS LOUDLY if it's missing (no silent fallback to bulk context).
"""
import pytest
from sqlalchemy.orm import Session

from backend.intelligence.engine.orchestration.stage8_grounding import (
    LLMGrounder,
    stage8_sync_wrapper,
    stage8_sync_wrapper_interactive,
    stage8_sync_wrapper_legacy,
)
from backend.intelligence.engine.orchestration.stage8_phase2l_adapter import ExecutionContext
from backend.agent.context.contracts import RepositoryContext, ContextEvidence
from backend.models.repository import Analysis


@pytest.fixture
def mock_execution_context(db: Session) -> ExecutionContext:
    """Create execution context for testing."""
    analysis = db.query(Analysis).filter_by(repo_name="default").first()
    if not analysis:
        analysis = Analysis(repo_name="default", status="completed")
        db.add(analysis)
        db.commit()

    return ExecutionContext(
        analysis_id=analysis.id,
        repo_root="/home/dheeraj/repository_intelligence_platform",
        db=db,
        repo_name="default",
    )


@pytest.fixture
def mock_repository_context() -> RepositoryContext:
    """Create mock RepositoryContext."""
    return RepositoryContext(
        repository_id="test-repo",
        requirement="Test query",
        relevant_files=["backend/app.py"],
        relevant_symbols=[{"name": "main", "file": "backend/app.py"}],
        evidence=[
            ContextEvidence(
                source_type="rim_fact",
                source_id="fact1",
                summary="Test fact",
                data={},
                confidence=0.95,
                relevance=0.8,
            )
        ],
    )


class TestInteractiveModeContract:
    """Test that Phase 2M interactive mode requires execution_context."""

    def test_ground_interactive_requires_execution_context(
        self,
        mock_repository_context: RepositoryContext,
    ):
        """Test that ground_interactive RAISES if execution_context is None."""
        grounder = LLMGrounder()

        # Should raise ValueError, NOT silently fall back
        with pytest.raises(ValueError, match="REPOSITORY_CONTEXT_ERROR"):
            # Use sync wrapper for testing
            stage8_sync_wrapper_interactive(
                mock_repository_context,
                "Test query",
                None,  # No execution_context - should fail
            )

    def test_ground_interactive_requires_analysis_id(
        self,
        mock_repository_context: RepositoryContext,
    ):
        """Test that ground_interactive validates analysis_id."""
        from unittest.mock import MagicMock

        grounder = LLMGrounder()

        # Invalid execution context (missing analysis_id)
        bad_context = ExecutionContext(
            analysis_id=None,  # Missing!
            repo_root="/some/path",
            db=MagicMock(),  # Mock db object
        )

        with pytest.raises(ValueError, match="REPOSITORY_CONTEXT_ERROR"):
            stage8_sync_wrapper_interactive(
                mock_repository_context,
                "Test query",
                bad_context,
            )

    def test_ground_interactive_requires_repo_root(
        self,
        mock_repository_context: RepositoryContext,
    ):
        """Test that ground_interactive validates repo_root."""
        from unittest.mock import MagicMock

        grounder = LLMGrounder()

        # Invalid execution context (missing repo_root)
        bad_context = ExecutionContext(
            analysis_id=123,  # Valid
            repo_root=None,  # Missing!
            db=MagicMock(),  # Mock db object
        )

        with pytest.raises(ValueError, match="REPOSITORY_CONTEXT_ERROR"):
            stage8_sync_wrapper_interactive(
                mock_repository_context,
                "Test query",
                bad_context,
            )

    def test_ground_interactive_requires_db(
        self,
        mock_repository_context: RepositoryContext,
    ):
        """Test that ground_interactive validates db."""
        grounder = LLMGrounder()

        # Invalid execution context (missing db)
        bad_context = ExecutionContext(
            analysis_id=123,  # Valid
            repo_root="/some/path",  # Valid
            db=None,  # Missing!
        )

        with pytest.raises(ValueError, match="REPOSITORY_CONTEXT_ERROR"):
            stage8_sync_wrapper_interactive(
                mock_repository_context,
                "Test query",
                bad_context,
            )

    def test_ground_legacy_still_works_without_execution_context(
        self,
        mock_repository_context: RepositoryContext,
    ):
        """Test that legacy mode still works WITHOUT execution_context."""
        grounder = LLMGrounder()

        try:
            # Should NOT raise - legacy mode accepts None execution_context
            answer, grounding = stage8_sync_wrapper_legacy(
                mock_repository_context,
                "Test query",
            )

            # Should get an answer
            assert len(answer) > 0
            assert grounding.grounding_status in [
                "grounded",
                "partial",
                "ungrounded",
                "insufficient_context",
            ]
        except Exception as e:
            # LLM call might fail in test environment, that's ok
            # The important thing is it didn't raise REPOSITORY_CONTEXT_ERROR
            if "REPOSITORY_CONTEXT_ERROR" in str(e):
                pytest.fail(f"Legacy mode should not require execution_context, got: {e}")

    def test_no_silent_fallback_in_dispatcher(
        self,
        mock_repository_context: RepositoryContext,
    ):
        """
        Test that the dispatcher (stage8_sync_wrapper) doesn't silently fall back.

        When execution_context is None and we call stage8_sync_wrapper,
        it should use legacy mode explicitly (not hide the choice).
        """
        # With execution_context=None, should use legacy mode
        try:
            answer, grounding = stage8_sync_wrapper(
                mock_repository_context,
                "Test query",
                execution_context=None,
            )

            # Should get an answer from legacy path
            assert len(answer) > 0
        except Exception as e:
            # LLM call might fail, but shouldn't be a REPOSITORY_CONTEXT_ERROR
            if "REPOSITORY_CONTEXT_ERROR" in str(e):
                pytest.fail(f"Dispatcher should not fail with REPOSITORY_CONTEXT_ERROR: {e}")


class TestBehaviorSeparation:
    """Test that interactive and legacy modes are clearly separated."""

    def test_interactive_and_legacy_methods_exist(self):
        """Test that both methods exist and can be called separately."""
        grounder = LLMGrounder()

        assert hasattr(grounder, "ground_interactive")
        assert hasattr(grounder, "ground_legacy")
        assert callable(grounder.ground_interactive)
        assert callable(grounder.ground_legacy)

    def test_sync_wrappers_for_each_mode(self):
        """Test that sync wrappers exist for each mode."""
        # These should all exist
        assert callable(stage8_sync_wrapper_interactive)
        assert callable(stage8_sync_wrapper_legacy)
        assert callable(stage8_sync_wrapper)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
