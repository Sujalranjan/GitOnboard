"""
Unit tests for AgentStateMachine and state transition enforcement.
"""
import pytest

from backend.agent.state_machine import (
    AgentStateMachine,
    InvalidStateTransitionError,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
)
from backend.models.implementation import (
    AgentRunStatus,
    AgentState,
    map_agent_state_to_legacy_status,
)


def test_state_machine_valid_happy_path():
    sm = AgentStateMachine()

    # IDLE -> UNDERSTANDING
    assert sm.can_transition(AgentState.IDLE, AgentState.UNDERSTANDING)
    res = sm.validate_transition(AgentState.IDLE, AgentState.UNDERSTANDING)
    assert res == AgentState.UNDERSTANDING

    # UNDERSTANDING -> PLANNING
    assert sm.can_transition(AgentState.UNDERSTANDING, AgentState.PLANNING)
    res = sm.validate_transition(AgentState.UNDERSTANDING, AgentState.PLANNING)
    assert res == AgentState.PLANNING

    # PLANNING -> AWAITING_APPROVAL
    assert sm.can_transition(AgentState.PLANNING, AgentState.AWAITING_APPROVAL)
    res = sm.validate_transition(AgentState.PLANNING, AgentState.AWAITING_APPROVAL)
    assert res == AgentState.AWAITING_APPROVAL

    # AWAITING_APPROVAL -> EXECUTING
    assert sm.can_transition(AgentState.AWAITING_APPROVAL, AgentState.EXECUTING)
    res = sm.validate_transition(AgentState.AWAITING_APPROVAL, AgentState.EXECUTING)
    assert res == AgentState.EXECUTING

    # EXECUTING -> VERIFYING
    assert sm.can_transition(AgentState.EXECUTING, AgentState.VERIFYING)
    res = sm.validate_transition(AgentState.EXECUTING, AgentState.VERIFYING)
    assert res == AgentState.VERIFYING

    # VERIFYING -> COMPLETED
    assert sm.can_transition(AgentState.VERIFYING, AgentState.COMPLETED)
    res = sm.validate_transition(AgentState.VERIFYING, AgentState.COMPLETED)
    assert res == AgentState.COMPLETED


def test_state_machine_fast_path():
    sm = AgentStateMachine()

    # UNDERSTANDING -> EXECUTING (Direct execution without explicit approval)
    assert sm.can_transition(AgentState.UNDERSTANDING, AgentState.EXECUTING)
    assert sm.validate_transition(AgentState.UNDERSTANDING, AgentState.EXECUTING) == AgentState.EXECUTING

    # PLANNING -> EXECUTING
    assert sm.can_transition(AgentState.PLANNING, AgentState.EXECUTING)
    assert sm.validate_transition(AgentState.PLANNING, AgentState.EXECUTING) == AgentState.EXECUTING


def test_state_machine_rejections():
    sm = AgentStateMachine()

    # Cannot jump IDLE -> COMPLETED
    assert not sm.can_transition(AgentState.IDLE, AgentState.COMPLETED)
    with pytest.raises(InvalidStateTransitionError):
        sm.validate_transition(AgentState.IDLE, AgentState.COMPLETED)

    # Cannot jump IDLE -> EXECUTING
    assert not sm.can_transition(AgentState.IDLE, AgentState.EXECUTING)
    with pytest.raises(InvalidStateTransitionError):
        sm.validate_transition(AgentState.IDLE, AgentState.EXECUTING)

    # Cannot transition backwards from VERIFYING -> UNDERSTANDING
    assert not sm.can_transition(AgentState.VERIFYING, AgentState.UNDERSTANDING)
    with pytest.raises(InvalidStateTransitionError):
        sm.validate_transition(AgentState.VERIFYING, AgentState.UNDERSTANDING)


def test_terminal_states_lock():
    sm = AgentStateMachine()

    assert sm.is_terminal(AgentState.COMPLETED)
    assert sm.is_terminal(AgentState.FAILED)
    assert sm.is_terminal(AgentState.CANCELLED)

    assert not sm.is_terminal(AgentState.IDLE)
    assert not sm.is_terminal(AgentState.UNDERSTANDING)
    assert not sm.is_terminal(AgentState.EXECUTING)

    # Terminal states reject all outbound transitions
    for term in (AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED):
        for target in AgentState:
            assert not sm.can_transition(term, target)
            with pytest.raises(InvalidStateTransitionError):
                sm.validate_transition(term, target)


def test_cancellation_from_all_active_states():
    sm = AgentStateMachine()

    active_states = [
        AgentState.IDLE,
        AgentState.UNDERSTANDING,
        AgentState.PLANNING,
        AgentState.AWAITING_APPROVAL,
        AgentState.EXECUTING,
        AgentState.VERIFYING,
    ]

    for st in active_states:
        assert sm.can_transition(st, AgentState.CANCELLED)
        assert sm.validate_transition(st, AgentState.CANCELLED) == AgentState.CANCELLED


def test_failure_from_all_active_states():
    sm = AgentStateMachine()

    active_states = [
        AgentState.IDLE,
        AgentState.UNDERSTANDING,
        AgentState.PLANNING,
        AgentState.AWAITING_APPROVAL,
        AgentState.EXECUTING,
        AgentState.VERIFYING,
    ]

    for st in active_states:
        assert sm.can_transition(st, AgentState.FAILED)
        assert sm.validate_transition(st, AgentState.FAILED) == AgentState.FAILED


def test_legacy_status_mapping():
    assert map_agent_state_to_legacy_status(AgentState.IDLE) == AgentRunStatus.QUEUED
    assert map_agent_state_to_legacy_status(AgentState.UNDERSTANDING) == AgentRunStatus.RUNNING
    assert map_agent_state_to_legacy_status(AgentState.PLANNING) == AgentRunStatus.RUNNING
    assert map_agent_state_to_legacy_status(AgentState.EXECUTING) == AgentRunStatus.RUNNING
    assert map_agent_state_to_legacy_status(AgentState.VERIFYING) == AgentRunStatus.VERIFYING
    assert map_agent_state_to_legacy_status(AgentState.COMPLETED) == AgentRunStatus.COMPLETED
    assert map_agent_state_to_legacy_status(AgentState.FAILED) == AgentRunStatus.FAILED
    assert map_agent_state_to_legacy_status(AgentState.CANCELLED) == AgentRunStatus.FAILED
