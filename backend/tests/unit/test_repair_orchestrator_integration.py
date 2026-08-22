"""
Integration Tests for TaskOrchestrator + EngineeringAgentLoop + VerificationDispatcher + RepairController.
"""
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List

from backend.agent.loop import (
    AgentExecutionResult,
    AgentLoopConfig,
    EngineeringAgentLoop,
    ModelAdapter,
)
from backend.agent.planning.contracts import Plan, PlanStatus, PlanTask, PlanTaskStatus
from backend.agent.repair.contracts import RepairConfig, RepairStatus
from backend.agent.repair.repair import RepairController
from backend.agent.tasks import (
    EngineeringAgentTaskExecutor,
    TaskExecutionContext,
    TaskOrchestrator,
)
from backend.agent.tools import create_default_tool_registry
from backend.agent.verification.dispatcher import VerificationDispatcher
from backend.verification.judge import Judge
from backend.verification.schemas import Defect as LegacyDefect, VerificationResult as LegacyVerificationResult
from backend.verification.static_verifier import StaticVerifier


class MockScriptAdapter(ModelAdapter):
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
            "summary": "Completed default repair",
            "acceptance_criteria_status": [{"criterion": "c1", "status": "satisfied", "evidence": "e1"}],
            "verification_requested": True,
        })


class MockSequenceStaticVerifier(StaticVerifier):
    def __init__(self, sequence: List[bool]):
        self.sequence = list(sequence)
        self.idx = 0

    def verify(self, worktree_path, modified_files=None, git_diff=None):
        passed = self.sequence[min(self.idx, len(self.sequence) - 1)]
        self.idx += 1
        return LegacyVerificationResult(
            vector_name="static",
            status="PASS" if passed else "FAIL",
            passed=passed,
            execution_state="PASS" if passed else "FAIL",
            defects=[] if passed else [
                LegacyDefect(
                    category="STATIC_IMPORT_MISSING",
                    file_path="item_service.py",
                    description="Syntax defect",
                )
            ],
            evidence_manifest=[{"type": "ast_verified"}] if passed else [],
            details={"output": "Check done"},
            execution_time_ms=10.0,
        )


def test_task_orchestrator_repair_flow_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        subprocess.run(["git", "init"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=wt_path, capture_output=True, check=True)

        tool_registry = create_default_tool_registry()

        # Step 1: Create plan with a task
        task1 = PlanTask(
            task_id="task-orch-r1",
            step_number=1,
            title="Create and repair service",
            description="Create service with get_item",
            affected_files=["item_service.py"],
            acceptance_criteria=["item_service.py exists"],
            verification_strategy="verify_static",
        )
        plan = Plan(
            plan_id="plan-repair-1",
            agent_run_id="run-rep-1",
            repository_id="repo-rep-1",
            requirement="Create and repair service",
            version=1,
            tasks=[task1],
            status=PlanStatus.APPROVED,
        )

        # Initial implementation creates file with a flaw
        scripted_responses = [
            json.dumps({
                "action": "tool_call",
                "tool_name": "create_file",
                "arguments": {
                    "path": "item_service.py",
                    "content": "def get_item():\n    return 1\n",
                },
            }),
            json.dumps({
                "action": "complete",
                "summary": "Created item_service.py",
                "acceptance_criteria_status": [{"criterion": "item_service.py exists", "status": "satisfied", "evidence": "Created"}],
                "verification_requested": True,
            }),
        ]
        adapter = MockScriptAdapter(scripted_responses)
        loop = EngineeringAgentLoop(tool_registry=tool_registry, model_adapter=adapter)
        executor = EngineeringAgentTaskExecutor(agent_loop=loop)

        # Verifier: Initial execution fails, repair passes
        verifier = VerificationDispatcher(
            static_verifier=MockSequenceStaticVerifier([False, True]),
            judge=Judge(),
        )

        repair_controller = RepairController(
            agent_loop=loop,
            verification_dispatcher=verifier,
            config=RepairConfig(max_repair_attempts=2),
        )

        orchestrator = TaskOrchestrator(executor=executor, verifier=verifier)
        orchestrator.evaluate_dependencies(plan)

        # Execute initial task
        next_task = orchestrator.select_next_task(plan)
        assert next_task.task_id == "task-orch-r1"

        exec_ctx = TaskExecutionContext(
            agent_run_id="run-rep-1",
            plan_id="plan-repair-1",
            task_id="task-orch-r1",
            repository_id="repo-rep-1",
            worktree_path=str(wt_path),
            task_definition=next_task,
        )

        orchestrator.start_task(plan, "task-orch-r1")
        exec_res = orchestrator.executor.execute(exec_ctx)
        orchestrator.complete_task_execution(plan, "task-orch-r1", exec_res)

        # Initial verification fails
        init_verif = verifier.verify(exec_ctx, exec_res)
        assert init_verif.passed is False
        orchestrator.record_verification_result(plan, "task-orch-r1", passed=False, error=init_verif.summary)

        assert plan.tasks[0].status == PlanTaskStatus.FAILED

        # Invoke Repair Controller
        repair_res = repair_controller.repair_task(
            task_context=exec_ctx,
            initial_verification_result=init_verif,
        )
        assert repair_res.passed is True
        assert repair_res.status == RepairStatus.PASSED

        # Record repair result in orchestrator
        orchestrator.record_repair_result(plan, "task-orch-r1", repair_res)

        assert plan.tasks[0].status == PlanTaskStatus.PASSED
        assert orchestrator.all_tasks_passed(plan) is True
