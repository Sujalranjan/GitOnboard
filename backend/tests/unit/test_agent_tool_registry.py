"""
Unit tests for AgentToolRegistry: registration, schema validation, timeout, and result normalization.
"""
import time
import pytest

from backend.agent.tools.contracts import (
    AgentToolContext,
    ToolDefinition,
    ToolErrorCode,
    ToolResult,
)
from backend.agent.tools.policy import PolicyAction, ToolPolicy
from backend.agent.tools.registry import AgentToolRegistry


def _mock_dummy_handler(args, context):
    return {"echo": args.get("msg", ""), "run": context.agent_run_id}


def _mock_slow_handler(args, context):
    time.sleep(1.5)
    return {"done": True}


def _mock_failing_handler(args, context):
    raise ValueError("Internal service database failure")


def test_tool_registration_and_catalog():
    registry = AgentToolRegistry()

    tool = ToolDefinition(
        name="echo_tool",
        description="Echoes input back",
        category="test",
        input_schema={
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        },
        handler=_mock_dummy_handler,
    )

    registry.register(tool, default_policy=PolicyAction.ALLOWED)
    assert registry.get_tool("echo_tool") is not None
    assert len(registry.list_tools()) == 1

    # Catalog inspection: handler is not exposed
    catalog = registry.list_catalog()
    assert len(catalog) == 1
    assert catalog[0]["name"] == "echo_tool"
    assert catalog[0]["policy"] == "ALLOWED"
    assert "handler" not in catalog[0]


def test_duplicate_tool_registration_rejected():
    registry = AgentToolRegistry()
    tool = ToolDefinition(
        name="dup_tool",
        description="Duplicate",
        category="test",
        input_schema={"type": "object"},
        handler=_mock_dummy_handler,
    )
    registry.register(tool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_unknown_tool_rejection():
    registry = AgentToolRegistry()
    context = AgentToolContext(agent_run_id="run_123", repository_id="repo_1")

    res = registry.invoke("non_existent_tool", {}, context)
    assert not res.success
    assert res.error is not None
    assert res.error.code == ToolErrorCode.TOOL_NOT_FOUND.value
    assert "not registered" in res.error.message


def test_input_argument_validation():
    registry = AgentToolRegistry()
    tool = ToolDefinition(
        name="strict_tool",
        description="Requires int port and string host",
        category="test",
        input_schema={
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
            },
            "required": ["host", "port"],
        },
        handler=_mock_dummy_handler,
    )
    registry.register(tool)
    context = AgentToolContext(agent_run_id="run_123", repository_id="repo_1")

    # Missing required argument
    res1 = registry.invoke("strict_tool", {"host": "localhost"}, context)
    assert not res1.success
    assert res1.error.code == ToolErrorCode.INVALID_ARGUMENTS.value

    # Wrong type for argument
    res2 = registry.invoke("strict_tool", {"host": "localhost", "port": "not_an_int"}, context)
    assert not res2.success
    assert res2.error.code == ToolErrorCode.INVALID_ARGUMENTS.value

    # Valid arguments
    res3 = registry.invoke("strict_tool", {"host": "localhost", "port": 8000}, context)
    assert res3.success


def test_successful_invocation_normalization():
    registry = AgentToolRegistry()
    tool = ToolDefinition(
        name="echo_tool",
        description="Echoes input",
        category="test",
        input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        handler=_mock_dummy_handler,
    )
    registry.register(tool)
    context = AgentToolContext(agent_run_id="run_123", repository_id="repo_1")

    res = registry.invoke("echo_tool", {"msg": "hello world"}, context)
    assert res.success
    assert res.error is None
    assert res.data == {"echo": "hello world", "run": "run_123"}
    assert res.metadata["tool_name"] == "echo_tool"
    assert res.metadata["duration_ms"] >= 0


def test_failing_handler_exception_normalization():
    registry = AgentToolRegistry()
    tool = ToolDefinition(
        name="failing_tool",
        description="Throws an exception",
        category="test",
        input_schema={"type": "object"},
        handler=_mock_failing_handler,
    )
    registry.register(tool)
    context = AgentToolContext(agent_run_id="run_123", repository_id="repo_1")

    res = registry.invoke("failing_tool", {}, context)
    assert not res.success
    assert res.error is not None
    assert res.error.code == ToolErrorCode.EXECUTION_FAILED.value
    assert "Internal service database failure" in res.error.message
    assert res.error.details == {"exception_type": "ValueError"}


def test_timeout_enforcement():
    registry = AgentToolRegistry()
    tool = ToolDefinition(
        name="slow_tool",
        description="Sleeps",
        category="test",
        input_schema={"type": "object"},
        default_timeout_sec=0.2,
        handler=_mock_slow_handler,
    )
    registry.register(tool)
    context = AgentToolContext(agent_run_id="run_123", repository_id="repo_1")

    res = registry.invoke("slow_tool", {}, context)
    assert not res.success
    assert res.error.code == ToolErrorCode.TIMEOUT.value
    assert "timed out after 0.2" in res.error.message
