"""
Unit tests for Phase 6 LoopGuardrails & hard safety limits.
"""
import time
import pytest

from backend.agent.loop.contracts import AgentLoopConfig, StopReason
from backend.agent.loop.guardrails import LoopGuardrails


def test_turn_limit_guardrail():
    config = AgentLoopConfig(max_agent_turns=3)
    guardrails = LoopGuardrails(config=config)

    assert guardrails.check_pre_turn_limits() is None
    guardrails.record_turn()

    assert guardrails.check_pre_turn_limits() is None
    guardrails.record_turn()

    assert guardrails.check_pre_turn_limits() is None
    guardrails.record_turn()

    assert guardrails.check_pre_turn_limits() == StopReason.MAX_TURNS_EXCEEDED


def test_timeout_guardrail():
    config = AgentLoopConfig(max_execution_seconds=0.05)
    guardrails = LoopGuardrails(config=config)

    time.sleep(0.06)
    assert guardrails.check_pre_turn_limits() == StopReason.EXECUTION_TIMEOUT


def test_max_tool_calls_guardrail():
    config = AgentLoopConfig(max_tool_calls=2)
    guardrails = LoopGuardrails(config=config)

    stop_reason, _ = guardrails.record_tool_call("read_file", {"path": "a.py"})
    assert stop_reason is None

    stop_reason, _ = guardrails.record_tool_call("read_file", {"path": "b.py"})
    assert stop_reason is None

    stop_reason, _ = guardrails.record_tool_call("read_file", {"path": "c.py"})
    assert stop_reason == StopReason.MAX_TOOL_CALLS_EXCEEDED


def test_max_command_executions_guardrail():
    config = AgentLoopConfig(max_command_executions=2)
    guardrails = LoopGuardrails(config=config)

    stop_reason, _ = guardrails.record_tool_call("execute_command", {"command": "git status"})
    assert stop_reason is None

    stop_reason, _ = guardrails.record_tool_call("execute_command", {"command": "ls"})
    assert stop_reason is None

    stop_reason, _ = guardrails.record_tool_call("execute_command", {"command": "pwd"})
    assert stop_reason == StopReason.MAX_COMMANDS_EXCEEDED


def test_repeated_tool_call_detection_and_warning():
    config = AgentLoopConfig(max_repeated_tool_calls=3)
    guardrails = LoopGuardrails(config=config)

    # Call 1: distinct
    stop_reason, should_warn = guardrails.record_tool_call("read_file", {"path": "users.py"})
    assert stop_reason is None
    assert should_warn is False

    # Call 2: repeated -> should warn
    stop_reason, should_warn = guardrails.record_tool_call("read_file", {"path": "users.py"})
    assert stop_reason is None
    assert should_warn is True

    # Call 3: repeated again -> triggers REPEATED_TOOL_CALL_LIMIT
    stop_reason, should_warn = guardrails.record_tool_call("read_file", {"path": "users.py"})
    assert stop_reason == StopReason.REPEATED_TOOL_CALL_LIMIT


def test_repeated_tool_call_streak_reset_on_different_args():
    config = AgentLoopConfig(max_repeated_tool_calls=3)
    guardrails = LoopGuardrails(config=config)

    guardrails.record_tool_call("read_file", {"path": "users.py"})
    _, should_warn = guardrails.record_tool_call("read_file", {"path": "users.py"})
    assert should_warn is True

    # Call with different arg resets streak
    stop_reason, should_warn = guardrails.record_tool_call("read_file", {"path": "services.py"})
    assert stop_reason is None
    assert should_warn is False


def test_observation_truncation():
    config = AgentLoopConfig(max_observation_bytes=50)
    guardrails = LoopGuardrails(config=config)

    short_data = "Hello world"
    assert guardrails.sanitize_observation(short_data) == "Hello world"

    long_data = "A" * 200
    sanitized = guardrails.sanitize_observation(long_data)
    assert "[OBSERVATION TRUNCATED" in sanitized
