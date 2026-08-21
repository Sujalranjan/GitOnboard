"""
Unit tests for Task Orchestrator Dependency DAG Evaluation (Phase 5).
"""
import pytest
from backend.agent.planning.contracts import Plan, PlanStatus, PlanTask, PlanTaskStatus
from backend.agent.tasks.orchestrator import TaskOrchestrator


def _create_sample_plan(tasks):
    return Plan(
        plan_id="test_plan",
        agent_run_id="run_1",
        repository_id="repo_1",
        requirement="test",
        status=PlanStatus.APPROVED,
        tasks=tasks,
    )



def test_linear_dependency_dag():
    orchestrator = TaskOrchestrator()

    # Task 1 -> Task 2 -> Task 3
    t1 = PlanTask(task_id="task-1", step_number=1, title="T1", description="desc", dependencies=[])
    t2 = PlanTask(task_id="task-2", step_number=2, title="T2", description="desc", dependencies=["task-1"])
    t3 = PlanTask(task_id="task-3", step_number=3, title="T3", description="desc", dependencies=["task-2"])

    plan = _create_sample_plan([t1, t2, t3])

    # Initial evaluation: only task-1 is READY
    statuses = orchestrator.evaluate_dependencies(plan)
    assert statuses["task-1"] == PlanTaskStatus.READY
    assert statuses["task-2"] == PlanTaskStatus.PENDING
    assert statuses["task-3"] == PlanTaskStatus.PENDING

    # Complete task-1 -> PASSED
    t1.status = PlanTaskStatus.PASSED
    statuses = orchestrator.evaluate_dependencies(plan)
    assert statuses["task-2"] == PlanTaskStatus.READY
    assert statuses["task-3"] == PlanTaskStatus.PENDING

    # Complete task-2 -> PASSED
    t2.status = PlanTaskStatus.PASSED
    statuses = orchestrator.evaluate_dependencies(plan)
    assert statuses["task-3"] == PlanTaskStatus.READY


def test_branching_and_diamond_dependency_dag():
    orchestrator = TaskOrchestrator()

    # Diamond DAG:
    #       t1
    #      /  \
    #    t2    t3
    #      \  /
    #       t4
    t1 = PlanTask(task_id="task-1", step_number=1, title="T1", description="desc", dependencies=[])
    t2 = PlanTask(task_id="task-2", step_number=2, title="T2", description="desc", dependencies=["task-1"])
    t3 = PlanTask(task_id="task-3", step_number=3, title="T3", description="desc", dependencies=["task-1"])
    t4 = PlanTask(task_id="task-4", step_number=4, title="T4", description="desc", dependencies=["task-2", "task-3"])

    plan = _create_sample_plan([t1, t2, t3, t4])

    orchestrator.evaluate_dependencies(plan)
    assert t1.status == PlanTaskStatus.READY
    assert t2.status == PlanTaskStatus.PENDING
    assert t3.status == PlanTaskStatus.PENDING
    assert t4.status == PlanTaskStatus.PENDING

    # Pass T1 -> T2 and T3 become READY, T4 still PENDING
    t1.status = PlanTaskStatus.PASSED
    orchestrator.evaluate_dependencies(plan)
    assert t2.status == PlanTaskStatus.READY
    assert t3.status == PlanTaskStatus.READY
    assert t4.status == PlanTaskStatus.PENDING

    # Pass T2 -> T4 still PENDING (waiting for T3)
    t2.status = PlanTaskStatus.PASSED
    orchestrator.evaluate_dependencies(plan)
    assert t4.status == PlanTaskStatus.PENDING

    # Pass T3 -> T4 finally becomes READY
    t3.status = PlanTaskStatus.PASSED
    orchestrator.evaluate_dependencies(plan)
    assert t4.status == PlanTaskStatus.READY


def test_failed_dependency_blocks_downstream_with_reason():
    orchestrator = TaskOrchestrator()

    t1 = PlanTask(task_id="task-1", step_number=1, title="T1", description="desc", dependencies=[])
    t2 = PlanTask(task_id="task-2", step_number=2, title="T2", description="desc", dependencies=["task-1"])
    t3 = PlanTask(task_id="task-3", step_number=3, title="T3", description="desc", dependencies=["task-2"])

    plan = _create_sample_plan([t1, t2, t3])

    # T1 FAILS
    t1.status = PlanTaskStatus.FAILED
    t1.failure_reason = "Syntax error in model generation"

    orchestrator.evaluate_dependencies(plan)

    # T2 and T3 must become BLOCKED with explicit upstream reason preserved
    assert t2.status == PlanTaskStatus.BLOCKED
    assert "task-1" in t2.blocked_reason
    assert "FAILED" in t2.blocked_reason

    assert t3.status == PlanTaskStatus.BLOCKED
    assert "task-2" in t3.blocked_reason
