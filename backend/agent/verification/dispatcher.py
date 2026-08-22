"""
Verification Dispatcher for Phase 7 Verification-Driven Execution.

Orchestrates multi-vector verification by reusing existing verifiers:
  - StaticVerifier
  - DynamicVerifier
  - ContractVerifier
  - Judge
Enforces sequential check execution, timeouts, cancellation, defect extraction,
evidence aggregation, audit event streaming, and database persistence.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult
from backend.agent.tasks.verification import VerificationDispatcher as BaseVerificationDispatcher
from backend.agent.verification.contracts import (
    DefectCategory,
    VerificationCheck,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
    VerificationStrategy,
    VerificationType,
)
from backend.agent.verification.evidence import VerificationEvidenceCollector
from backend.agent.verification.result import VerificationResultAggregator
from backend.agent.verification.strategy import VerificationStrategyResolver
from backend.models.implementation import AgentEvent, AgentEventType, AgentRun
from backend.services.git_manager import GitManager
from backend.verification.contract_verifier import ContractVerifier
from backend.verification.dynamic_verifier import DynamicVerifier
from backend.verification.judge import Judge
from backend.verification.schemas import (
    Defect,
    DefectSeverity,
    ExecutionState,
    VerificationReport,
    VerificationResult as LegacyVerificationResult,
)
from backend.verification.static_verifier import StaticVerifier

logger = logging.getLogger(__name__)


class VerificationDispatcher(BaseVerificationDispatcher):
    """
    Authoritative verification dispatcher connecting TaskOrchestrator and
    EngineeringAgentLoop to GitOnBoard's verification mesh.
    """

    def __init__(
        self,
        static_verifier: Optional[StaticVerifier] = None,
        dynamic_verifier: Optional[DynamicVerifier] = None,
        contract_verifier: Optional[ContractVerifier] = None,
        judge: Optional[Judge] = None,
        strategy_resolver: Optional[VerificationStrategyResolver] = None,
        evidence_collector: Optional[VerificationEvidenceCollector] = None,
        result_aggregator: Optional[VerificationResultAggregator] = None,
        event_coordinator: Optional[AgentEventCoordinator] = None,
    ):
        self.static_verifier = static_verifier or StaticVerifier()
        self.dynamic_verifier = dynamic_verifier or DynamicVerifier()
        self.contract_verifier = contract_verifier or ContractVerifier()
        self.judge = judge or Judge()
        self.strategy_resolver = strategy_resolver or VerificationStrategyResolver()
        self.evidence_collector = evidence_collector or VerificationEvidenceCollector()
        self.result_aggregator = result_aggregator or VerificationResultAggregator()
        self.events = event_coordinator or AgentEventCoordinator()

    def verify_task(
        self,
        context: TaskExecutionContext,
        execution_result: TaskExecutionResult,
        db: Optional[Session] = None,
        run_model: Optional[AgentRun] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Implements BaseVerificationDispatcher interface for TaskOrchestrator.
        Executes multi-vector verification and returns (passed, failure_reason).
        """
        result = self.verify(
            task_context=context,
            execution_result=execution_result,
            db=db,
            run_model=run_model,
        )
        return result.passed, (None if result.passed else result.summary)

    def verify(
        self,
        task_context: TaskExecutionContext,
        execution_result: TaskExecutionResult,
        strategy: Optional[VerificationStrategy] = None,
        db: Optional[Session] = None,
        run_model: Optional[AgentRun] = None,
        is_final: bool = False,
    ) -> VerificationResult:
        """
        Executes the full verification sequence for a task execution.
        """
        start_time = time.perf_counter()
        task_id = task_context.task_id
        run_id = task_context.agent_run_id

        logger.info(f"VerificationDispatcher: Starting verification for task '{task_id}' (run '{run_id}')")

        self._emit(
            event_type=AgentEventType.VERIFICATION_STARTED,
            message=f"Starting verification for task '{task_id}'",
            payload={"task_id": task_id, "is_final": is_final},
            db=db,
            run_model=run_model,
        )

        # 1. Resolve Verification Strategy
        if not strategy:
            strategy = self.strategy_resolver.resolve(
                task_context=task_context,
                is_final=is_final,
            )

        # 2. Extract Worktree Diff and Target Files
        wt_path = Path(task_context.worktree_path).resolve() if task_context.worktree_path else Path.cwd()
        modified_files, git_diff = self._get_modified_and_diff(task_context)
        if not modified_files and task_context.task_definition:
            modified_files = list(task_context.task_definition.affected_files)

        # Pre-execution validation: if Phase 6 reported failure, record defect immediately
        if not execution_result.success:
            err_msg = execution_result.error or "Phase 6 agent execution failed prior to verification"
            err_check = VerificationCheck(
                type=VerificationType.STATIC,
                name="Pre-Verification Execution Sanity",
                required=True,
            )
            err_evidence = self.evidence_collector.create_error_evidence(
                verification_id=strategy.task_id,
                check=err_check,
                error_message=err_msg,
                status=VerificationStatus.FAILED,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            res = self.result_aggregator.aggregate(
                task_id=task_id,
                checks=[err_check],
                evidence_list=[err_evidence],
                duration_ms=duration_ms,
            )
            self._persist_and_emit_completion(res, db=db, run_model=run_model)
            return res

        # 3. Sequential Execution of Verification Checks
        evidence_list: List[VerificationEvidence] = []
        static_legacy_res: Optional[LegacyVerificationResult] = None
        dynamic_legacy_res: Optional[LegacyVerificationResult] = None
        contract_legacy_res: Optional[LegacyVerificationResult] = None

        aborted_early = False

        for check in strategy.checks:
            # Check cancellation between checks
            if run_model and getattr(run_model, "cancellation_reason", None):
                duration_ms = (time.perf_counter() - start_time) * 1000
                res = self.result_aggregator.aggregate(
                    task_id=task_id,
                    checks=strategy.checks,
                    evidence_list=evidence_list,
                    duration_ms=duration_ms,
                    cancellation_reason=run_model.cancellation_reason,
                )
                self._persist_and_emit_completion(res, db=db, run_model=run_model)
                return res

            self._emit(
                event_type=AgentEventType.VERIFICATION_CHECK_STARTED,
                message=f"Starting verification check: '{check.name}' ({check.type.value})",
                payload={"task_id": task_id, "check_id": check.check_id, "type": check.type.value},
                db=db,
                run_model=run_model,
            )

            check_start = time.perf_counter()
            try:
                if check.type == VerificationType.STATIC:
                    static_legacy_res = self.static_verifier.verify(
                        worktree_path=wt_path,
                        modified_files=modified_files,
                        git_diff=git_diff,
                    )
                    ev = self.evidence_collector.build_evidence_from_verifier_result(
                        verification_id=strategy.task_id,
                        check=check,
                        verifier_result=static_legacy_res,
                        duration_ms=(time.perf_counter() - check_start) * 1000,
                    )

                elif check.type == VerificationType.DYNAMIC:
                    dynamic_legacy_res = self.dynamic_verifier.verify(
                        worktree_path=wt_path,
                        timeout_sec=int(check.timeout),
                    )
                    ev = self.evidence_collector.build_evidence_from_verifier_result(
                        verification_id=strategy.task_id,
                        check=check,
                        verifier_result=dynamic_legacy_res,
                        duration_ms=(time.perf_counter() - check_start) * 1000,
                    )

                elif check.type == VerificationType.CONTRACT:
                    contract_data = self._build_contract_payload(task_context, check)
                    contract_legacy_res = self.contract_verifier.verify(
                        contract=contract_data,
                        modified_files=modified_files,
                        git_diff=git_diff,
                    )
                    ev = self.evidence_collector.build_evidence_from_verifier_result(
                        verification_id=strategy.task_id,
                        check=check,
                        verifier_result=contract_legacy_res,
                        duration_ms=(time.perf_counter() - check_start) * 1000,
                    )

                else:
                    ev = self.evidence_collector.create_error_evidence(
                        verification_id=strategy.task_id,
                        check=check,
                        error_message=f"Unknown verification check type '{check.type}'",
                    )

            except Exception as ex:
                logger.exception(f"VerificationDispatcher: Exception during check '{check.name}': {ex}")
                ev = self.evidence_collector.create_error_evidence(
                    verification_id=strategy.task_id,
                    check=check,
                    error_message=str(ex),
                    status=VerificationStatus.ERROR,
                    duration_ms=(time.perf_counter() - check_start) * 1000,
                )

            evidence_list.append(ev)

            # Emit per-check completion or failure
            if ev.status == VerificationStatus.PASSED:
                self._emit(
                    event_type=AgentEventType.VERIFICATION_CHECK_COMPLETED,
                    message=f"Verification check '{check.name}' PASSED ({ev.duration_ms:.1f}ms)",
                    payload={"task_id": task_id, "check_id": check.check_id, "status": "PASSED"},
                    db=db,
                    run_model=run_model,
                )
            else:
                self._emit(
                    event_type=AgentEventType.VERIFICATION_CHECK_FAILED,
                    message=f"Verification check '{check.name}' FAILED: {len(ev.defects)} defect(s)",
                    payload={"task_id": task_id, "check_id": check.check_id, "status": ev.status.value},
                    db=db,
                    run_model=run_model,
                )
                for d in ev.defects:
                    self._emit(
                        event_type=AgentEventType.VERIFICATION_DEFECT_FOUND,
                        message=f"Defect found in '{check.name}': {d.message}",
                        payload={"task_id": task_id, "defect": d.model_dump()},
                        db=db,
                        run_model=run_model,
                    )

                # Fail-fast: If a required check fails (e.g. static check), stop before running costly dynamic tests
                if check.required:
                    logger.warning(
                        f"VerificationDispatcher: Required check '{check.name}' failed. Aborting subsequent checks."
                    )
                    aborted_early = True
                    break

        # 4. Invoke Judge for Multi-Vector Synthesis
        judge_report: Optional[VerificationReport] = None
        if not aborted_early or static_legacy_res or dynamic_legacy_res or contract_legacy_res:
            self._emit(
                event_type=AgentEventType.VERIFICATION_JUDGE_STARTED,
                message="Synthesizing multi-vector verification report via Judge",
                payload={"task_id": task_id},
                db=db,
                run_model=run_model,
            )
            # Ensure all vectors have a result object for Judge
            s_res = static_legacy_res or LegacyVerificationResult(
                vector_name="static", status="PASS", passed=True, execution_state=ExecutionState.PASS.value
            )
            d_res = dynamic_legacy_res or LegacyVerificationResult(
                vector_name="dynamic", status="PASS", passed=True, execution_state=ExecutionState.PASS.value
            )
            c_res = contract_legacy_res or LegacyVerificationResult(
                vector_name="contract", status="PASS", passed=True, execution_state=ExecutionState.PASS.value
            )
            judge_report = self.judge.aggregate(
                run_id=run_id,
                static_result=s_res,
                dynamic_result=d_res,
                contract_result=c_res,
            )
            self._emit(
                event_type=AgentEventType.VERIFICATION_JUDGE_COMPLETED,
                message=f"Judge aggregation finished: {judge_report.status}",
                payload={"task_id": task_id, "verdict": judge_report.status, "passed": judge_report.passed},
                db=db,
                run_model=run_model,
            )

        # 5. Aggregate final result
        duration_ms = (time.perf_counter() - start_time) * 1000
        final_result = self.result_aggregator.aggregate(
            task_id=task_id,
            checks=strategy.checks,
            evidence_list=evidence_list,
            judge_report=judge_report,
            duration_ms=duration_ms,
        )

        self._persist_and_emit_completion(final_result, db=db, run_model=run_model)
        return final_result

    def _persist_and_emit_completion(
        self,
        result: VerificationResult,
        db: Optional[Session],
        run_model: Optional[AgentRun],
    ) -> None:
        """
        Persists verification evidence into AgentRun.metadata_json and emits final completion event.
        """
        # Persist structured outcome into AgentRun metadata
        if run_model:
            meta = dict(run_model.metadata_json or {})
            verif_history = dict(meta.get("verification_results") or {})
            verif_history[result.task_id] = result.model_dump(mode="json")
            meta["verification_results"] = verif_history
            meta["last_verification_result"] = result.model_dump(mode="json")
            run_model.metadata_json = meta
            if db:
                db.add(run_model)
                db.commit()

        # Emit authoritative terminal event
        if result.passed:
            self._emit(
                event_type=AgentEventType.VERIFICATION_PASSED,
                message=result.summary,
                payload={"task_id": result.task_id, "verification_id": result.verification_id},
                db=db,
                run_model=run_model,
            )
        else:
            self._emit(
                event_type=AgentEventType.VERIFICATION_FAILED,
                message=result.summary,
                payload={
                    "task_id": result.task_id,
                    "verification_id": result.verification_id,
                    "status": result.status.value,
                    "defects_count": len(result.defects),
                },
                db=db,
                run_model=run_model,
            )

    def _emit(
        self,
        event_type: AgentEventType,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None,
        run_model: Optional[AgentRun] = None,
    ) -> None:
        """Safe helper to emit event if db and run_model are present."""
        if db and run_model and self.events:
            try:
                self.events.emit_event(
                    db=db,
                    agent_run=run_model,
                    event_type=event_type,
                    message=message,
                    payload=payload or {},
                )
            except Exception as err:
                logger.debug(f"VerificationDispatcher: Failed to emit event {event_type.value}: {err}")

    def _get_modified_and_diff(self, context: TaskExecutionContext) -> tuple[List[str], str]:
        if not context.worktree_path or not Path(context.worktree_path).exists():
            return [], ""
        wt = Path(context.worktree_path)
        if not (wt / ".git").exists():
            return [], ""
        try:
            gm = GitManager(base_worktree_dir=wt.parent)
            modified = gm.list_modified_files(worktree_path=context.worktree_path)
            diff = gm.get_diff(worktree_path=context.worktree_path)
            return modified, diff
        except Exception as ex:
            logger.warning(f"VerificationDispatcher: Could not extract git diff: {ex}")
            return [], ""

    def _build_contract_payload(self, context: TaskExecutionContext, check: VerificationCheck) -> Dict[str, Any]:
        task = context.task_definition
        criteria = (
            check.metadata.get("criteria")
            or (task.acceptance_criteria if task else [])
            or ["Implementation satisfies task acceptance criteria"]
        )
        files = (
            check.metadata.get("files")
            or (task.affected_files if task else [])
            or []
        )
        return {
            "acceptance_criteria": criteria,
            "affected_components": [{"file": f, "symbol": None} for f in files],
            "invariants": [],
        }
