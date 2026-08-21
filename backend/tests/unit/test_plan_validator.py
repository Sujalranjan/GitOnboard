"""
Unit tests for PlanValidator (Phase 4).
"""
import pytest
from backend.agent.planning.contracts import (
    Plan,
    PlanStatus,
    PlanTask,
    PlanTaskStatus,
)
from backend.agent.planning.validator import PlanValidator


def test_validator_valid_plan():
    validator = PlanValidator()

    task1 = PlanTask(
        task_id="task-1",
        step_number=1,
        title="Add Data Model",
        description="Define SQLAlchemy model",
        affected_files=["models/item.py"],
        acceptance_criteria=["AC-01: Table created"],
        verification_strategy="verify_static",
    )
    task2 = PlanTask(
        task_id="task-2",
        step_number=2,
        title="Add Service Method",
        description="Implement create_item",
        dependencies=["task-1"],
        affected_files=["services/item.py"],
        acceptance_criteria=["AC-02: Item saved"],
        verification_strategy="verify_test_suite",
    )

    plan = Plan(
        agent_run_id="run_test",
        repository_id="test_repo",
        requirement="Add item persistence",
        tasks=[task1, task2],
        unknowns=["Database connection pool size not explicitly verified"],
    )

    res = validator.validate(plan)
    assert res.valid is True
    assert len(res.errors) == 0
    assert len(res.dependency_cycles) == 0
    assert len(res.unknowns) == 1


def test_validator_empty_plan_rejected():
    validator = PlanValidator()
    plan = Plan(
        agent_run_id="run_empty",
        repository_id="test_repo",
        requirement="Do something",
        tasks=[],
    )

    res = validator.validate(plan)
    assert res.valid is False
    assert any("no tasks" in err.lower() for err in res.errors)


def test_validator_missing_acceptance_criteria_rejected():
    validator = PlanValidator()
    task = PlanTask(
        task_id="task-1",
        title="Implement feature",
        description="Write code",
        acceptance_criteria=[],  # Missing!
        verification_strategy="verify_static",
    )
    plan = Plan(
        agent_run_id="run_no_ac",
        repository_id="test_repo",
        requirement="Write feature",
        tasks=[task],
    )

    res = validator.validate(plan)
    assert res.valid is False
    assert "task-1" in res.missing_acceptance_criteria
    assert any("acceptance criteria" in err.lower() for err in res.errors)


def test_validator_missing_verification_strategy_rejected():
    validator = PlanValidator()
    task = PlanTask(
        task_id="task-1",
        title="Implement feature",
        description="Write code",
        acceptance_criteria=["AC-01"],
        verification_strategy="",  # Missing!
    )
    plan = Plan(
        agent_run_id="run_no_verif",
        repository_id="test_repo",
        requirement="Write feature",
        tasks=[task],
    )

    res = validator.validate(plan)
    assert res.valid is False
    assert "task-1" in res.missing_verification
    assert any("verification strategy" in err.lower() for err in res.errors)


def test_validator_circular_dependency_detected():
    validator = PlanValidator()

    # Cycle: task-1 -> task-2 -> task-3 -> task-1
    task1 = PlanTask(
        task_id="task-1",
        title="Step 1",
        description="Desc 1",
        dependencies=["task-3"],
        acceptance_criteria=["AC-01"],
        verification_strategy="verify_static",
    )
    task2 = PlanTask(
        task_id="task-2",
        title="Step 2",
        description="Desc 2",
        dependencies=["task-1"],
        acceptance_criteria=["AC-02"],
        verification_strategy="verify_static",
    )
    task3 = PlanTask(
        task_id="task-3",
        title="Step 3",
        description="Desc 3",
        dependencies=["task-2"],
        acceptance_criteria=["AC-03"],
        verification_strategy="verify_static",
    )

    plan = Plan(
        agent_run_id="run_cycle",
        repository_id="test_repo",
        requirement="Cycle test",
        tasks=[task1, task2, task3],
    )

    res = validator.validate(plan)
    assert res.valid is False
    assert len(res.dependency_cycles) > 0
    assert any("circular dependency" in err.lower() for err in res.errors)
