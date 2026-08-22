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

    def execute_task(self, context: TaskExecutionContext) -> TaskExecutionResult:
        """Alias for execute()."""
        return self.execute(context)


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


class EngineeringAgentTaskExecutor(TaskExecutor):
    """
    Phase 6 TaskExecutor adapter executing tasks via the controlled EngineeringAgentLoop.
    Maps structured AgentExecutionResult into standard TaskExecutionResult for Phase 7 verification.
    """

    def __init__(
        self,
        loop: Optional[Any] = None,
        config: Optional[Any] = None,
        agent_loop: Optional[Any] = None,
    ):
        actual_loop = loop or agent_loop
        if actual_loop is None:
            from backend.agent.loop import EngineeringAgentLoop
            self.loop = EngineeringAgentLoop()
        else:
            self.loop = actual_loop
        self.config = config

    def execute(self, context: TaskExecutionContext) -> TaskExecutionResult:
        logger.info(f"EngineeringAgentTaskExecutor: Running EngineeringAgentLoop for task '{context.task_id}'")
        agent_result = self.loop.run(
            task_context=context,
            config=self.config,
        )

        is_success = (agent_result.status == "COMPLETED_FOR_VERIFICATION")
        target_status = PlanTaskStatus.VERIFYING if is_success else PlanTaskStatus.FAILED

        summary_text = (
            agent_result.completion_signal.summary
            if agent_result.completion_signal
            else f"Task stopped: {agent_result.status} (Reason: {agent_result.stop_reason.value})"
        )

        return TaskExecutionResult(
            task_id=context.task_id,
            success=is_success,
            status=target_status,
            summary=summary_text,
            changed_files=agent_result.changed_files,
            tool_calls=agent_result.tool_calls,
            observations=agent_result.observations,
            error=agent_result.error,
            duration_ms=agent_result.duration_ms,
            metadata={
                "stop_reason": agent_result.stop_reason.value,
                "iterations": agent_result.iterations,
                "tool_call_count": agent_result.tool_call_count,
                "diff": agent_result.diff,
                **agent_result.metadata,
            },
        )
