"""
Verification Dispatcher & Handoff Boundary for GitOnBoard Engineering Agent.

Defines the isolated contract between the Task Orchestrator and the Verification Mesh:
  - VerificationDispatcher ABC: Abstract verification handoff
  - DefaultVerificationDispatcher: Thin adapter boundary for Phase 5 (prior to Phase 7 Verification Engine)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Optional, Tuple

from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult

logger = logging.getLogger(__name__)


class VerificationDispatcher(ABC):
    """
    Abstract interface defining the verification handoff boundary.
    The Task Orchestrator hands off the completed task to verification,
    which evaluates acceptance criteria and verification strategy.
    """

    @abstractmethod
    def verify_task(
        self,
        context: TaskExecutionContext,
        execution_result: TaskExecutionResult,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates verification strategy for the task.
        Returns:
            Tuple[bool, Optional[str]]: (passed, failure_reason)
        """
        pass


class DefaultVerificationDispatcher(VerificationDispatcher):
    """
    Thin verification adapter for Phase 5 task orchestration.
    Handoff boundary prior to Phase 7 automated verification engine.
    """

    def __init__(self, force_verdict: Optional[bool] = None, failure_message: Optional[str] = None):
        self.force_verdict = force_verdict
        self.failure_message = failure_message

    def verify_task(
        self,
        context: TaskExecutionContext,
        execution_result: TaskExecutionResult,
    ) -> Tuple[bool, Optional[str]]:
        task = context.task_definition
        strategy = task.verification_strategy or "verify_static"
        logger.info(f"DefaultVerificationDispatcher: Verifying task '{task.task_id}' using strategy '{strategy}'")

        if self.force_verdict is not None:
            if not self.force_verdict:
                return False, self.failure_message or f"Verification failed for task '{task.task_id}' ({strategy})"
            return True, None

        # By default, if execution succeeded, verification passes
        if not execution_result.success:
            return False, execution_result.error or "Execution failed prior to verification"

        return True, None
