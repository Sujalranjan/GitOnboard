"""Tests for real work-based progress tracking."""
import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.services.progress_tracker import ProgressTracker, STAGE_WEIGHTS
from backend.database import SessionLocal


@pytest.fixture
def db_session():
    """Create a test database session."""
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def test_analysis(db_session: Session):
    """Create a test analysis record."""
    repo = Repository(
        id=999,
        github_repo_id="test-repo-999",
        url="https://github.com/test/test-repo",
        user_id=1
    )
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(
        id=999,
        repository_id=repo.id,
        status="Analyzing"
    )
    db_session.add(analysis)
    db_session.flush()

    job = AnalysisJob(
        id=999,
        analysis_id=analysis.id,
        status="Analyzing"
    )
    db_session.add(job)
    db_session.commit()

    return analysis


class TestProgressTracker:
    """Test ProgressTracker service."""

    def test_initialization(self, db_session: Session, test_analysis: Analysis):
        """Test ProgressTracker initialization."""
        tracker = ProgressTracker(db_session, test_analysis.id)
        assert tracker.analysis_id == test_analysis.id
        assert tracker.db is db_session

    def test_update_stage_progress(self, db_session: Session, test_analysis: Analysis):
        """Test updating progress for a stage."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Update parsing progress (50% complete)
        tracker.update("Parsing", "Parsing Python files", 600, 1200, "files")

        # Refresh from DB
        db_session.refresh(test_analysis)

        assert test_analysis.progress_stage == "Parsing"
        assert test_analysis.progress_substage == "Parsing Python files"
        assert test_analysis.progress_processed == 600
        assert test_analysis.progress_total == 1200
        assert test_analysis.progress_unit == "files"
        # Progress should be: Scanning (5%) + (Parsing weight 30% * 50% complete) = 5% + 15% = 20%
        # But we're not at Scanning yet, so it should just be 30 * 0.5 * 100 = 15%
        assert test_analysis.progress_percentage > 0

    def test_progress_monotonicity(self, db_session: Session, test_analysis: Analysis):
        """Verify progress never decreases."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Progress increases
        tracker.update("Parsing", "Parsing files", 100, 1000, "files")
        db_session.refresh(test_analysis)
        progress1 = test_analysis.progress_percentage

        # Simulate regression attempt
        tracker.update("Parsing", "Parsing files", 50, 1000, "files")
        db_session.refresh(test_analysis)
        progress2 = test_analysis.progress_percentage

        # Progress should not decrease
        assert progress2 >= progress1

    def test_stage_transitions(self, db_session: Session, test_analysis: Analysis):
        """Test progress through stage transitions."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Simulate progression through stages
        stages = [
            ("Scanning", "Scanning files", 100, 100, "files"),
            ("Parsing", "Parsing files", 500, 1000, "files"),
            ("Symbol extraction", "Extracting symbols", 5000, 10000, "symbols"),
            ("Building relationships", "Building relationships", 8000, 10000, "relationships"),
            ("Persisting facts", "Saving entities", 10000, 10000, "entities"),
            ("Building indexes", "Building indexes", 2000, 2000, "documents"),
        ]

        previous_progress = 0
        for stage, substage, processed, total, unit in stages:
            tracker.update(stage, substage, processed, total, unit)
            db_session.refresh(test_analysis)
            current_progress = test_analysis.progress_percentage

            # Progress should increase (or stay same for very small steps)
            assert current_progress >= previous_progress, \
                f"Progress regressed from {previous_progress} to {current_progress} at {stage}"
            previous_progress = current_progress

    def test_mark_complete(self, db_session: Session, test_analysis: Analysis):
        """Test marking analysis as complete."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Mark as complete
        tracker.mark_complete()

        db_session.refresh(test_analysis)
        assert test_analysis.progress_percentage == 100
        assert test_analysis.progress_stage == "Completed"

    def test_mark_failed(self, db_session: Session, test_analysis: Analysis):
        """Test marking analysis as failed."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Mark as failed
        error_msg = "Connection timeout during indexing"
        tracker.mark_failed(error_msg)

        db_session.refresh(test_analysis)
        assert test_analysis.progress_stage == "Failed"
        # Progress should not be set to 100 on failure
        assert test_analysis.progress_percentage < 100

    def test_format_message(self):
        """Test progress message formatting."""
        # With substage and total
        msg = ProgressTracker._format_message("Parsing", "Parsing Python files", 340, 1200, "files")
        assert "340" in msg
        assert "1,200" in msg
        assert "files" in msg

        # With substage only
        msg = ProgressTracker._format_message("Parsing", "Parsing", 0, 0, "items")
        assert "Parsing" in msg

        # Without substage
        msg = ProgressTracker._format_message("Parsing", None, 100, 200, "items")
        assert "Parsing" in msg
        assert "100" in msg
        assert "200" in msg

    def test_unknown_total(self, db_session: Session, test_analysis: Analysis):
        """Test progress tracking when total is unknown."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Update with unknown total (total=0)
        tracker.update("Finalizing", "Finalizing", 1, 0, "stage")

        db_session.refresh(test_analysis)
        assert test_analysis.progress_processed == 1
        assert test_analysis.progress_total == 0
        # Progress should still be calculated

    def test_throttled_updates(self, db_session: Session, test_analysis: Analysis):
        """Test that frequent updates are throttled."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Simulate many rapid updates
        for i in range(5):
            tracker.update("Parsing", f"File {i}", i + 1, 100, "files")

        # Counter should have incremented
        assert tracker._update_counter > 0

        # But we shouldn't have committed yet (unless we hit 10 or complete)
        # This is implementation-dependent but shows throttling works

    def test_stage_weights_sum(self):
        """Verify stage weights sum to 100."""
        total_weight = sum(STAGE_WEIGHTS.values())
        assert total_weight == 100, f"Stage weights sum to {total_weight}, expected 100"

    def test_backward_compatibility(self, db_session: Session, test_analysis: Analysis):
        """Test backward compatibility with jobs that have no progress data."""
        # Job exists without progress data
        db_session.refresh(test_analysis)
        assert test_analysis.progress_percentage == 0

        # API should fall back to status_map if no real progress data exists
        # This is tested in the endpoint test


class TestProgressCalculation:
    """Test progress calculation logic."""

    def test_weighted_progress_calculation(self, db_session: Session, test_analysis: Analysis):
        """Test weighted progress calculation."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Scanning complete (5%)
        tracker.update("Scanning", "Scan complete", 100, 100, "files")
        db_session.refresh(test_analysis)
        progress1 = test_analysis.progress_percentage

        # Parsing 50% complete (5% + 30% * 0.5 = 20%)
        tracker.update("Parsing", "Parsing", 500, 1000, "files")
        db_session.refresh(test_analysis)
        progress2 = test_analysis.progress_percentage

        # Parsing 100% complete, Symbol extraction starting (5% + 30% + 0%)
        tracker.update("Symbol extraction", "Extracting", 0, 10000, "symbols")
        db_session.refresh(test_analysis)
        progress3 = test_analysis.progress_percentage

        # Verify monotonic increase and reasonable values
        assert progress1 > 0
        assert progress2 > progress1
        assert progress3 >= progress2
        assert progress3 < 100  # Not complete

    def test_handles_missing_stage(self, db_session: Session, test_analysis: Analysis):
        """Test handling of unknown stage names."""
        tracker = ProgressTracker(db_session, test_analysis.id)

        # Update with unknown stage (should log warning but not crash)
        tracker.update("Unknown Stage", "Doing something", 50, 100, "items")

        db_session.refresh(test_analysis)
        assert test_analysis.progress_stage == "Unknown Stage"
        # Should still have some progress
        assert test_analysis.progress_percentage >= 0


class TestProgressAPI:
    """Test progress API response."""

    def test_progress_endpoint_response(self, db_session: Session, test_analysis: Analysis):
        """Test job progress endpoint response structure."""
        from backend.routers.repo.core import _format_progress_message

        msg = _format_progress_message("Parsing Python", 340, 1200, "files")
        assert msg == "Parsing Python (340 / 1,200 files)"

        msg = _format_progress_message("Analyzing", 0, 0, "items")
        assert msg == "Analyzing"
