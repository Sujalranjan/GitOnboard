"""
Integration test verifying Phase 5 (Task Orchestrator), Phase 6 (Engineering Agent Loop),
and Phase 7 (Verification Dispatcher) handoffs.
"""
import json
import tempfile
from pathlib import Path

from backend.agent.loop import (
    AgentExecutionResult,
    AgentLoopConfig,
    CompletionSignal,
    CriterionEvaluation,
    EngineeringAgentLoop,
    ModelAdapter,
    StopReason,
)
from backend.agent.planning.contracts import Plan, PlanStatus, PlanTask, PlanTaskStatus
from backend.agent.tasks import (
    EngineeringAgentTaskExecutor,
    TaskExecutionContext,
    TaskOrchestrator,
)
from backend.agent.tools import create_default_tool_registry
from backend.agent.verification.dispatcher import VerificationDispatcher
from backend.verification.judge import Judge
from backend.verification.schemas import (
    ExecutionState,
    VerificationReport,
    VerificationResult as LegacyVerificationResult,
)
from backend.verification.static_verifier import StaticVerifier


class MockScriptAdapter(ModelAdapter):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.idx = 0

    async def call_model(self, messages):
        if self.idx < len(self.responses):
            res = self.responses[self.idx]
            self.idx += 1
            return res
        return json.dumps({
            "action": "complete",
            "summary": "Done",
            "acceptance_criteria_status": [{"criterion": "c1", "status": "satisfied", "evidence": "ev"}],
            "verification_requested": True,
        })


class MockPassStaticVerifier(StaticVerifier):
    def verify(self, worktree_path, modified_files=None, git_diff=None):
        return LegacyVerificationResult(
            vector_name="static",
            status="PASS",
            passed=True,
            execution_state="PASS",
            defects=[],
            evidence_manifest=[{"type": "ast_verified", "files": modified_files or []}],
            details={"output": "Static verification passed"},
            execution_time_ms=10.0,
        )


def test_task_orchestrator_with_engineering_loop_and_verification_dispatcher():
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        subprocess.run(["git", "init"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=wt_path, capture_output=True, check=True)
        tool_registry = create_default_tool_registry()

        # Step 1: Create a single task plan
        task1 = PlanTask(
            task_id="task-1",
            step_number=1,
            title="Create user service",
            description="Create user service with get_user function",
            affected_files=["user_service.py"],
            acceptance_criteria=["user_service.py exists with get_user"],
            verification_strategy="verify_static",
        )
        plan = Plan(
            plan_id="plan-integration-1",
            agent_run_id="run-int-1",
            repository_id="repo-int-1",
            requirement="Create user service",
            version=1,
            tasks=[task1],
            status=PlanStatus.APPROVED,
        )

        # Step 2: Set up Phase 6 EngineeringAgentLoop
        scripted_model_responses = [
            json.dumps({
                "action": "tool_call",
                "tool_name": "create_file",
                "arguments": {
                    "path": "user_service.py",
                    "content": "def get_user(uid: int):\n    '''Get user by id'''\n    return {'id': uid}\n",
                },
            }),
            json.dumps({
                "action": "complete",
                "summary": "Created user service with get_user",
                "acceptance_criteria_status": [
                    {
                        "criterion": "user_service.py exists with get_user",
                        "status": "satisfied",
                        "evidence": "Created user_service.py with def get_user",
                    }
                ],
                "verification_requested": True,
            }),
        ]
        adapter = MockScriptAdapter(scripted_model_responses)
        loop = EngineeringAgentLoop(
            tool_registry=tool_registry,
            model_adapter=adapter,
            config=AgentLoopConfig(max_agent_turns=5),
        )
        executor = EngineeringAgentTaskExecutor(agent_loop=loop)

        # Step 3: Set up Phase 7 VerificationDispatcher
        verifier = VerificationDispatcher(
            static_verifier=MockPassStaticVerifier(),
            judge=Judge(),
        )

        orchestrator = TaskOrchestrator(executor=executor, verifier=verifier)
        orchestrator.evaluate_dependencies(plan)

        # Select and execute task
        next_task = orchestrator.select_next_task(plan)
        assert next_task is not None
        assert next_task.task_id == "task-1"

        exec_ctx = TaskExecutionContext(
            agent_run_id="run-int-1",
            plan_id="plan-integration-1",
            task_id="task-1",
            repository_id="repo-int-1",
            worktree_path=str(wt_path),
            task_definition=next_task,
        )

        orchestrator.start_task(plan, "task-1")
        exec_res = orchestrator.executor.execute_task(exec_ctx)

        assert exec_res.success is True
        assert exec_res.metadata["stop_reason"] == "COMPLETED_FOR_VERIFICATION"

        orchestrator.complete_task_execution(plan, "task-1", exec_res)
        assert next_task.status == PlanTaskStatus.VERIFYING

        # Run Phase 7 verification
        passed, error = orchestrator.verifier.verify_task(exec_ctx, exec_res)
        assert passed is True
        assert error is None

        orchestrator.record_verification_result(plan, "task-1", passed=passed, error=error)
        assert next_task.status == PlanTaskStatus.PASSED
        assert orchestrator.all_tasks_passed(plan) is True
