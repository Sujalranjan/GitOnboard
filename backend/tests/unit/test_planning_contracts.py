"""
Unit tests for Planning Contracts and Data Models (Phase 4).
"""
import pytest
from datetime import datetime, timezone
from backend.agent.planning.contracts import (
    Plan,
    PlanStatus,
    PlanTask,
    PlanTaskStatus,
    PlanValidationResult,
)


def test_plan_task_defaults():
    task = PlanTask(
        task_id="task-1",
        title="Add user validation function",
        description="Write def validate_user in auth/validation.py",
        affected_files=["auth/validation.py"],
        acceptance_criteria=["AC-01: Reject empty username"],
        verification_strategy="verify_static",
    )
    assert task.task_id == "task-1"
    assert task.step_number == 1
    assert task.status == PlanTaskStatus.PENDING
    assert task.dependencies == []
    assert task.attempt_count == 0


def test_plan_instantiation_and_bounded_summary():
    task1 = PlanTask(
        task_id="task-1",
        step_number=1,
        title="Create schema",
        description="Define SQL model",
        affected_files=["models/user.py"],
        acceptance_criteria=["AC-01"],
        verification_strategy="verify_static",
    )
    task2 = PlanTask(
        task_id="task-2",
        step_number=2,
        title="Implement endpoint",
        description="Add POST route",
        dependencies=["task-1"],
        affected_files=["routes/user.py"],
        acceptance_criteria=["AC-02"],
        verification_strategy="verify_test_suite",
    )

    plan = Plan(
        agent_run_id="run_123",
        repository_id="test_repo",
        requirement="Implement user signup flow",
        version=1,
        status=PlanStatus.READY_FOR_APPROVAL,
        tasks=[task1, task2],
        task_dependencies={"task-1": [], "task-2": ["task-1"]},
        acceptance_criteria=["AC-01", "AC-02"],
        unknowns=["No existing auth provider"],
        risks=["Migration required"],
        validation=PlanValidationResult(valid=True),
    )

    assert plan.version == 1
    assert len(plan.tasks) == 2
    assert plan.status == PlanStatus.READY_FOR_APPROVAL

    # Test bounded summary
    summary = plan.to_bounded_summary()
    assert summary["plan_id"] == plan.plan_id
    assert summary["version"] == 1
    assert summary["status"] == "READY_FOR_APPROVAL"
    assert summary["task_count"] == 2
    assert len(summary["tasks"]) == 2
    assert summary["is_valid"] is True
    assert summary["unknowns_count"] == 1
    assert summary["risks_count"] == 1


def test_plan_status_enum_values():
    assert PlanStatus.DRAFT.value == "DRAFT"
    assert PlanStatus.READY_FOR_APPROVAL.value == "READY_FOR_APPROVAL"
    assert PlanStatus.APPROVED.value == "APPROVED"
    assert PlanStatus.REJECTED.value == "REJECTED"
    assert PlanStatus.INVALID.value == "INVALID"
