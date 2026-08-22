"""
Unit tests for Phase 6 EngineeringAgentLoop execution scenarios.
"""
import pytest
from typing import List

from backend.agent.loop import (
    AgentExecutionResult,
    AgentLoopConfig,
    EngineeringAgentLoop,
    ModelAdapter,
    StopReason,
)
from backend.agent.planning.contracts import PlanTask
from backend.agent.tasks.contracts import TaskExecutionContext
from backend.agent.tools import AgentToolRegistry, PolicyAction, ToolDefinition, ToolPolicy


class MockSequenceModelAdapter(ModelAdapter):
    """Mock adapter returning a deterministic sequence of string responses."""

    def __init__(self, responses: List[str]):
        super().__init__()
        self.responses = list(responses)
        self.call_count = 0

    async def call_model(self, messages) -> str:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return '{"action": "complete", "summary": "Fallback completed", "acceptance_criteria_status": [{"criterion": "c1", "status": "satisfied", "evidence": "e1"}]}'


@pytest.fixture
def sample_task_context():
    task_def = PlanTask(
        task_id="task_test_1",
        step_number=1,
        title="Implement GET /status",
        description="Add status check endpoint",
        affected_files=["backend/routers/status.py"],
        acceptance_criteria=["Endpoint returns 200 OK with health info"],
        verification_strategy="unit_test",
    )
    return TaskExecutionContext(
        agent_run_id="run_101",
        plan_id="plan_202",
        task_id="task_test_1",
        repository_id="repo_303",
        worktree_path=None,
        task_definition=task_def,
    )


@pytest.fixture
def mock_tool_registry():
    registry = AgentToolRegistry(policy=ToolPolicy())

    def dummy_read(args, ctx):
        return {"content": "print('status ok')"}

    registry.register(
        ToolDefinition(
            name="read_file",
            description="Reads file contents",
            category="workspace",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=dummy_read,
        ),
        default_policy=PolicyAction.ALLOWED,
    )
    return registry


def test_loop_multiturn_successful_completion(sample_task_context, mock_tool_registry):
    responses = [
        # Turn 1: tool call
        '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "backend/routers/status.py"}}',
        # Turn 2: complete
        '{"action": "complete", "summary": "Added status endpoint", "acceptance_criteria_status": [{"criterion": "Endpoint returns 200 OK with health info", "status": "satisfied", "evidence": "Implemented in backend/routers/status.py"}], "verification_requested": true}',
    ]
    mock_adapter = MockSequenceModelAdapter(responses)
    loop = EngineeringAgentLoop(
        tool_registry=mock_tool_registry,
        model_adapter=mock_adapter,
        config=AgentLoopConfig(max_agent_turns=5),
    )

    result = loop.run(sample_task_context)

    assert result.status == "COMPLETED_FOR_VERIFICATION"
    assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
    assert result.iterations == 2
    assert result.tool_call_count == 1
    assert result.completion_signal is not None
    assert result.completion_signal.summary == "Added status endpoint"
    assert len(result.changed_files) == 1
    assert result.changed_files[0] == "backend/routers/status.py"


def test_loop_handles_policy_denial(sample_task_context, mock_tool_registry):
    # Set policy to BLOCKED for read_file
    mock_tool_registry.policy.set_policy("read_file", PolicyAction.BLOCKED)

    responses = [
        '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "secret.txt"}}',
        '{"action": "complete", "summary": "Handled block and finished", "acceptance_criteria_status": [{"criterion": "Handled securely", "status": "satisfied", "evidence": "Policy blocked unauthorized read"}], "verification_requested": true}',
    ]
    mock_adapter = MockSequenceModelAdapter(responses)
    loop = EngineeringAgentLoop(
        tool_registry=mock_tool_registry,
        model_adapter=mock_adapter,
        config=AgentLoopConfig(max_agent_turns=5),
    )

    result = loop.run(sample_task_context)

    assert result.status == "COMPLETED_FOR_VERIFICATION"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["success"] is False
    assert result.tool_calls[0]["error"]["code"] == "POLICY_BLOCKED"


def test_loop_detects_repeated_tool_calls_and_terminates(sample_task_context, mock_tool_registry):
    # Model calls read_file 3 times identically
    call_json = '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "same.py"}}'
    responses = [call_json, call_json, call_json, call_json]

    mock_adapter = MockSequenceModelAdapter(responses)
    loop = EngineeringAgentLoop(
        tool_registry=mock_tool_registry,
        model_adapter=mock_adapter,
        config=AgentLoopConfig(max_repeated_tool_calls=3, max_agent_turns=10),
    )

    result = loop.run(sample_task_context)

    assert result.status == "FAILED"
    assert result.stop_reason == StopReason.REPEATED_TOOL_CALL_LIMIT


def test_loop_cancellation(sample_task_context, mock_tool_registry):
    call_json = '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "a.py"}}'
    mock_adapter = MockSequenceModelAdapter([call_json, call_json])

    loop = EngineeringAgentLoop(
        tool_registry=mock_tool_registry,
        model_adapter=mock_adapter,
    )

    # Cancel immediately
    result = loop.run(sample_task_context, cancel_checker=lambda: True)

    assert result.status == "CANCELLED"
    assert result.stop_reason == StopReason.CANCELLED


def test_loop_max_turns_exceeded(sample_task_context, mock_tool_registry):
    # Infinite tool calling loop
    call_json_tmpl = '{{"action": "tool_call", "tool_name": "read_file", "arguments": {{"path": "file_{}.py"}}}}'
    responses = [call_json_tmpl.format(i) for i in range(10)]

    mock_adapter = MockSequenceModelAdapter(responses)
    loop = EngineeringAgentLoop(
        tool_registry=mock_tool_registry,
        model_adapter=mock_adapter,
        config=AgentLoopConfig(max_agent_turns=3),
    )

    result = loop.run(sample_task_context)

    assert result.status == "FAILED"
    assert result.stop_reason == StopReason.MAX_TURNS_EXCEEDED
