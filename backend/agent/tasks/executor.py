"""
Task Execution Boundary Interface for GitOnBoard Engineering Agent.

Defines the isolated contract between the Task Orchestrator and the Task Implementation Layer:
  - TaskExecutor ABC: Abstract execution contract
  - DefaultTaskExecutor: Thin adapter / stub boundary for Phase 5 (prior to Phase 6 EngineeringAgentLoop)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import logging
import time
from typing import Any, Dict, Optional

from backend.agent.planning.contracts import PlanTaskStatus
from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult

logger = logging.getLogger(__name__)


class TaskExecutor(ABC):
    """
    Abstract interface defining the task execution boundary.
    Phase 5 isolates task scheduling and dependencies from the actual implementation reasoning.
    Phase 6 implements the interactive LLM/tool reasoning loop behind this interface.
    """

    @abstractmethod
    def execute(self, context: TaskExecutionContext) -> TaskExecutionResult:
        """
        Executes the given task within the supplied execution context.
        Returns a structured TaskExecutionResult.
        """
        pass


class DefaultTaskExecutor(TaskExecutor):
    """
    Thin adapter boundary for Phase 5 task orchestration.
    Performs structured execution handoff without premature Phase 6 implementation reasoning.
    """

    def __init__(self, simulate_failure: bool = False, failure_message: Optional[str] = None):
        self.simulate_failure = simulate_failure
        self.failure_message = failure_message

    def execute(self, context: TaskExecutionContext) -> TaskExecutionResult:
        start_time = time.perf_counter()
        task = context.task_definition
        logger.info(f"DefaultTaskExecutor: Executing task '{task.task_id}' ('{task.title}')")

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        if self.simulate_failure:
            err_msg = self.failure_message or f"Execution simulated failure for task '{task.task_id}'"
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                status=PlanTaskStatus.FAILED,
                summary=f"Task execution failed: {err_msg}",
                error=err_msg,
                duration_ms=round(duration_ms, 2),
            )

        return TaskExecutionResult(
            task_id=task.task_id,
            success=True,
            status=PlanTaskStatus.VERIFYING,
            summary=f"Task '{task.task_id}' executed successfully. Ready for verification.",
            changed_files=task.affected_files,
            observations=[f"Completed execution steps for: {task.title}"],
            duration_ms=round(duration_ms, 2),
        )
