"""
Unit Tests for RepairController: Multi-Turn Repair Cycles and Invariant Checks.
"""
import json
import tempfile
from pathlib import Path
from typing import List

from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.loop import (
    AgentExecutionResult,
    AgentLoopConfig,
    EngineeringAgentLoop,
    ModelAdapter,
    StopReason,
)
from backend.agent.planning.contracts import PlanTask
from backend.agent.repair.contracts import (
    FailureCategory,
    RepairConfig,
    RepairResult,
    RepairStatus,
)
from backend.agent.repair.diagnosis import FailureDiagnosisController
from backend.agent.repair.limits import RepairAttemptTracker
from backend.agent.repair.repair import RepairController
from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult
from backend.agent.tools import create_default_tool_registry
from backend.agent.verification.contracts import (
    DefectSeverity,
    VerificationDefect,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
)
from backend.agent.verification.dispatcher import VerificationDispatcher
from backend.verification.judge import Judge
from backend.verification.schemas import Defect as LegacyDefect, VerificationResult as LegacyVerificationResult
from backend.verification.static_verifier import StaticVerifier


class MockScriptModelAdapter(ModelAdapter):
    def __init__(self, responses: List[str]):
        super().__init__()
        self.responses = list(responses)
        self.call_idx = 0

    async def call_model(self, messages) -> str:
        if self.call_idx < len(self.responses):
            resp = self.responses[self.call_idx]
            self.call_idx += 1
            return resp
        return json.dumps({
            "action": "complete",
            "summary": "Completed fallback repair",
            "acceptance_criteria_status": [
                {"criterion": "Repaired bug", "status": "satisfied", "evidence": "Fixed"}
            ],
            "verification_requested": True,
        })


class MockStepStaticVerifier(StaticVerifier):
    def __init__(self, outcomes: List[bool]):
        self.outcomes = list(outcomes)
        self.call_idx = 0

    def verify(self, worktree_path, modified_files=None, git_diff=None):
        passed = self.outcomes[min(self.call_idx, len(self.outcomes) - 1)]
        self.call_idx += 1
        return LegacyVerificationResult(
            vector_name="static",
            status="PASS" if passed else "FAIL",
            passed=passed,
            execution_state="PASS" if passed else "FAIL",
            defects=[] if passed else [
                LegacyDefect(
                    category="STATIC_IMPORT_MISSING",
                    file_path="service.py",
                    description="Syntax issue still present",
                )
            ],
            evidence_manifest=[{"type": "ast_verified"}] if passed else [],
            details={"output": "Check complete"},
            execution_time_ms=10.0,
        )


def test_repair_controller_successful_single_attempt():
    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        tool_registry = create_default_tool_registry()

        # Step 1: Script model to fix the file
        scripted_responses = [
            json.dumps({
                "action": "tool_call",
                "tool_name": "create_file",
                "arguments": {
                    "path": "service.py",
                    "content": "def fix_bug():\n    return True\n",
                },
            }),
            json.dumps({
                "action": "complete",
                "summary": "Fixed syntax error in service.py",
                "acceptance_criteria_status": [
                    {"criterion": "service.py valid", "status": "satisfied", "evidence": "Created"}
                ],
                "verification_requested": True,
            }),
        ]
        adapter = MockScriptModelAdapter(scripted_responses)
        loop = EngineeringAgentLoop(
            tool_registry=tool_registry,
            model_adapter=adapter,
            config=AgentLoopConfig(max_agent_turns=5),
        )

        verifier = VerificationDispatcher(
            static_verifier=MockStepStaticVerifier([True]),
            judge=Judge(),
        )

        controller = RepairController(
            agent_loop=loop,
            verification_dispatcher=verifier,
            config=RepairConfig(max_repair_attempts=3),
        )

        task_def = PlanTask(
            task_id="task-r1",
            step_number=1,
            title="Fix Service",
            description="Fix syntax error",
            affected_files=["service.py"],
            acceptance_criteria=["service.py valid"],
            verification_strategy="verify_static",
        )
        task_ctx = TaskExecutionContext(
            agent_run_id="run-1",
            plan_id="plan-1",
            task_id="task-r1",
            repository_id="repo-1",
            worktree_path=str(wt_path),
            task_definition=task_def,
        )

        initial_failure = VerificationResult(
            verification_id="v-init",
            task_id="task-r1",
            status=VerificationStatus.FAILED,
            passed=False,
            failed_checks=["Static AST & Import Integrity"],
            defects=[
                VerificationDefect(
                    type="SYNTAX_ERROR",
                    severity=DefectSeverity.HIGH,
                    message="invalid syntax in service.py line 2",
                    file="service.py",
                )
            ],
            summary="Initial static verification failed",
        )

        repair_res = controller.repair_task(
            task_context=task_ctx,
            initial_verification_result=initial_failure,
        )

        assert repair_res.passed is True
        assert repair_res.status == RepairStatus.PASSED
        assert repair_res.attempts_used == 1
        assert "service.py" in repair_res.changed_files
        assert (wt_path / "service.py").exists()


def test_repair_controller_multi_attempt_then_pass():
    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        tool_registry = create_default_tool_registry()

        # Model takes 2 repair cycles: attempt 1 modifies, attempt 2 finishes
        scripted_responses = [
            # Cycle 1: creates attempt 1
            json.dumps({
                "action": "tool_call",
                "tool_name": "create_file",
                "arguments": {"path": "helper.py", "content": "# attempt 1\n"},
            }),
            json.dumps({
                "action": "complete",
                "summary": "First repair attempt",
                "acceptance_criteria_status": [{"criterion": "c1", "status": "satisfied", "evidence": "e1"}],
                "verification_requested": True,
            }),
            # Cycle 2: creates attempt 2
            json.dumps({
                "action": "tool_call",
                "tool_name": "create_file",
                "arguments": {"path": "helper.py", "content": "def helper():\n    return 42\n"},
            }),
            json.dumps({
                "action": "complete",
                "summary": "Second repair attempt",
                "acceptance_criteria_status": [{"criterion": "c1", "status": "satisfied", "evidence": "e2"}],
                "verification_requested": True,
            }),
        ]
        adapter = MockScriptModelAdapter(scripted_responses)
        loop = EngineeringAgentLoop(
            tool_registry=tool_registry,
            model_adapter=adapter,
            config=AgentLoopConfig(max_agent_turns=5),
        )

        # Verifier: First call fails, Second call passes
        verifier = VerificationDispatcher(
            static_verifier=MockStepStaticVerifier([False, True]),
            judge=Judge(),
        )

        controller = RepairController(
            agent_loop=loop,
            verification_dispatcher=verifier,
            config=RepairConfig(max_repair_attempts=3),
        )

        task_def = PlanTask(
            task_id="task-r2",
            step_number=1,
            title="Multi-Attempt Task",
            description="Fix helper.py",
            affected_files=["helper.py"],
            verification_strategy="verify_static",
        )
        task_ctx = TaskExecutionContext(
            agent_run_id="run-2",
            plan_id="plan-2",
            task_id="task-r2",
            repository_id="repo-2",
            worktree_path=str(wt_path),
            task_definition=task_def,
        )

        initial_failure = VerificationResult(
            verification_id="v-init-2",
            task_id="task-r2",
            status=VerificationStatus.FAILED,
            passed=False,
            summary="Initial failure",
        )

        repair_res = controller.repair_task(
            task_context=task_ctx,
            initial_verification_result=initial_failure,
        )

        assert repair_res.passed is True
        assert repair_res.status == RepairStatus.PASSED
        assert repair_res.attempts_used == 2
        assert len(repair_res.history) == 2


def test_repair_controller_exhausts_attempts_transitions_to_blocked():
    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        tool_registry = create_default_tool_registry()

        scripted_responses = [
            json.dumps({
                "action": "complete",
                "summary": "Claim fixed",
                "acceptance_criteria_status": [{"criterion": "c", "status": "satisfied", "evidence": "e"}],
                "verification_requested": True,
            }),
        ]
        adapter = MockScriptModelAdapter(scripted_responses)
        loop = EngineeringAgentLoop(
            tool_registry=tool_registry,
            model_adapter=adapter,
            config=AgentLoopConfig(max_agent_turns=5),
        )

        # Verifier always fails
        verifier = VerificationDispatcher(
            static_verifier=MockStepStaticVerifier([False, False, False]),
            judge=Judge(),
        )

        controller = RepairController(
            agent_loop=loop,
            verification_dispatcher=verifier,
            config=RepairConfig(max_repair_attempts=2),
        )

        task_def = PlanTask(
            task_id="task-unfixable",
            step_number=1,
            title="Unfixable Defect",
            description="Fails repeatedly",
            affected_files=["bad.py"],
            verification_strategy="verify_static",
        )
        task_ctx = TaskExecutionContext(
            agent_run_id="run-3",
            plan_id="plan-3",
            task_id="task-unfixable",
            repository_id="repo-3",
            worktree_path=str(wt_path),
            task_definition=task_def,
        )

        initial_failure = VerificationResult(
            verification_id="v-init-3",
            task_id="task-unfixable",
            status=VerificationStatus.FAILED,
            passed=False,
            summary="Unfixable failure",
        )

        repair_res = controller.repair_task(
            task_context=task_ctx,
            initial_verification_result=initial_failure,
        )

        assert repair_res.passed is False
        assert repair_res.status == RepairStatus.BLOCKED
        assert "Maximum repair attempts (2) exhausted" in (repair_res.stop_reason or "")
