"""
Task State Machine & Lifecycle Transitions for GitOnBoard Engineering Agent.

Defines the formal state machine governing individual PlanTask instances:
  - Valid transition matrix
  - Terminal state locking (PASSED, FAILED, BLOCKED, SKIPPED)
  - Strict transition validation and error handling
"""
from __future__ import annotations

import logging
from typing import Dict, List, Set

from backend.agent.planning.contracts import PlanTaskStatus

logger = logging.getLogger(__name__)


class InvalidTaskStateTransitionError(Exception):
    """Raised when an illegal task state transition is requested."""
    def __init__(self, task_id: str, from_status: PlanTaskStatus, to_status: PlanTaskStatus, reason: str = ""):
        self.task_id = task_id
        self.from_status = from_status
        self.to_status = to_status
        msg = f"Invalid task state transition for '{task_id}': cannot move from '{from_status.value}' to '{to_status.value}'"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class TaskStateMachine:
    """
    State machine managing task lifecycle transitions according to strict architectural contracts.
    """

    # Allowed forward transitions from each status
    ALLOWED_TRANSITIONS: Dict[PlanTaskStatus, Set[PlanTaskStatus]] = {
        PlanTaskStatus.PENDING: {
            PlanTaskStatus.READY,
            PlanTaskStatus.BLOCKED,
            PlanTaskStatus.SKIPPED,
        },
        PlanTaskStatus.READY: {
            PlanTaskStatus.RUNNING,
            PlanTaskStatus.BLOCKED,
            PlanTaskStatus.SKIPPED,
        },
        PlanTaskStatus.RUNNING: {
            PlanTaskStatus.VERIFYING,
            PlanTaskStatus.FAILED,
            PlanTaskStatus.BLOCKED,
        },
        PlanTaskStatus.VERIFYING: {
            PlanTaskStatus.PASSED,
            PlanTaskStatus.FAILED,
            PlanTaskStatus.DIAGNOSING,
            PlanTaskStatus.BLOCKED,
        },
        PlanTaskStatus.DIAGNOSING: {
            PlanTaskStatus.REPAIRING,
            PlanTaskStatus.BLOCKED,
            PlanTaskStatus.FAILED,
        },
        PlanTaskStatus.REPAIRING: {
            PlanTaskStatus.REVERIFYING,
            PlanTaskStatus.BLOCKED,
            PlanTaskStatus.FAILED,
        },
        PlanTaskStatus.REVERIFYING: {
            PlanTaskStatus.PASSED,
            PlanTaskStatus.DIAGNOSING,
            PlanTaskStatus.FAILED,
            PlanTaskStatus.BLOCKED,
        },
        PlanTaskStatus.FAILED: {
            PlanTaskStatus.DIAGNOSING,
            PlanTaskStatus.REPAIRING,
            PlanTaskStatus.BLOCKED,
            PlanTaskStatus.PASSED,
        },
        # Terminal states have no forward transitions
        PlanTaskStatus.PASSED: set(),
        PlanTaskStatus.BLOCKED: set(),
        PlanTaskStatus.SKIPPED: set(),
    }

    TERMINAL_STATES: Set[PlanTaskStatus] = {
        PlanTaskStatus.PASSED,
        PlanTaskStatus.FAILED,
        PlanTaskStatus.BLOCKED,
        PlanTaskStatus.SKIPPED,
    }

    @classmethod
    def is_terminal(cls, status: PlanTaskStatus) -> bool:
        """Returns True if the task status is terminal (cannot transition further)."""
        return status in cls.TERMINAL_STATES

    @classmethod
    def can_transition(cls, from_status: PlanTaskStatus, to_status: PlanTaskStatus) -> bool:
        """Returns True if moving from from_status to to_status is allowed."""
        if from_status == to_status:
            return True
        allowed = cls.ALLOWED_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    @classmethod
    def validate_transition(
        cls,
        task_id: str,
        from_status: PlanTaskStatus,
        to_status: PlanTaskStatus,
        reason: str = "",
    ) -> None:
        """
        Validates the transition. Raises InvalidTaskStateTransitionError if illegal.
        """
        if from_status == to_status:
            return

        if not cls.can_transition(from_status, to_status):
            if cls.is_terminal(from_status) and not cls.ALLOWED_TRANSITIONS.get(from_status):
                raise InvalidTaskStateTransitionError(
                    task_id=task_id,
                    from_status=from_status,
                    to_status=to_status,
                    reason=f"Task '{task_id}' is in terminal status '{from_status.value}' and cannot transition further",
                )
            raise InvalidTaskStateTransitionError(
                task_id=task_id,
                from_status=from_status,
                to_status=to_status,
                reason=reason or f"Transition not permitted in lifecycle matrix",
            )

        logger.debug(f"TaskStateMachine: '{task_id}' transitioning from '{from_status.value}' -> '{to_status.value}'")
