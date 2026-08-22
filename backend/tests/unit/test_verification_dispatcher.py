"""
Unit tests for VerificationDispatcher in Phase 7.
"""
from pathlib import Path
import tempfile
import pytest

from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.planning.contracts import PlanTask
from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult
from backend.agent.verification.contracts import (
    VerificationResult,
    VerificationStatus,
)
from backend.agent.verification.dispatcher import VerificationDispatcher
from backend.models.implementation import AgentRun, AgentState
from backend.verification.contract_verifier import ContractVerifier
from backend.verification.dynamic_verifier import DynamicVerifier
from backend.verification.judge import Judge
from backend.verification.schemas import (
    Defect as LegacyDefect,
    ExecutionState,
    VerificationReport,
    VerificationResult as LegacyVerificationResult,
)
from backend.verification.static_verifier import StaticVerifier


class MockStaticVerifier(StaticVerifier):
    def __init__(self, passed: bool = True, defects=None):
        self._passed = passed
        self._defects = defects or []

    def verify(self, worktree_path, modified_files=None, git_diff=None):
        return LegacyVerificationResult(
            vector_name="static",
            status="PASS" if self._passed else "FAIL",
            passed=self._passed,
            execution_state="PASS" if self._passed else "FAIL",
            defects=self._defects,
            evidence_manifest=[{"type": "ast_verified", "files": modified_files or []}],
            details={"output": "Static check complete"},
            execution_time_ms=10.0,
        )


class MockDynamicVerifier(DynamicVerifier):
    def __init__(self, passed: bool = True, defects=None):
        self._passed = passed
        self._defects = defects or []

    def verify(self, worktree_path, timeout_sec=60):
        return LegacyVerificationResult(
            vector_name="dynamic",
            status="PASS" if self._passed else "FAIL",
            passed=self._passed,
            execution_state="PASS" if self._passed else "FAIL",
            defects=self._defects,
            evidence_manifest=[{"type": "test_run", "exit_code": 0 if self._passed else 1}],
            details={"output": "Dynamic check complete", "exit_code": 0 if self._passed else 1},
            execution_time_ms=25.0,
        )


class MockContractVerifier(ContractVerifier):
    def __init__(self, passed: bool = True, defects=None):
        self._passed = passed
        self._defects = defects or []

    def verify(self, contract, modified_files=None, git_diff=None):
        return LegacyVerificationResult(
            vector_name="contract",
            status="PASS" if self._passed else "FAIL",
            passed=self._passed,
            execution_state="PASS" if self._passed else "FAIL",
            defects=self._defects,
            evidence_manifest=[{"type": "contract_verified", "criteria_count": 1}],
            details={"output": "Contract check complete"},
            execution_time_ms=15.0,
        )


def test_dispatcher_successful_full_verification():
    with tempfile.TemporaryDirectory() as tmpdir:
        dispatcher = VerificationDispatcher(
            static_verifier=MockStaticVerifier(passed=True),
            dynamic_verifier=MockDynamicVerifier(passed=True),
            contract_verifier=MockContractVerifier(passed=True),
            judge=Judge(),
            event_coordinator=AgentEventCoordinator(),
        )

        task_def = PlanTask(
            task_id="task-1",
            step_number=1,
            title="Implement User API",
            description="Add user endpoint",
            affected_files=["routes/users.py"],
            verification_strategy="verify_dynamic",
        )
        task_ctx = TaskExecutionContext(
            agent_run_id="run-1",
            plan_id="plan-1",
            task_id="task-1",
            repository_id="repo-1",
            worktree_path=tmpdir,
            task_definition=task_def,
        )
        exec_res = TaskExecutionResult(
            task_id="task-1",
            success=True,
            summary="Implemented user API",
        )

        res = dispatcher.verify(task_context=task_ctx, execution_result=exec_res)
        assert res.passed is True
        assert res.status == VerificationStatus.PASSED
        assert len(res.evidence) >= 2
        assert len(res.defects) == 0


def test_dispatcher_static_failure_aborts_dynamic_tests():
    with tempfile.TemporaryDirectory() as tmpdir:
        static_defect = LegacyDefect(
            category="STATIC_IMPORT_MISSING",
            file_path="main.py",
            description="Missing import 'utils'",
        )
        dispatcher = VerificationDispatcher(
            static_verifier=MockStaticVerifier(passed=False, defects=[static_defect]),
            dynamic_verifier=MockDynamicVerifier(passed=True),
            judge=Judge(),
        )

        task_def = PlanTask(
            task_id="task-2",
            step_number=1,
            title="Syntax Broken Task",
            description="Fix utils",
            affected_files=["main.py"],
            verification_strategy="verify_dynamic",
        )
        task_ctx = TaskExecutionContext(
            agent_run_id="run-2",
            plan_id="plan-2",
            task_id="task-2",
            repository_id="repo-2",
            worktree_path=tmpdir,
            task_definition=task_def,
        )
        exec_res = TaskExecutionResult(task_id="task-2", success=True, summary="Task 2 execution completed")

        res = dispatcher.verify(task_context=task_ctx, execution_result=exec_res)
        assert res.passed is False
        assert res.status == VerificationStatus.FAILED
        assert len(res.defects) == 1
        assert res.defects[0].type == "STATIC_IMPORT_MISSING"


def test_dispatcher_execution_failure_fails_pre_verification():
    with tempfile.TemporaryDirectory() as tmpdir:
        dispatcher = VerificationDispatcher()
        task_def = PlanTask(
            task_id="task-3",
            step_number=1,
            title="Failed Execution Task",
            description="Test",
            verification_strategy="verify_static",
        )
        task_ctx = TaskExecutionContext(
            agent_run_id="run-3",
            plan_id="plan-3",
            task_id="task-3",
            repository_id="repo-3",
            worktree_path=tmpdir,
            task_definition=task_def,
        )
        exec_res = TaskExecutionResult(
            task_id="task-3",
            success=False,
            summary="Execution failed",
            error="Agent exceeded max turns",
        )

        res = dispatcher.verify(task_context=task_ctx, execution_result=exec_res)
        assert res.passed is False
        assert res.status == VerificationStatus.FAILED
        assert any("Agent exceeded max turns" in d.message for d in res.defects)


def test_dispatcher_cancellation_preserves_cancelled_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        dispatcher = VerificationDispatcher()
        task_def = PlanTask(
            task_id="task-4",
            step_number=1,
            title="Cancelled Task",
            description="Test",
            verification_strategy="verify_static",
        )
        task_ctx = TaskExecutionContext(
            agent_run_id="run-4",
            plan_id="plan-4",
            task_id="task-4",
            repository_id="repo-4",
            worktree_path=tmpdir,
            task_definition=task_def,
        )
        exec_res = TaskExecutionResult(task_id="task-4", success=True, summary="Task 4 execution completed")

        run_model = AgentRun(
            id="run-4",
            task_id="task-4",
            current_state=AgentState.CANCELLED,
            cancellation_reason="User pressed stop button",
        )

        res = dispatcher.verify(
            task_context=task_ctx, execution_result=exec_res, run_model=run_model
        )
        assert res.passed is False
        assert res.status == VerificationStatus.CANCELLED
        assert "User pressed stop button" in res.summary
