"""
Unit tests for Task Orchestrator Engine (Phase 5).
"""
import pytest
from backend.agent.planning.contracts import Plan, PlanStatus, PlanTask, PlanTaskStatus
from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult
from backend.agent.tasks.executor import DefaultTaskExecutor
from backend.agent.tasks.orchestrator import TaskOrchestrator, TaskOrchestratorError
from backend.agent.tasks.verification import DefaultVerificationDispatcher


def _create_sample_plan(status=PlanStatus.APPROVED):
    t1 = PlanTask(task_id="task-1", step_number=1, title="Task 1", description="desc", dependencies=[])
    t2 = PlanTask(task_id="task-2", step_number=2, title="Task 2", description="desc", dependencies=["task-1"])
    return Plan(
        plan_id="test_plan",
        agent_run_id="run_1",
        repository_id="repo_1",
        requirement="test",
        status=status,
        tasks=[t1, t2],
    )


def test_unapproved_plan_rejected_for_execution():
    orchestrator = TaskOrchestrator()
    unapproved_plan = _create_sample_plan(status=PlanStatus.READY_FOR_APPROVAL)

    with pytest.raises(TaskOrchestratorError, match="Plan must be APPROVED"):
        orchestrator.start_task(unapproved_plan, "task-1")


def test_deterministic_task_selection_ordering():
    orchestrator = TaskOrchestrator()

    # Two independent tasks
    t1 = PlanTask(task_id="task-b", step_number=2, title="Task B", description="desc", dependencies=[])
    t2 = PlanTask(task_id="task-a", step_number=1, title="Task A", description="desc", dependencies=[])
    plan = Plan(
        plan_id="test_plan",
        agent_run_id="run_1",
        repository_id="repo_1",
        requirement="test",
        status=PlanStatus.APPROVED,
        tasks=[t1, t2],
    )

    # Must select task-a first because step_number=1 < step_number=2
    selected = orchestrator.select_next_task(plan)
    assert selected is not None
    assert selected.task_id == "task-a"


def test_sequential_task_execution_flow():
    executor = DefaultTaskExecutor()
    verifier = DefaultVerificationDispatcher()
    orchestrator = TaskOrchestrator(executor=executor, verifier=verifier)

    plan = _create_sample_plan(status=PlanStatus.APPROVED)

    # Step 1: Select task-1
    task1 = orchestrator.select_next_task(plan)
    assert task1.task_id == "task-1"
    assert task1.status == PlanTaskStatus.READY

    # Step 2: Start task-1
    orchestrator.start_task(plan, "task-1")
    assert task1.status == PlanTaskStatus.RUNNING

    # Step 3: Complete execution
    exec_ctx = TaskExecutionContext(
        agent_run_id="run_1",
        plan_id=plan.plan_id,
        task_id="task-1",
        repository_id="repo_1",
        task_definition=task1,
    )
    exec_res = executor.execute(exec_ctx)
    orchestrator.complete_task_execution(plan, "task-1", exec_res)
    assert task1.status == PlanTaskStatus.VERIFYING

    # Step 4: Verify task-1
    passed, err = verifier.verify_task(exec_ctx, exec_res)
    orchestrator.record_verification_result(plan, "task-1", passed, err)
    assert task1.status == PlanTaskStatus.PASSED

    # Step 5: task-2 must now be READY
    task2 = orchestrator.select_next_task(plan)
    assert task2.task_id == "task-2"
    assert task2.status == PlanTaskStatus.READY


def test_task_execution_failure_propagation():
    executor = DefaultTaskExecutor(simulate_failure=True, failure_message="Compilation failed")
    orchestrator = TaskOrchestrator(executor=executor)

    plan = _create_sample_plan(status=PlanStatus.APPROVED)

    task1 = orchestrator.select_next_task(plan)
    orchestrator.start_task(plan, "task-1")

    exec_ctx = TaskExecutionContext(
        agent_run_id="run_1",
        plan_id=plan.plan_id,
        task_id="task-1",
        repository_id="repo_1",
        task_definition=task1,
    )
    exec_res = executor.execute(exec_ctx)
    orchestrator.complete_task_execution(plan, "task-1", exec_res)

    assert task1.status == PlanTaskStatus.FAILED
    assert task1.failure_reason == "Compilation failed"

    # task-2 must be BLOCKED
    t2 = plan.tasks[1]
    assert t2.status == PlanTaskStatus.BLOCKED
    assert "task-1" in t2.blocked_reason
