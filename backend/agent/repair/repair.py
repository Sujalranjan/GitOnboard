"""
RepairController: Coordinates bounded Failure Diagnosis, Agentic Repair, and Re-Verification.

Core Invariants:
  1. Reuses EngineeringAgentLoop (Phase 6) and VerificationDispatcher (Phase 7).
  2. Bounded execution: enforces max attempts, timeouts, and repeated failure signatures.
  3. Re-verification is mandatory: a task only passes when Phase 7 Judge confirms evidence.
  4. Real-time event logging via AgentEventCoordinator and metadata persistence in PostgreSQL.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.loop import (
    AgentExecutionResult,
    AgentLoopConfig,
    EngineeringAgentLoop,
    StopReason,
)
from backend.agent.planning.contracts import PlanTask, PlanTaskStatus
from backend.agent.repair.contracts import (
    DiagnosisContext,
    RepairAttempt,
    RepairConfig,
    RepairResult,
    RepairStatus,
)
from backend.agent.repair.diagnosis import FailureDiagnosisController
from backend.agent.repair.limits import RepairAttemptTracker
from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult
from backend.agent.verification.contracts import VerificationResult, VerificationStatus
from backend.agent.verification.dispatcher import VerificationDispatcher
from backend.models.implementation import AgentEventType, AgentRun

logger = logging.getLogger(__name__)


class RepairController:
    """
    Orchestrates the bounded diagnosis -> repair -> re-verification loop.
    """

    def __init__(
        self,
        agent_loop: Optional[EngineeringAgentLoop] = None,
        verification_dispatcher: Optional[VerificationDispatcher] = None,
        diagnosis_controller: Optional[FailureDiagnosisController] = None,
        attempt_tracker: Optional[RepairAttemptTracker] = None,
        event_coordinator: Optional[AgentEventCoordinator] = None,
        config: Optional[RepairConfig] = None,
    ):
        self.config = config or RepairConfig()
        self.agent_loop = agent_loop or EngineeringAgentLoop()
        self.verifier = verification_dispatcher or VerificationDispatcher()
        self.diagnosis = diagnosis_controller or FailureDiagnosisController()
        self.limits = attempt_tracker or RepairAttemptTracker(config=self.config)
        self.events = event_coordinator or AgentEventCoordinator()

    def repair_task(
        self,
        task_context: TaskExecutionContext,
        initial_verification_result: VerificationResult,
        db: Optional[Session] = None,
        run_model: Optional[AgentRun] = None,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> RepairResult:
        """
        Executes the bounded diagnosis-repair loop for a failed task.
        """
        task_id = task_context.task_id
        current_verif_result = initial_verification_result
        all_changed_files: Set[str] = set()
        latest_diff: Optional[str] = None
        latest_diagnosis_id: Optional[str] = None

        logger.info(f"RepairController: Initiating repair sequence for task '{task_id}'")

        while True:
            # 1. Check for cancellation
            if (cancel_checker and cancel_checker()) or (run_model and getattr(run_model, "cancel_requested", False)):
                logger.info(f"RepairController: Repair cancelled for task '{task_id}'")
                self._emit(
                    db, run_model, AgentEventType.CANCELLED, f"Repair cancelled for task '{task_id}'", {"task_id": task_id}
                )
                return self._build_result(
                    task_id=task_id,
                    status=RepairStatus.CANCELLED,
                    passed=False,
                    diagnosis_id=latest_diagnosis_id,
                    changed_files=list(all_changed_files),
                    diff=latest_diff,
                    verification_result=current_verif_result,
                    stop_reason="Cancelled by user or system",
                    summary="Repair cancelled during execution.",
                )

            # 2. Step: Diagnosis
            attempt_num = self.limits.get_attempt_count(task_id) + 1

            self._emit(
                db,
                run_model,
                AgentEventType.DIAGNOSIS_STARTED,
                f"Starting diagnosis for task '{task_id}' (attempt #{attempt_num})",
                {"task_id": task_id, "attempt_number": attempt_num},
            )

            diag_ctx = self.diagnosis.diagnose(
                task_context=task_context,
                verification_result=current_verif_result,
                attempt_number=attempt_num,
            )
            latest_diagnosis_id = diag_ctx.diagnosis_id

            self._emit(
                db,
                run_model,
                AgentEventType.DIAGNOSIS_CONTEXT_ASSEMBLED,
                f"Diagnosis context assembled: {len(diag_ctx.defects)} defect(s), primary category: {diag_ctx.primary_category.value}",
                {
                    "task_id": task_id,
                    "diagnosis_id": diag_ctx.diagnosis_id,
                    "primary_category": diag_ctx.primary_category.value,
                    "defect_count": len(diag_ctx.defects),
                    "affected_files": diag_ctx.affected_files,
                },
            )

            # 3. Step: Check limits and start attempt
            is_allowed, attempt, rejection_reason = self.limits.start_attempt(
                task_id=task_id,
                diagnosis_id=diag_ctx.diagnosis_id,
                defect_ids=[d.defect_id for d in diag_ctx.defects],
            )

            if not is_allowed or attempt is None:
                self._emit(
                    db,
                    run_model,
                    AgentEventType.REPAIR_BLOCKED,
                    f"Repair blocked for task '{task_id}': {rejection_reason}",
                    {"task_id": task_id, "reason": rejection_reason},
                )
                return self._build_result(
                    task_id=task_id,
                    status=RepairStatus.BLOCKED,
                    passed=False,
                    diagnosis_id=latest_diagnosis_id,
                    changed_files=list(all_changed_files),
                    diff=latest_diff,
                    verification_result=current_verif_result,
                    stop_reason=rejection_reason,
                    summary=f"Task blocked during repair: {rejection_reason}",
                    db=db,
                    run_model=run_model,
                )

            # Check stagnation / repeated failure signatures
            is_sig_ok, sig_reason = self.limits.record_and_check_signature(
                task_id=task_id,
                diagnosis_context=diag_ctx,
                diff=latest_diff,
            )
            if not is_sig_ok:
                self._emit(
                    db,
                    run_model,
                    AgentEventType.REPAIR_BLOCKED,
                    f"Repair blocked on repeated signature for task '{task_id}': {sig_reason}",
                    {"task_id": task_id, "reason": sig_reason},
                )
                return self._build_result(
                    task_id=task_id,
                    status=RepairStatus.BLOCKED,
                    passed=False,
                    diagnosis_id=latest_diagnosis_id,
                    changed_files=list(all_changed_files),
                    diff=latest_diff,
                    verification_result=current_verif_result,
                    stop_reason=sig_reason,
                    summary=f"Task blocked due to repeated unresolving failure: {sig_reason}",
                    db=db,
                    run_model=run_model,
                )

            # 4. Step: Agent Investigation and Modification
            self._emit(
                db,
                run_model,
                AgentEventType.REPAIR_ATTEMPT_STARTED,
                f"Starting agent repair attempt #{attempt.attempt_number} for task '{task_id}'",
                {
                    "task_id": task_id,
                    "attempt_number": attempt.attempt_number,
                    "diagnosis_id": diag_ctx.diagnosis_id,
                },
            )

            # Build targeted repair task execution context
            repair_task_context = self._build_repair_execution_context(task_context, diag_ctx)
            loop_config = AgentLoopConfig(
                max_agent_turns=self.config.max_agent_iterations_per_attempt,
            )

            agent_exec_res: AgentExecutionResult = self.agent_loop.run(
                task_context=repair_task_context,
                config=loop_config,
                db=db,
                run_model=run_model,
                cancel_checker=cancel_checker,
            )

            if agent_exec_res.changed_files:
                all_changed_files.update(agent_exec_res.changed_files)
            if agent_exec_res.diff:
                latest_diff = agent_exec_res.diff

            self._emit(
                db,
                run_model,
                AgentEventType.REPAIR_ATTEMPT_COMPLETED,
                f"Repair attempt #{attempt.attempt_number} finished with status '{agent_exec_res.status}'",
                {
                    "task_id": task_id,
                    "attempt_number": attempt.attempt_number,
                    "status": agent_exec_res.status,
                    "changed_files": agent_exec_res.changed_files,
                },
            )

            # 5. Step: Mandatory Re-Verification via VerificationDispatcher (Phase 7)
            self._emit(
                db,
                run_model,
                AgentEventType.REPAIR_REVERIFY_STARTED,
                f"Starting re-verification for task '{task_id}' (attempt #{attempt.attempt_number})",
                {"task_id": task_id, "attempt_number": attempt.attempt_number},
            )

            task_exec_summary = (
                agent_exec_res.completion_signal.summary
                if agent_exec_res.completion_signal
                else f"Repair attempt #{attempt.attempt_number} completed."
            )
            repair_task_res = TaskExecutionResult(
                task_id=task_id,
                success=(agent_exec_res.status == "COMPLETED_FOR_VERIFICATION"),
                summary=task_exec_summary,
                changed_files=agent_exec_res.changed_files,
            )

            current_verif_result = self.verifier.verify(
                task_context=task_context,
                execution_result=repair_task_res,
                db=db,
                run_model=run_model,
            )

            # Record attempt outcome
            self.limits.record_attempt_completion(
                task_id=task_id,
                attempt=attempt,
                changed_files=agent_exec_res.changed_files,
                diff=agent_exec_res.diff,
                verification_result=current_verif_result,
                stop_reason=agent_exec_res.stop_reason.value if hasattr(agent_exec_res.stop_reason, "value") else str(agent_exec_res.stop_reason),
            )

            self._emit(
                db,
                run_model,
                AgentEventType.REPAIR_REVERIFY_COMPLETED,
                f"Re-verification verdict for task '{task_id}': {current_verif_result.status.value}",
                {
                    "task_id": task_id,
                    "attempt_number": attempt.attempt_number,
                    "status": current_verif_result.status.value,
                    "passed": current_verif_result.passed,
                },
            )

            # 6. Step: Evaluate Verdict
            if current_verif_result.passed:
                self._emit(
                    db,
                    run_model,
                    AgentEventType.REPAIR_PASSED,
                    f"Task '{task_id}' repaired and verified successfully in {attempt.attempt_number} attempt(s).",
                    {
                        "task_id": task_id,
                        "attempt_number": attempt.attempt_number,
                        "verification_id": current_verif_result.verification_id,
                    },
                )
                return self._build_result(
                    task_id=task_id,
                    status=RepairStatus.PASSED,
                    passed=True,
                    diagnosis_id=latest_diagnosis_id,
                    changed_files=list(all_changed_files),
                    diff=latest_diff,
                    verification_result=current_verif_result,
                    summary=f"Task '{task_id}' repaired and re-verified successfully on attempt #{attempt.attempt_number}.",
                    db=db,
                    run_model=run_model,
                )

            # If failed, continue to next diagnosis cycle
            self._emit(
                db,
                run_model,
                AgentEventType.REPAIR_FAILED,
                f"Repair attempt #{attempt.attempt_number} failed verification: {current_verif_result.summary}",
                {
                    "task_id": task_id,
                    "attempt_number": attempt.attempt_number,
                    "failure_summary": current_verif_result.summary,
                },
            )

    def _build_repair_execution_context(
        self,
        original_context: TaskExecutionContext,
        diag_ctx: DiagnosisContext,
    ) -> TaskExecutionContext:
        """
        Creates a specialized TaskExecutionContext containing targeted failure evidence.
        """
        orig_def = original_context.task_definition

        repair_title = f"Repair Defect: {orig_def.title if orig_def else original_context.task_id}"
        repair_desc = (
            f"Original Task: {orig_def.description if orig_def else ''}\n\n"
            f"=== VERIFICATION FAILURE DIAGNOSIS ===\n"
            f"Primary Defect Category: {diag_ctx.primary_category.value}\n"
            f"Attempt Number: {diag_ctx.repair_attempt_number}\n\n"
            f"Evidence & Detected Defects:\n{diag_ctx.known_evidence_summary}\n\n"
            f"Instructions:\n"
            f"1. Use read_file / get_symbol to inspect the implicated code.\n"
            f"2. Fix the specific defects while preserving existing interfaces and acceptance criteria.\n"
            f"3. Do not delete tests or weaken assertions."
        )

        repair_task_def = PlanTask(
            task_id=original_context.task_id,
            step_number=orig_def.step_number if orig_def else 1,
            title=repair_title,
            description=repair_desc,
            affected_files=diag_ctx.affected_files or (orig_def.affected_files if orig_def else []),
            affected_symbols=diag_ctx.affected_symbols or (orig_def.affected_symbols if orig_def else []),
            acceptance_criteria=diag_ctx.acceptance_criteria,
            verification_strategy=orig_def.verification_strategy if orig_def else "verify_static",
        )

        return TaskExecutionContext(
            agent_run_id=original_context.agent_run_id,
            plan_id=original_context.plan_id,
            task_id=original_context.task_id,
            repository_id=original_context.repository_id,
            worktree_path=original_context.worktree_path,
            task_definition=repair_task_def,
            repository_context_summary=original_context.repository_context_summary,
            execution_config=original_context.execution_config,
        )

    def _build_result(
        self,
        task_id: str,
        status: RepairStatus,
        passed: bool,
        diagnosis_id: Optional[str],
        changed_files: List[str],
        diff: Optional[str],
        verification_result: Optional[VerificationResult],
        summary: str,
        stop_reason: Optional[str] = None,
        db: Optional[Session] = None,
        run_model: Optional[AgentRun] = None,
    ) -> RepairResult:
        history = self.limits.get_attempts(task_id)
        result = RepairResult(
            task_id=task_id,
            status=status,
            passed=passed,
            diagnosis_id=diagnosis_id,
            attempts_used=len(history),
            max_attempts=self.config.max_repair_attempts,
            changed_files=changed_files,
            diff=diff,
            verification_result=verification_result,
            history=history,
            stop_reason=stop_reason,
            summary=summary,
        )

        # Persist into run_model metadata if present
        if db and run_model:
            try:
                meta = run_model.metadata_json or {}
                repairs = meta.setdefault("repair_results", {})
                repairs[task_id] = result.model_dump()
                run_model.metadata_json = meta
                db.add(run_model)
                db.commit()
            except Exception as ex:
                logger.warning(f"RepairController: Could not persist repair result in metadata_json: {ex}")

        return result

    def _emit(
        self,
        db: Optional[Session],
        run_model: Optional[AgentRun],
        event_type: Any,
        message: str,
        payload: Dict[str, Any],
    ) -> None:
        if db is not None and run_model is not None and self.events is not None:
            try:
                self.events.emit_event(
                    db=db,
                    agent_run=run_model,
                    event_type=event_type,
                    message=message,
                    payload=payload,
                )
            except Exception as ex:
                logger.warning(f"RepairController: Failed to emit event {event_type}: {ex}")
