"""
Unit tests for Phase 6 Engineering Agent Loop data contracts.
"""
import pytest
from datetime import datetime, timezone

from backend.agent.loop.contracts import (
    AgentExecutionResult,
    AgentLoopConfig,
    CompletionSignal,
    CriterionEvaluation,
    StopReason,
    ToolCall,
    ToolObservation,
)


def test_agent_loop_config_defaults():
    config = AgentLoopConfig()
    assert config.max_agent_turns == 30
    assert config.max_tool_calls == 50
    assert config.max_command_executions == 10
    assert config.max_execution_seconds == 900.0
    assert config.max_command_seconds == 120.0
    assert config.max_observation_bytes == 50000
    assert config.max_repeated_tool_calls == 3


def test_stop_reason_enum_values():
    assert StopReason.COMPLETED_FOR_VERIFICATION.value == "COMPLETED_FOR_VERIFICATION"
    assert StopReason.MAX_TURNS_EXCEEDED.value == "MAX_TURNS_EXCEEDED"
    assert StopReason.MAX_TOOL_CALLS_EXCEEDED.value == "MAX_TOOL_CALLS_EXCEEDED"
    assert StopReason.MAX_COMMANDS_EXCEEDED.value == "MAX_COMMANDS_EXCEEDED"
    assert StopReason.EXECUTION_TIMEOUT.value == "EXECUTION_TIMEOUT"
    assert StopReason.REPEATED_TOOL_CALL_LIMIT.value == "REPEATED_TOOL_CALL_LIMIT"
    assert StopReason.POLICY_DENIED.value == "POLICY_DENIED"
    assert StopReason.INVALID_TOOL_CALL.value == "INVALID_TOOL_CALL"
    assert StopReason.INVALID_COMPLETION.value == "INVALID_COMPLETION"
    assert StopReason.MODEL_ERROR.value == "MODEL_ERROR"
    assert StopReason.CANCELLED.value == "CANCELLED"
    assert StopReason.EXECUTION_ERROR.value == "EXECUTION_ERROR"


def test_tool_call_and_observation_envelopes():
    call = ToolCall(
        tool_call_id="call_123",
        tool_name="read_file",
        arguments={"path": "backend/main.py"},
    )
    assert call.tool_name == "read_file"
    assert call.arguments["path"] == "backend/main.py"

    obs = ToolObservation(
        tool_call_id="call_123",
        tool_name="read_file",
        success=True,
        data={"content": "print('hello')"},
        duration_ms=12.5,
    )
    assert obs.success is True
    assert obs.data["content"] == "print('hello')"
    assert obs.duration_ms == 12.5


def test_completion_signal_validation():
    crit = CriterionEvaluation(
        criterion="Endpoint returns 200 OK",
        status="satisfied",
        evidence="Verified via tests/test_users.py::test_get_user",
    )
    signal = CompletionSignal(
        summary="Added user endpoint with 404 handler",
        acceptance_criteria_status=[crit],
        verification_requested=True,
    )
    assert signal.summary == "Added user endpoint with 404 handler"
    assert len(signal.acceptance_criteria_status) == 1
    assert signal.verification_requested is True


def test_agent_execution_result_payload():
    result = AgentExecutionResult(
        status="COMPLETED_FOR_VERIFICATION",
        task_id="task_1",
        iterations=3,
        tool_call_count=2,
        changed_files=["routes/users.py"],
        diff="--- a/routes/users.py\n+++ b/routes/users.py\n@@ -1 +1,2 @@",
        observations=["Tool read_file: SUCCESS", "Tool modify_file: SUCCESS"],
        tool_calls=[],
        stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
        duration_ms=450.0,
    )
    assert result.status == "COMPLETED_FOR_VERIFICATION"
    assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
    assert result.iterations == 3
    assert len(result.changed_files) == 1
