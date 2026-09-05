"""Real work-based progress tracking for repository analysis."""
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from backend.models.repository import Analysis, AnalysisJob

logger = logging.getLogger(__name__)

# Stage weights (must sum to 100)
# These define how much each stage contributes to overall progress
STAGE_WEIGHTS = {
    "Downloading": 5,
    "Scanning": 5,
    "Parsing": 30,
    "Symbol extraction": 20,
    "Building relationships": 15,
    "Persisting facts": 10,
    "Building indexes": 10,
    "Finalization": 5,
}


class ProgressTracker:
    """Track real work-based analysis progress."""

    def __init__(self, db: Session, analysis_id: int):
        self.db = db
        self.analysis_id = analysis_id
        self._update_counter = 0  # Throttle DB updates

    def update(
        self,
        stage: str,
        substage: Optional[str] = None,
        processed: int = 0,
        total: int = 0,
        unit: str = "items",
    ) -> None:
        """Update progress for current stage with real work metrics.

        Args:
            stage: Main stage name (e.g., "Parsing", "Symbol extraction")
            substage: Optional detailed substage (e.g., "Parsing Python files")
            processed: Number of work units completed
            total: Total work units (0 if unknown)
            unit: Unit name (e.g., "files", "symbols", "entities")
        """
        # Fetch current analysis and job
        analysis = self.db.query(Analysis).get(self.analysis_id)
        if not analysis:
            logger.error(f"Analysis {self.analysis_id} not found")
            return

        job = self.db.query(AnalysisJob).filter(
            AnalysisJob.analysis_id == self.analysis_id
        ).first()

        # Calculate stage-level progress (0.0 to 1.0)
        if total > 0:
            stage_progress = processed / total
        else:
            # If no total is known, assume stage is either complete (1.0) or incomplete
            # This happens for stages with unknown work units
            stage_progress = 1.0 if processed > 0 else 0.5

        # Calculate overall progress using weighted model
        overall_progress = self._calculate_overall_progress(
            analysis, stage, stage_progress
        )

        # Update analysis record
        analysis.progress_stage = stage
        analysis.progress_substage = substage or stage
        analysis.progress_percentage = overall_progress
        analysis.progress_processed = processed
        analysis.progress_total = total
        analysis.progress_unit = unit

        # Update job denormalized progress (for fast polling)
        if job:
            job.progress_percentage = overall_progress
            job.progress_details = {
                "stage": stage,
                "substage": substage or stage,
                "processed": processed,
                "total": total,
                "unit": unit,
                "message": self._format_message(stage, substage, processed, total, unit),
            }

        # Throttle database writes (update every ~10 updates or on stage completion)
        self._update_counter += 1
        if self._update_counter >= 10 or processed >= total:
            try:
                self.db.commit()
                self._update_counter = 0
            except Exception as e:
                logger.error(f"Failed to update progress: {e}")
                self.db.rollback()

    def _calculate_overall_progress(
        self, analysis: Analysis, current_stage: str, stage_progress: float
    ) -> int:
        """Calculate overall progress percentage (0-100) using weighted stages.

        This ensures progress is monotonic and derives from actual completed work.

        Args:
            analysis: Current Analysis record (tracks previous stage progress)
            current_stage: Name of current stage
            stage_progress: Progress within current stage (0.0 to 1.0)

        Returns:
            Overall progress percentage (0-100)
        """
        # Get stage weights
        stage_order = list(STAGE_WEIGHTS.keys())

        if current_stage not in STAGE_WEIGHTS:
            logger.warning(
                f"Unknown stage '{current_stage}', treating as single-unit progress"
            )
            stage_weight = 0
        else:
            stage_weight = STAGE_WEIGHTS[current_stage]

        # Sum weights of all completed stages
        current_stage_idx = (
            stage_order.index(current_stage) if current_stage in stage_order else -1
        )
        completed_weight = sum(
            STAGE_WEIGHTS.get(s, 0)
            for s in stage_order[: max(0, current_stage_idx)]
        )

        # Calculate overall progress
        # = (sum of completed stages) + (current stage weight * stage progress)
        overall = completed_weight + (stage_weight * stage_progress * 100)

        # Clamp to 0-99 (100 should only be set when truly complete)
        overall = max(0, min(99, int(overall)))

        # Ensure monotonicity: progress never decreases
        if (
            analysis.progress_percentage is not None
            and overall < analysis.progress_percentage
        ):
            logger.debug(
                f"Progress would regress from {analysis.progress_percentage} to {overall}, keeping current"
            )
            return analysis.progress_percentage

        return overall

    def mark_complete(self) -> None:
        """Mark analysis as 100% complete."""
        analysis = self.db.query(Analysis).get(self.analysis_id)
        job = self.db.query(AnalysisJob).filter(
            AnalysisJob.analysis_id == self.analysis_id
        ).first()

        if analysis:
            analysis.progress_percentage = 100
            analysis.progress_stage = "Completed"

        if job:
            job.progress_percentage = 100
            job.progress_details = {
                "stage": "Completed",
                "substage": "Analysis complete",
                "message": "Repository analysis completed",
            }

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to mark analysis complete: {e}")
            self.db.rollback()

    def mark_failed(self, error_msg: str = "") -> None:
        """Mark analysis as failed."""
        analysis = self.db.query(Analysis).get(self.analysis_id)
        job = self.db.query(AnalysisJob).filter(
            AnalysisJob.analysis_id == self.analysis_id
        ).first()

        if analysis:
            # Don't set progress to 100 on failure
            analysis.progress_stage = "Failed"

        if job:
            job.progress_details = {
                "stage": "Failed",
                "message": error_msg or "Analysis failed",
            }

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to mark analysis failed: {e}")
            self.db.rollback()

    @staticmethod
    def _format_message(
        stage: str,
        substage: Optional[str],
        processed: int,
        total: int,
        unit: str,
    ) -> str:
        """Format human-readable progress message."""
        if substage:
            if total > 0:
                return f"{substage} ({processed:,} / {total:,} {unit})"
            else:
                return f"{substage}"
        else:
            if total > 0:
                return f"{stage} ({processed:,} / {total:,} {unit})"
            else:
                return stage
