"""
Unit tests for TaskStateMachine (Phase 5).
"""
import pytest
from backend.agent.planning.contracts import PlanTaskStatus
from backend.agent.tasks.state_machine import (
    InvalidTaskStateTransitionError,
    TaskStateMachine,
)


def test_task_state_machine_valid_transitions():
    sm = TaskStateMachine()

    # Happy path lifecycle
    assert sm.can_transition(PlanTaskStatus.PENDING, PlanTaskStatus.READY) is True
    assert sm.can_transition(PlanTaskStatus.READY, PlanTaskStatus.RUNNING) is True
    assert sm.can_transition(PlanTaskStatus.RUNNING, PlanTaskStatus.VERIFYING) is True
    assert sm.can_transition(PlanTaskStatus.VERIFYING, PlanTaskStatus.PASSED) is True

    # Failure paths
    assert sm.can_transition(PlanTaskStatus.RUNNING, PlanTaskStatus.FAILED) is True
    assert sm.can_transition(PlanTaskStatus.VERIFYING, PlanTaskStatus.FAILED) is True

    # Blocked and skipped
    assert sm.can_transition(PlanTaskStatus.READY, PlanTaskStatus.BLOCKED) is True
    assert sm.can_transition(PlanTaskStatus.READY, PlanTaskStatus.SKIPPED) is True
    assert sm.can_transition(PlanTaskStatus.RUNNING, PlanTaskStatus.BLOCKED) is True


def test_task_state_machine_invalid_transitions():
    sm = TaskStateMachine()

    # Disallowed forward/backward jumps
    assert sm.can_transition(PlanTaskStatus.PENDING, PlanTaskStatus.RUNNING) is False
    assert sm.can_transition(PlanTaskStatus.PENDING, PlanTaskStatus.PASSED) is False
    assert sm.can_transition(PlanTaskStatus.READY, PlanTaskStatus.PASSED) is False
    assert sm.can_transition(PlanTaskStatus.RUNNING, PlanTaskStatus.PASSED) is False  # Must go through VERIFYING

    with pytest.raises(InvalidTaskStateTransitionError):
        sm.validate_transition("task-1", PlanTaskStatus.PENDING, PlanTaskStatus.RUNNING)


def test_task_state_machine_terminal_states_lock():
    sm = TaskStateMachine()

    # Terminal states
    assert sm.is_terminal(PlanTaskStatus.PASSED) is True
    assert sm.is_terminal(PlanTaskStatus.FAILED) is True
    assert sm.is_terminal(PlanTaskStatus.BLOCKED) is True
    assert sm.is_terminal(PlanTaskStatus.SKIPPED) is True

    # Non-terminal states
    assert sm.is_terminal(PlanTaskStatus.PENDING) is False
    assert sm.is_terminal(PlanTaskStatus.READY) is False
    assert sm.is_terminal(PlanTaskStatus.RUNNING) is False
    assert sm.is_terminal(PlanTaskStatus.VERIFYING) is False

    # Attempting to transition from terminal state must raise
    with pytest.raises(InvalidTaskStateTransitionError):
        sm.validate_transition("task-1", PlanTaskStatus.PASSED, PlanTaskStatus.RUNNING)

    with pytest.raises(InvalidTaskStateTransitionError):
        sm.validate_transition("task-2", PlanTaskStatus.FAILED, PlanTaskStatus.READY)

    with pytest.raises(InvalidTaskStateTransitionError):
        sm.validate_transition("task-3", PlanTaskStatus.BLOCKED, PlanTaskStatus.RUNNING)
