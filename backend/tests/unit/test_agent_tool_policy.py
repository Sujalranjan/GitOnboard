"""
Unit tests for ToolPolicy and safety invariants: ALLOWED, BLOCKED, APPROVAL_REQUIRED, and isolation.
"""
from unittest.mock import MagicMock
import pytest

from backend.agent.tools.contracts import (
    AgentToolContext,
    ToolDefinition,
    ToolErrorCode,
)
from backend.agent.tools.policy import PolicyAction, PolicyDecision, ToolPolicy
from backend.agent.tools.registry import AgentToolRegistry


def test_tool_policy_allowed_executes_handler():
    mock_handler = MagicMock(return_value={"executed": True})
    tool = ToolDefinition(
        name="allowed_tool",
        description="Allowed tool",
        category="test",
        input_schema={"type": "object"},
        handler=mock_handler,
    )

    policy = ToolPolicy()
    policy.set_policy("allowed_tool", PolicyAction.ALLOWED)
    registry = AgentToolRegistry(policy=policy)
    registry.register(tool)

    context = AgentToolContext(agent_run_id="run_1", repository_id="repo_1")
    res = registry.invoke("allowed_tool", {}, context)

    assert res.success
    assert res.data == {"executed": True}
    mock_handler.assert_called_once()


def test_tool_policy_blocked_never_calls_handler():
    mock_handler = MagicMock()
    tool = ToolDefinition(
        name="dangerous_tool",
        description="Blocked tool",
        category="test",
        input_schema={"type": "object"},
        handler=mock_handler,
    )

    policy = ToolPolicy()
    policy.set_policy("dangerous_tool", PolicyAction.BLOCKED, reason="Forbidden in this environment")
    registry = AgentToolRegistry(policy=policy)
    registry.register(tool)

    context = AgentToolContext(agent_run_id="run_1", repository_id="repo_1")
    res = registry.invoke("dangerous_tool", {}, context)

    assert not res.success
    assert res.error is not None
    assert res.error.code == ToolErrorCode.POLICY_BLOCKED.value
    assert "Forbidden in this environment" in res.error.message

    # Critical Invariant: Handler was never invoked!
    mock_handler.assert_not_called()


def test_tool_policy_approval_required_never_calls_handler():
    mock_handler = MagicMock()
    tool = ToolDefinition(
        name="destructive_tool",
        description="Requires approval",
        category="test",
        input_schema={"type": "object", "properties": {"target": {"type": "string"}}},
        handler=mock_handler,
    )

    policy = ToolPolicy()
    policy.set_policy("destructive_tool", PolicyAction.APPROVAL_REQUIRED, reason="Needs admin approval")
    registry = AgentToolRegistry(policy=policy)
    registry.register(tool)

    context = AgentToolContext(agent_run_id="run_1", repository_id="repo_1")
    res = registry.invoke("destructive_tool", {"target": "production_db"}, context)

    assert not res.success
    assert res.error is not None
    assert res.error.code == ToolErrorCode.APPROVAL_REQUIRED.value
    assert "Needs admin approval" in res.error.message

    # Critical Invariant: Handler was never invoked!
    mock_handler.assert_not_called()


def test_path_traversal_isolation_guard():
    mock_handler = MagicMock()
    tool = ToolDefinition(
        name="read_file_tool",
        description="Reads file",
        category="test",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=mock_handler,
    )

    policy = ToolPolicy()
    registry = AgentToolRegistry(policy=policy)
    registry.register(tool, default_policy=PolicyAction.ALLOWED)

    context = AgentToolContext(
        agent_run_id="run_1",
        repository_id="repo_1",
        worktree_path="f:/GitOnboard/data/worktrees/repo1_run1",
    )

    # Attempt path traversal escaping worktree
    res = registry.invoke("read_file_tool", {"path": "../../etc/passwd"}, context)

    assert not res.success
    assert res.error.code == ToolErrorCode.POLICY_BLOCKED.value
    assert "Path traversal detected" in res.error.message

    # Handler was never invoked
    mock_handler.assert_not_called()
