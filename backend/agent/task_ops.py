"""
Task execution and recovery operations for EngineeringAgent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.agent.planning.contracts import Plan, PlanTask, PlanTaskStatus
from backend.agent.tasks import TaskExecutionContext, TaskExecutionResult
from backend.models.implementation import (
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentState,
    AgentStateTransition,
)

if TYPE_CHECKING:
    from backend.agent.engineering_agent import EngineeringAgent

logger = logging.getLogger(__name__)


class EngineeringAgentTaskOps:
    """Encapsulates task orchestration steps, execution loops, run completion, and restart recovery."""

    def __init__(self, agent: "EngineeringAgent"):
        self.agent = agent

    def start_plan_execution(
        self,
        db: Session,
        run_id: str,
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """
        Initiates controlled execution of an approved implementation plan.
        Transitions run state from AWAITING_APPROVAL -> EXECUTING and marks initial eligible tasks READY.
        """
        from backend.agent.engineering_agent import EngineeringAgentError
        run = self.agent.get_run(db, run_id)
        if user_id is not None and run.user_id is not None and run.user_id != user_id:
            raise EngineeringAgentError(f"Execution not authorized: User '{user_id}' does not own run '{run_id}'")

        if run.current_state == AgentState.EXECUTING:
            logger.info(f"Run '{run_id}' is already in EXECUTING state. Returning current state idempotently.")
            return run

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot start execution for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        self.agent.assert_execution_authorized(db, run_id, user_id=user_id)

        plan = self.agent.get_plan(db, run_id)
        if not plan:
            raise EngineeringAgentError(f"No plan found for run '{run_id}'")

        self.agent.task_orchestrator.evaluate_dependencies(plan)

        meta = run.metadata_json or {}
        meta["plan"] = plan.model_dump(mode="json")
        run.metadata_json = meta
        flag_modified(run, "metadata_json")
        db.add(run)
        db.commit()

        self.agent.transition_state(
            db,
            run.id,
            to_state=AgentState.EXECUTING,
            reason=f"Plan '{plan.plan_id}' approved; starting controlled execution of {len(plan.tasks)} tasks",
        )

        for task in plan.tasks:
            if task.status == PlanTaskStatus.READY:
                self.agent.events.emit_event(
                    db,
                    run,
                    AgentEventType.TASK_READY,
                    f"Task '{task.task_id}' ('{task.title}') is READY for execution.",
                    {"task_id": task.task_id, "step_number": task.step_number},
                )

        return run

    def get_plan_tasks(self, db: Session, run_id: str) -> List[PlanTask]:
        """Returns all PlanTask items with current lifecycle statuses for the run."""
        plan = self.agent.get_plan(db, run_id)
        if not plan:
            return []
        self.agent.task_orchestrator.evaluate_dependencies(plan)
        return plan.tasks

    def get_plan_task(self, db: Session, run_id: str, task_id: str) -> Optional[PlanTask]:
        """Retrieves a single PlanTask by task_id."""
        plan = self.agent.get_plan(db, run_id)
        if not plan:
            return None
        return next((t for t in plan.tasks if t.task_id == task_id), None)

    def get_next_task(self, db: Session, run_id: str) -> Optional[PlanTask]:
        """Deterministically selects the next eligible task to execute according to DAG dependencies."""
        plan = self.agent.get_plan(db, run_id)
        if not plan:
            return None
        return self.agent.task_orchestrator.select_next_task(plan)

    def execute_next_task(
        self,
        db: Session,
        run_id: str,
    ) -> Tuple[Optional[PlanTask], Optional[TaskExecutionResult]]:
        """Executes the next eligible task sequentially."""
        from backend.agent.engineering_agent import EngineeringAgentError
        run = self.agent.get_run(db, run_id)
        if run.current_state != AgentState.EXECUTING:
            raise EngineeringAgentError(
                f"Cannot execute tasks for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.EXECUTING.value}' state."
            )

        self.agent.assert_execution_authorized(db, run_id)

        plan = self.agent.get_plan(db, run_id)
        if not plan or plan.status != plan.status.APPROVED:
            raise EngineeringAgentError(f"No approved plan found for run '{run_id}'")

        next_task = self.agent.task_orchestrator.select_next_task(plan)
        if not next_task:
            return None, None

        task_id = next_task.task_id

        self.agent.events.emit_event(
            db,
            run,
            AgentEventType.NEXT_TASK_SELECTED,
            f"Selected next eligible task '{task_id}': '{next_task.title}'",
            {"task_id": task_id, "step_number": next_task.step_number},
        )

        self.agent.task_orchestrator.start_task(plan, task_id)
        self.agent.events.emit_event(
            db,
            run,
            AgentEventType.TASK_STARTED,
            f"Started executing task '{task_id}': '{next_task.title}'",
            {"task_id": task_id, "step_number": next_task.step_number},
        )

        repo_ctx = (run.metadata_json or {}).get("repository_context", {})
        exec_ctx = TaskExecutionContext(
            agent_run_id=run.id,
            plan_id=plan.plan_id,
            task_id=task_id,
            repository_id=run.repository_id,
            worktree_path=run.worktree_path,
            task_definition=next_task,
            repository_context_summary=repo_ctx,
            execution_config=(run.metadata_json or {}).get("config", {}),
        )

        exec_result = self.agent.task_orchestrator.executor.execute(exec_ctx)
        self.agent.task_orchestrator.complete_task_execution(plan, task_id, exec_result)

        if exec_result.success:
            self.agent.events.emit_event(
                db,
                run,
                AgentEventType.TASK_EXECUTION_COMPLETED,
                f"Task '{task_id}' execution completed in {exec_result.duration_ms:.1f}ms: {exec_result.summary}",
                {"task_id": task_id, "duration_ms": exec_result.duration_ms, "changed_files": exec_result.changed_files},
            )

            self.agent.events.emit_event(
                db,
                run,
                AgentEventType.TASK_VERIFYING,
                f"Verifying task '{task_id}' criteria ({next_task.verification_strategy})...",
                {"task_id": task_id, "verification_strategy": next_task.verification_strategy},
            )
            passed, v_err = self.agent.task_orchestrator.verifier.verify_task(exec_ctx, exec_result)
            self.agent.task_orchestrator.record_verification_result(plan, task_id, passed, v_err)

            if passed:
                self.agent.events.emit_event(
                    db,
                    run,
                    AgentEventType.TASK_PASSED,
                    f"Task '{task_id}' passed verification criteria.",
                    {"task_id": task_id},
                )
            else:
                self.agent.events.emit_event(
                    db,
                    run,
                    AgentEventType.TASK_FAILED,
                    f"Task '{task_id}' failed verification: {v_err}",
                    {"task_id": task_id, "failure_reason": v_err},
                )
        else:
            self.agent.events.emit_event(
                db,
                run,
                AgentEventType.TASK_EXECUTION_FAILED,
                f"Task '{task_id}' execution failed: {exec_result.error}",
                {"task_id": task_id, "error": exec_result.error},
            )
            self.agent.events.emit_event(
                db,
                run,
                AgentEventType.TASK_FAILED,
                f"Task '{task_id}' failed: {exec_result.error}",
                {"task_id": task_id, "failure_reason": exec_result.error},
            )

        for t in plan.tasks:
            if t.task_id != task_id:
                if t.status == PlanTaskStatus.BLOCKED and not t.metadata.get("blocked_event_emitted"):
                    t.metadata["blocked_event_emitted"] = True
                    self.agent.events.emit_event(
                        db,
                        run,
                        AgentEventType.TASK_BLOCKED,
                        f"Task '{t.task_id}' is BLOCKED: {t.blocked_reason}",
                        {"task_id": t.task_id, "blocked_reason": t.blocked_reason},
                    )
                elif t.status == PlanTaskStatus.READY and not t.metadata.get("ready_event_emitted"):
                    t.metadata["ready_event_emitted"] = True
                    self.agent.events.emit_event(
                        db,
                        run,
                        AgentEventType.TASK_READY,
                        f"Task '{t.task_id}' ('{t.title}') is now READY.",
                        {"task_id": t.task_id},
                    )

        meta = run.metadata_json or {}
        meta["plan"] = plan.model_dump(mode="json")
        run.metadata_json = meta
        flag_modified(run, "metadata_json")
        db.add(run)
        db.commit()

        if self.agent.task_orchestrator.all_tasks_passed(plan):
            logger.info(f"All {len(plan.tasks)} tasks in plan '{plan.plan_id}' passed! Ready for Phase 7 final verification.")

        return self.agent.task_orchestrator._find_task(plan, task_id), exec_result

    def complete_run(
        self,
        db: Session,
        run_id: str,
        success: bool = True,
        failure_reason: Optional[str] = None,
    ) -> AgentRun:
        """Marks a run as COMPLETED or FAILED after all tasks have been executed and verified."""
        run = self.agent.get_run(db, run_id)

        if run.current_state not in (AgentState.EXECUTING, AgentState.VERIFYING):
            logger.warning(f"Run '{run_id}' is in state {run.current_state.value}, expected EXECUTING or VERIFYING")
            return run

        target_state = AgentState.COMPLETED if success else AgentState.FAILED
        reason = failure_reason or "All tasks completed" if success else "Task execution or verification failed"

        self.agent.transition_state(db, run_id, target_state, reason)

        if not success:
            self.agent.events.emit_event(
                db,
                run,
                AgentEventType.RUN_FAILED,
                f"Run failed: {failure_reason or 'One or more tasks failed'}",
                {"failure_reason": failure_reason},
            )
        else:
            self.agent.events.emit_event(
                db,
                run,
                AgentEventType.RUN_COMPLETED,
                "Run completed successfully with all tasks passed",
                {},
            )

        return run

    def recover_in_flight_runs(self, db: Session) -> List[str]:
        """
        Restart recovery: Detects non-terminal runs interrupted by a server reboot
        and transitions them safely to FAILED with explicit failure reason.
        """
        active_states = [
            AgentState.IDLE,
            AgentState.UNDERSTANDING,
            AgentState.PLANNING,
            AgentState.AWAITING_APPROVAL,
            AgentState.EXECUTING,
            AgentState.VERIFYING,
        ]

        orphaned = db.query(AgentRun).filter(AgentRun.current_state.in_(active_states)).all()
        recovered_ids: List[str] = []

        for run in orphaned:
            logger.warning(f"EngineeringAgent recovery: Terminating interrupted run '{run.id}' (state: {run.current_state.value})")

            meta = run.metadata_json or {}
            plan_dict = meta.get("plan")
            if plan_dict and isinstance(plan_dict, dict):
                try:
                    plan = Plan.model_validate(plan_dict)
                    for t in plan.tasks:
                        if t.status in (PlanTaskStatus.RUNNING, PlanTaskStatus.VERIFYING):
                            t.status = PlanTaskStatus.BLOCKED
                            t.blocked_reason = "Server restart interrupted active task execution"
                            t.completed_at = datetime.now(timezone.utc)
                    meta["plan"] = plan.model_dump(mode="json")
                    run.metadata_json = meta
                    flag_modified(run, "metadata_json")
                except Exception as err:
                    logger.warning(f"Recovery: failed to update plan tasks for run '{run.id}': {err}")

            run.error_message = "Server restart interrupted active execution"
            run.completed_at = datetime.now(timezone.utc)
            run.current_state = AgentState.FAILED
            run.status = AgentRunStatus.FAILED
            run.updated_at = datetime.now(timezone.utc)

            transition = AgentStateTransition(
                agent_run_id=run.id,
                from_state=run.current_state,
                to_state=AgentState.FAILED,
                reason="Server restart recovery",
                timestamp=datetime.now(timezone.utc),
            )
            db.add(transition)
            db.add(run)
            recovered_ids.append(run.id)

        if recovered_ids:
            db.commit()
            logger.info(f"EngineeringAgent recovery: Successfully recovered {len(recovered_ids)} interrupted run(s)")

        return recovered_ids
