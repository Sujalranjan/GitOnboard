"""
Integration tests between Phase 5 TaskOrchestrator and Phase 6 EngineeringAgentTaskExecutor.
"""
import pytest
from typing import List

from backend.agent.loop import (
    AgentLoopConfig,
    EngineeringAgentLoop,
    ModelAdapter,
)
from backend.agent.planning.contracts import Plan, PlanStatus, PlanTask, PlanTaskStatus
from backend.agent.tasks import (
    DefaultVerificationDispatcher,
    EngineeringAgentTaskExecutor,
    TaskExecutionContext,
    TaskOrchestrator,
)
from backend.agent.tools import AgentToolRegistry, PolicyAction, ToolDefinition, ToolPolicy


class MockLoopAdapter(ModelAdapter):
    def __init__(self, responses: List[str]):
        super().__init__()
        self.responses = list(responses)
        self.idx = 0

    async def call_model(self, messages) -> str:
        if self.idx < len(self.responses):
            resp = self.responses[self.idx]
            self.idx += 1
            return resp
        return '{"action": "complete", "summary": "Fallback complete", "acceptance_criteria_status": [{"criterion": "c", "status": "satisfied", "evidence": "e"}]}'


def test_task_orchestrator_with_engineering_agent_loop_executor():
    # Setup tools and mock model adapter
    registry = AgentToolRegistry(policy=ToolPolicy())
    registry.register(
        ToolDefinition(
            name="read_file",
            description="Reads file",
            category="workspace",
            input_schema={"type": "object"},
            handler=lambda args, ctx: {"content": "ok"},
        ),
        default_policy=PolicyAction.ALLOWED,
    )

    responses = [
        '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "auth.py"}}',
        '{"action": "complete", "summary": "Implemented auth check", "acceptance_criteria_status": [{"criterion": "Auth check passes", "status": "satisfied", "evidence": "Tested in auth.py"}], "verification_requested": true}',
    ]
    model_adapter = MockLoopAdapter(responses)
    loop = EngineeringAgentLoop(
        tool_registry=registry,
        model_adapter=model_adapter,
        config=AgentLoopConfig(max_agent_turns=5),
    )

    executor = EngineeringAgentTaskExecutor(loop=loop)
    verifier = DefaultVerificationDispatcher()
    orchestrator = TaskOrchestrator(executor=executor, verifier=verifier)

    task1 = PlanTask(
        task_id="t1",
        step_number=1,
        title="Implement Auth",
        description="Auth endpoint",
        affected_files=["backend/auth.py"],
        acceptance_criteria=["Auth check passes"],
        dependencies=[],
        status=PlanTaskStatus.READY,
    )
    task2 = PlanTask(
        task_id="t2",
        step_number=2,
        title="Implement Profile",
        description="Profile endpoint",
        affected_files=["backend/profile.py"],
        acceptance_criteria=["Profile returns user"],
        dependencies=["t1"],
        status=PlanTaskStatus.PENDING,
    )
    plan = Plan(
        plan_id="plan_int_1",
        agent_run_id="run_int_1",
        repository_id="repo_1",
        title="Auth & Profile Plan",
        requirement="Implement Auth and Profile endpoints",
        status=PlanStatus.APPROVED,
        tasks=[task1, task2],
    )

    # 1. Orchestrator selects task 1
    selected = orchestrator.select_next_task(plan)
    assert selected is not None
    assert selected.task_id == "t1"

    # 2. Start task 1
    orchestrator.start_task(plan, "t1")
    assert plan.get_task("t1").status == PlanTaskStatus.RUNNING

    # 3. Execute task 1 via EngineeringAgentTaskExecutor
    exec_ctx = TaskExecutionContext(
        agent_run_id=plan.agent_run_id,
        plan_id=plan.plan_id,
        task_id="t1",
        repository_id=plan.repository_id,
        task_definition=selected,
    )
    exec_res = orchestrator.executor.execute(exec_ctx)

    assert exec_res.success is True
    assert exec_res.status == PlanTaskStatus.VERIFYING
    assert exec_res.summary == "Implemented auth check"
    assert exec_res.metadata["iterations"] == 2
    assert exec_res.metadata["tool_call_count"] == 1

    # 4. Complete execution handoff to Phase 7 verification
    orchestrator.complete_task_execution(plan, "t1", exec_res)
    assert plan.get_task("t1").status == PlanTaskStatus.VERIFYING

    # 5. Verify task
    passed, err = orchestrator.verifier.verify_task(exec_ctx, exec_res)
    assert passed is True
    assert err is None

    orchestrator.record_verification_result(plan, "t1", passed, err)
    assert plan.get_task("t1").status == PlanTaskStatus.PASSED

    # 6. Downstream task 2 is now unblocked and READY
    assert plan.get_task("t2").status == PlanTaskStatus.READY
    next_task = orchestrator.select_next_task(plan)
    assert next_task is not None
    assert next_task.task_id == "t2"
