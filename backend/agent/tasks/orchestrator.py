"""
Task Orchestrator Engine for GitOnBoard Engineering Agent.

Controls the execution flow of an approved implementation plan:
  - Authoritative dependency DAG evaluation
  - Deterministic task selection: (step_number, task_id)
  - Downstream failure/block propagation with explicit blocked_reason
  - Sequential execution enforcement
  - Task lifecycle transition coordination
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Tuple

from backend.agent.planning.contracts import Plan, PlanStatus, PlanTask, PlanTaskStatus
from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult
from backend.agent.tasks.executor import DefaultTaskExecutor, TaskExecutor
from backend.agent.tasks.state_machine import InvalidTaskStateTransitionError, TaskStateMachine
from backend.agent.tasks.verification import DefaultVerificationDispatcher, VerificationDispatcher

logger = logging.getLogger(__name__)


class TaskOrchestratorError(Exception):
    """Base exception for task orchestration errors."""
    pass


class TaskOrchestrator:
    """
    Orchestrates the dependency graph and lifecycle execution of tasks in an approved Plan.
    Enforces deterministic task eligibility, state transitions, and failure propagation.
    """

    def __init__(
        self,
        executor: Optional[TaskExecutor] = None,
        verifier: Optional[VerificationDispatcher] = None,
    ):
        self.executor = executor or DefaultTaskExecutor()
        self.verifier = verifier or DefaultVerificationDispatcher()
        self.state_machine = TaskStateMachine()

    def evaluate_dependencies(self, plan: Plan) -> Dict[str, PlanTaskStatus]:
        """
        Evaluates the dependency DAG for all tasks in the plan.
        - Unlocks PENDING tasks to READY if all dependencies are PASSED (or none exist).
        - Propagates BLOCKED to PENDING tasks if any upstream dependency FAILED, BLOCKED, or SKIPPED.
        - Preserves existing RUNNING, VERIFYING, and terminal statuses.
        Returns a mapping of task_id -> updated PlanTaskStatus.
        """
        task_map: Dict[str, PlanTask] = {t.task_id: t for t in plan.tasks}
        updated_statuses: Dict[str, PlanTaskStatus] = {}

        # Multiple passes to handle transitive dependencies correctly
        changed = True
        while changed:
            changed = False
            for task in plan.tasks:
                current_status = task.status

                # Ignore active or terminal tasks
                if current_status in (
                    PlanTaskStatus.RUNNING,
                    PlanTaskStatus.VERIFYING,
                    PlanTaskStatus.PASSED,
                    PlanTaskStatus.FAILED,
                    PlanTaskStatus.BLOCKED,
                    PlanTaskStatus.SKIPPED,
                ):
                    updated_statuses[task.task_id] = current_status
                    continue

                # For PENDING tasks, evaluate upstream dependencies
                if current_status == PlanTaskStatus.PENDING:
                    deps = task.dependencies or []

                    if not deps:
                        # No dependencies -> directly eligible to be READY
                        self.state_machine.validate_transition(task.task_id, current_status, PlanTaskStatus.READY)
                        task.status = PlanTaskStatus.READY
                        updated_statuses[task.task_id] = PlanTaskStatus.READY
                        changed = True
                        logger.info(f"TaskOrchestrator: Unlocked task '{task.task_id}' (no dependencies) -> READY")
                        continue

                    # Check upstream dependencies
                    has_failed_dep = False
                    failed_dep_id = None
                    failed_dep_status = None
                    all_passed = True

                    for dep_id in deps:
                        dep_task = task_map.get(dep_id)
                        if not dep_task:
                            has_failed_dep = True
                            failed_dep_id = dep_id
                            failed_dep_status = "MISSING"
                            all_passed = False
                            break

                        if dep_task.status in (
                            PlanTaskStatus.FAILED,
                            PlanTaskStatus.BLOCKED,
                            PlanTaskStatus.SKIPPED,
                        ):
                            has_failed_dep = True
                            failed_dep_id = dep_id
                            failed_dep_status = dep_task.status.value
                            all_passed = False
                            break

                        if dep_task.status != PlanTaskStatus.PASSED:
                            all_passed = False

                    if has_failed_dep:
                        # Propagate block
                        self.state_machine.validate_transition(
                            task.task_id,
                            current_status,
                            PlanTaskStatus.BLOCKED,
                            reason=f"Upstream dependency '{failed_dep_id}' is '{failed_dep_status}'",
                        )
                        task.status = PlanTaskStatus.BLOCKED
                        task.blocked_reason = f"Blocked because upstream dependency '{failed_dep_id}' is {failed_dep_status}"
                        task.completed_at = datetime.now(timezone.utc)
                        updated_statuses[task.task_id] = PlanTaskStatus.BLOCKED
                        changed = True
                        logger.warning(f"TaskOrchestrator: Blocked task '{task.task_id}' -> {task.blocked_reason}")

                    elif all_passed:
                        # All dependencies passed -> READY
                        self.state_machine.validate_transition(task.task_id, current_status, PlanTaskStatus.READY)
                        task.status = PlanTaskStatus.READY
                        updated_statuses[task.task_id] = PlanTaskStatus.READY
                        changed = True
                        logger.info(f"TaskOrchestrator: Unlocked task '{task.task_id}' (all {len(deps)} deps PASSED) -> READY")
                    else:
                        updated_statuses[task.task_id] = PlanTaskStatus.PENDING

        return updated_statuses

    def get_ready_tasks(self, plan: Plan) -> List[PlanTask]:
        """
        Returns all tasks currently in READY state, sorted deterministically by (step_number, task_id).
        """
        ready = [t for t in plan.tasks if t.status == PlanTaskStatus.READY]
        return sorted(ready, key=lambda t: (t.step_number, t.task_id))

    def select_next_task(self, plan: Plan) -> Optional[PlanTask]:
        """
        Deterministically selects the next eligible task to execute.
        Evaluates dependencies first, then picks the first READY task by (step_number, task_id).
        """
        self.evaluate_dependencies(plan)
        ready_tasks = self.get_ready_tasks(plan)
        if ready_tasks:
            selected = ready_tasks[0]
            logger.info(f"TaskOrchestrator: Selected next eligible task '{selected.task_id}' ('{selected.title}')")
            return selected
        return None

    def start_task(self, plan: Plan, task_id: str) -> PlanTask:
        """
        Transitions a task from READY -> RUNNING.
        Enforces plan approval and task eligibility.
        """
        if plan.status != PlanStatus.APPROVED:
            raise TaskOrchestratorError(
                f"Cannot start task on plan '{plan.plan_id}' in status '{plan.status.value}'. Plan must be APPROVED."
            )

        task = self._find_task(plan, task_id)
        if task.status != PlanTaskStatus.READY:
            raise TaskOrchestratorError(
                f"Cannot start task '{task_id}' in status '{task.status.value}'. Task must be in READY state."
            )

        self.state_machine.validate_transition(task.task_id, task.status, PlanTaskStatus.RUNNING)
        task.status = PlanTaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        task.attempt_count += 1
        task.updated_at = datetime.now(timezone.utc)
        logger.info(f"TaskOrchestrator: Started task '{task.task_id}' (attempt {task.attempt_count}) -> RUNNING")
        return task

    def complete_task_execution(
        self,
        plan: Plan,
        task_id: str,
        exec_result: TaskExecutionResult,
    ) -> PlanTask:
        """
        Records the outcome of the TaskExecutor boundary.
        Transitions RUNNING -> VERIFYING (on execution success) or RUNNING -> FAILED (on execution error).
        """
        task = self._find_task(plan, task_id)
        if task.status != PlanTaskStatus.RUNNING:
            raise TaskOrchestratorError(
                f"Cannot complete execution for task '{task_id}' in status '{task.status.value}'. Expected RUNNING."
            )

        if not exec_result.success:
            self.state_machine.validate_transition(task.task_id, task.status, PlanTaskStatus.FAILED)
            task.status = PlanTaskStatus.FAILED
            task.failure_reason = exec_result.error or "Execution failed"
            task.completed_at = datetime.now(timezone.utc)
            logger.error(f"TaskOrchestrator: Task '{task.task_id}' execution failed: {task.failure_reason}")
            # Propagate failure to downstream dependencies immediately
            self.evaluate_dependencies(plan)
        else:
            self.state_machine.validate_transition(task.task_id, task.status, PlanTaskStatus.VERIFYING)
            task.status = PlanTaskStatus.VERIFYING
            logger.info(f"TaskOrchestrator: Task '{task.task_id}' execution completed -> VERIFYING")

        task.metadata["last_execution_result"] = exec_result.model_dump(mode="json")
        return task

    def record_verification_result(
        self,
        plan: Plan,
        task_id: str,
        passed: bool,
        error: Optional[str] = None,
    ) -> PlanTask:
        """
        Records verification verdict.
        Transitions VERIFYING -> PASSED or VERIFYING -> FAILED, then re-evaluates dependency DAG.
        """
        task = self._find_task(plan, task_id)
        if task.status != PlanTaskStatus.VERIFYING:
            raise TaskOrchestratorError(
                f"Cannot record verification for task '{task_id}' in status '{task.status.value}'. Expected VERIFYING."
            )

        if passed:
            self.state_machine.validate_transition(task.task_id, task.status, PlanTaskStatus.PASSED)
            task.status = PlanTaskStatus.PASSED
            task.completed_at = datetime.now(timezone.utc)
            task.failure_reason = None
            logger.info(f"TaskOrchestrator: Task '{task.task_id}' passed verification -> PASSED")
        else:
            self.state_machine.validate_transition(task.task_id, task.status, PlanTaskStatus.FAILED)
            task.status = PlanTaskStatus.FAILED
            task.failure_reason = error or "Verification criteria not met"
            task.completed_at = datetime.now(timezone.utc)
            logger.warning(f"TaskOrchestrator: Task '{task.task_id}' failed verification -> FAILED: {task.failure_reason}")

        # Update dependent tasks
        self.evaluate_dependencies(plan)
        return task

    def record_repair_result(
        self,
        plan: Plan,
        task_id: str,
        repair_result: Any,
    ) -> PlanTask:
        """
        Records the outcome of a Phase 8 repair loop execution.
        Transitions task to PASSED, BLOCKED, or FAILED and propagates dependencies.
        """
        task = self._find_task(plan, task_id)
        
        target_status = PlanTaskStatus.FAILED
        if getattr(repair_result, "passed", False) or getattr(repair_result, "status", None) == "PASSED":
            target_status = PlanTaskStatus.PASSED
        elif getattr(repair_result, "status", None) == "BLOCKED":
            target_status = PlanTaskStatus.BLOCKED
        elif getattr(repair_result, "status", None) == "CANCELLED":
            target_status = PlanTaskStatus.FAILED

        self.state_machine.validate_transition(task.task_id, task.status, target_status)
        task.status = target_status
        task.completed_at = datetime.now(timezone.utc)
        task.metadata["last_repair_result"] = (
            repair_result.model_dump(mode="json") if hasattr(repair_result, "model_dump") else str(repair_result)
        )

        if target_status == PlanTaskStatus.PASSED:
            task.failure_reason = None
            logger.info(f"TaskOrchestrator: Task '{task.task_id}' repaired and verified -> PASSED")
        elif target_status == PlanTaskStatus.BLOCKED:
            task.blocked_reason = getattr(repair_result, "stop_reason", None) or getattr(repair_result, "summary", "Repair limit exhausted")
            logger.warning(f"TaskOrchestrator: Task '{task.task_id}' repair blocked -> BLOCKED: {task.blocked_reason}")
        else:
            task.failure_reason = getattr(repair_result, "summary", "Repair failed")
            logger.warning(f"TaskOrchestrator: Task '{task.task_id}' repair failed -> FAILED: {task.failure_reason}")

        self.evaluate_dependencies(plan)
        return task

    def is_plan_complete(self, plan: Plan) -> bool:
        """Returns True if all tasks in the plan are in a terminal state."""
        return all(self.state_machine.is_terminal(t.status) for t in plan.tasks)

    def all_tasks_passed(self, plan: Plan) -> bool:
        """Returns True if all tasks in the plan have reached PASSED."""
        return len(plan.tasks) > 0 and all(t.status == PlanTaskStatus.PASSED for t in plan.tasks)

    def has_failed_tasks(self, plan: Plan) -> bool:
        """Returns True if any task has reached FAILED or BLOCKED."""
        return any(t.status in (PlanTaskStatus.FAILED, PlanTaskStatus.BLOCKED) for t in plan.tasks)

    def _find_task(self, plan: Plan, task_id: str) -> PlanTask:
        for t in plan.tasks:
            if t.task_id == task_id:
                return t
        raise TaskOrchestratorError(f"Task '{task_id}' not found in plan '{plan.plan_id}'")
