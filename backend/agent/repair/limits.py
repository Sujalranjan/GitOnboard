"""
Repair Limits & Attempt Accounting for GitOnBoard Engineering Agent.

Enforces:
  - Strict bounded attempt limits (repair_attempts <= max_repair_attempts)
  - Duration timeouts
  - Detection of repeated identical failure signatures / stagnation
  - Safe transition to BLOCKED when autonomy limits are exhausted
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Dict, List, Optional, Tuple

from backend.agent.repair.contracts import (
    DiagnosisContext,
    RepairAttempt,
    RepairConfig,
    RepairStatus,
)
from backend.agent.verification.contracts import VerificationResult

logger = logging.getLogger(__name__)


class RepairAttemptTracker:
    """
    Tracks and enforces limits across sequential repair cycles for tasks.
    """

    def __init__(self, config: Optional[RepairConfig] = None):
        self.config = config or RepairConfig()
        self._task_attempts: Dict[str, List[RepairAttempt]] = {}
        self._task_start_times: Dict[str, float] = {}
        self._task_failure_signatures: Dict[str, List[str]] = {}

    def start_attempt(
        self,
        task_id: str,
        diagnosis_id: str,
        defect_ids: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[RepairAttempt], Optional[str]]:
        """
        Checks eligibility and registers the start of a new repair attempt.
        Returns: (is_allowed, attempt_record, rejection_or_blocked_reason)
        """
        if task_id not in self._task_attempts:
            self._task_attempts[task_id] = []
            self._task_start_times[task_id] = time.time()
            self._task_failure_signatures[task_id] = []

        history = self._task_attempts[task_id]
        attempt_number = len(history) + 1

        # Check 1: Max repair attempts exceeded
        if attempt_number > self.config.max_repair_attempts:
            reason = (
                f"Maximum repair attempts ({self.config.max_repair_attempts}) exhausted for task '{task_id}'. "
                f"Task requires human intervention."
            )
            logger.warning(f"RepairAttemptTracker: {reason}")
            return False, None, reason

        # Check 2: Total repair duration exceeded
        elapsed = time.time() - self._task_start_times[task_id]
        if elapsed > self.config.max_repair_duration_sec:
            reason = (
                f"Maximum repair duration ({self.config.max_repair_duration_sec}s) exceeded for task '{task_id}' "
                f"(elapsed: {elapsed:.1f}s)."
            )
            logger.warning(f"RepairAttemptTracker: {reason}")
            return False, None, reason

        # Create attempt record
        attempt = RepairAttempt(
            task_id=task_id,
            attempt_number=attempt_number,
            diagnosis_id=diagnosis_id,
            status=RepairStatus.REPAIRING,
            defect_ids=defect_ids or [],
        )
        history.append(attempt)
        logger.info(f"RepairAttemptTracker: Started repair attempt #{attempt_number} for task '{task_id}'")
        return True, attempt, None

    def record_attempt_completion(
        self,
        task_id: str,
        attempt: RepairAttempt,
        changed_files: List[str],
        diff: Optional[str],
        verification_result: Optional[VerificationResult],
        stop_reason: Optional[str] = None,
    ) -> None:
        """
        Updates an attempt record with execution and verification outcomes.
        """
        attempt.changed_files = list(changed_files)
        attempt.diff = diff
        attempt.stop_reason = stop_reason

        if verification_result:
            attempt.verification_id = verification_result.verification_id
            attempt.verification_status = verification_result.status.value
            if verification_result.passed:
                attempt.status = RepairStatus.PASSED
            else:
                attempt.status = RepairStatus.FAILED
                attempt.failure_reason = verification_result.summary
        else:
            attempt.status = RepairStatus.FAILED
            attempt.failure_reason = stop_reason or "Verification not executed"

    def record_and_check_signature(
        self,
        task_id: str,
        diagnosis_context: DiagnosisContext,
        diff: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Calculates a deterministic failure/repair signature and detects stagnant loops.
        Returns: (is_valid, blocked_reason_if_repeated)
        """
        signature = self._compute_signature(diagnosis_context, diff)
        signatures = self._task_failure_signatures.setdefault(task_id, [])
        signatures.append(signature)

        # Check for streak of identical signatures
        max_rep = self.config.max_repeated_failure_signatures
        if len(signatures) >= max_rep:
            recent = signatures[-max_rep:]
            if all(s == signature for s in recent):
                reason = (
                    f"Repeated identical failure signature detected {max_rep} times without progress on task '{task_id}'. "
                    f"Halting repair loop to prevent infinite cycle."
                )
                logger.warning(f"RepairAttemptTracker: {reason}")
                return False, reason

        return True, None

    def get_attempts(self, task_id: str) -> List[RepairAttempt]:
        return list(self._task_attempts.get(task_id, []))

    def get_attempt_count(self, task_id: str) -> int:
        return len(self._task_attempts.get(task_id, []))

    def _compute_signature(self, diagnosis_context: DiagnosisContext, diff: Optional[str] = None) -> str:
        parts = [
            str(diagnosis_context.primary_category.value),
            ",".join(sorted(diagnosis_context.failing_checks)),
            ",".join(sorted(diagnosis_context.affected_files)),
        ]
        if diagnosis_context.defects:
            parts.append(diagnosis_context.defects[0].message[:100])
        if diff:
            parts.append(hashlib.md5(diff.encode("utf-8")).hexdigest())

        raw_str = "|".join(parts)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]
