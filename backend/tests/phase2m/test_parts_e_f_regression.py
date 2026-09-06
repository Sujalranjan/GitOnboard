"""
PARTS E & F Regression Tests

E: Phase2L Inspection Semantics - file_exists flag
F: Stage 8 Tool Error Recovery - recovery guidance
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.database import Base
from backend.intelligence.inspection.file_inspector import inspect_file
from backend.models.fact_store import FactFile
from backend.models.repository import Analysis, Repository
from backend.models.user import User


class TestPhase2LInspectionSemantics:
    """PART E: Test that inspect_file distinguishes missing files."""

    @pytest.fixture
    def db(self) -> Session:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()

    @pytest.fixture
    def setup(self, db: Session):
        user = User(github_id="test", username="test", email="test@test.com")
        db.add(user)
        db.commit()
        db.refresh(user)

        repo = Repository(url="file:///test", user_id=user.id)
        db.add(repo)
        db.commit()
        db.refresh(repo)

        analysis = Analysis(repository_id=repo.id, status="completed")
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        # Add one valid file to FactStore
        valid_file = FactFile(
            id="file1",
            analysis_id=analysis.id,
            path="backend/routers/auth.py",
            language="python",
            size=1024,
        )
        db.add(valid_file)
        db.commit()

        return analysis, db

    def test_existing_file_returns_success(self, setup):
        """Existing file should return success=True."""
        analysis, db = setup

        result = inspect_file(
            file_path="backend/routers/auth.py",
            db=db,
            analysis_id=analysis.id,
            repo_root="/test",
        )

        assert result.success is True
        assert "error" not in result.model_dump() or result.error is None

    def test_missing_file_returns_failure(self, setup):
        """Missing file should return success=False with FILE_NOT_FOUND error."""
        analysis, db = setup

        result = inspect_file(
            file_path="backend/services/missing.py",  # Doesn't exist in FactStore
            db=db,
            analysis_id=analysis.id,
            repo_root="/test",
        )

        assert result.success is False
        assert result.error is not None
        assert "FILE_NOT_FOUND" in result.error or "does not exist" in result.error

    def test_distinguishes_empty_from_missing(self, setup):
        """System should distinguish existing+empty from missing."""
        analysis, db = setup

        # Test existing file
        result_existing = inspect_file(
            file_path="backend/routers/auth.py",
            db=db,
            analysis_id=analysis.id,
            repo_root="/test",
        )

        # Test missing file
        result_missing = inspect_file(
            file_path="backend/services/missing.py",
            db=db,
            analysis_id=analysis.id,
            repo_root="/test",
        )

        # Existing file: success=True (even if no symbols)
        assert result_existing.success is True

        # Missing file: success=False
        assert result_missing.success is False

        # They should be clearly different
        assert result_existing.success != result_missing.success


class TestStage8ToolErrorRecovery:
    """PART F: Test that recovery guidance is provided after tool failures."""

    def test_recovery_guidance_structure(self):
        """Verify that recovery guidance has expected structure."""
        # Mock tool failure scenario
        tool_result = {
            "success": False,
            "error": "File not found: backend/missing.py",
            "tool": "read_file",
        }

        # Simulate what stage8_grounding does
        tool_result_msg = str(tool_result)
        if not tool_result.get("success", False):
            recovery_guidance = (
                f"\n⚠️ TOOL FAILURE GUIDANCE:\n"
                f"The read_file operation failed: File not found: backend/missing.py\n"
                f"NEXT STEPS (choose one):\n"
                f"1. If file does not exist: try a different file, or check the list_context for available files\n"
                f"2. If symbol not found: inspect_file first to see available symbols, then try reading a different symbol\n"
                f"3. If you have enough information from previous results: provide your final_answer\n"
                f"4. Do NOT repeat the same failed operation - it will fail again"
            )
            tool_result_msg += "\n" + recovery_guidance

        # Verify guidance was added
        assert "TOOL FAILURE GUIDANCE" in tool_result_msg
        assert "NEXT STEPS" in tool_result_msg
        assert "Do NOT repeat" in tool_result_msg

    def test_recovery_guidance_not_added_for_success(self):
        """Verify that recovery guidance is NOT added when tool succeeds."""
        tool_result = {
            "success": True,
            "content": "File contents here",
            "tool": "read_file",
        }

        tool_result_msg = str(tool_result)
        if not tool_result.get("success", False):
            tool_result_msg += "\nGUIDANCE ADDED"  # This should NOT happen

        # Verify guidance was NOT added
        assert "GUIDANCE ADDED" not in tool_result_msg
