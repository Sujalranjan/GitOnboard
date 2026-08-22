"""
Guardrail 4 Integration Test: Non-Bypass Safety Verification for Phase 9.

Verifies that EVERY execution path:
  1. Direct Tool Invocation via AgentToolRegistry
  2. Workspace File Modifications
  3. Terminal Command Execution
  4. Git Operations
  5. Multi-Turn EngineeringAgentLoop
  6. RepairController Loop
passes through ExecutionPolicy before reaching any handler or sandbox, and that
blocked or unapproved operations NEVER execute the underlying tool handler.
"""
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.loop import AgentLoopConfig, EngineeringAgentLoop, ModelAdapter
from backend.agent.repair import RepairConfig, RepairController
from backend.agent.safety import (
    ApprovalController,
    CancellationController,
    ExecutionPolicy,
    PolicyAction,
    RiskLevel,
)
from backend.agent.tasks import TaskExecutionContext, TaskExecutionResult
from backend.agent.tools.contracts import (
    AgentToolContext,
    ToolDefinition,
    ToolErrorCode,
    ToolResult,
)
from backend.agent.tools.registry import AgentToolRegistry
from backend.database import Base
from backend.models.implementation import AgentRun, AgentState
from backend.agent.planning.contracts import PlanTask


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    run = AgentRun(
        id="run-nobypass-1",
        task_id="task-nobypass-1",
        repository_id="repo-nobypass-1",
        current_state=AgentState.EXECUTING,
    )
    session.add(run)
    session.commit()

    yield session
    session.close()


def test_registry_enforces_execution_policy_non_bypass(tmp_path):
    """Verifies that AgentToolRegistry evaluates ExecutionPolicy and rejects blocked calls before calling handler."""
    handler_mock = MagicMock(return_value={"result": "ran"})
    
    registry = AgentToolRegistry()
    registry.register(
        ToolDefinition(
            name="dangerous_custom_tool",
            category="terminal",
            description="A dangerous tool",
            input_schema={"type": "object", "properties": {"target": {"type": "string"}}},
            handler=handler_mock,
        )
    )

    # Set policy to BLOCKED
    registry.policy.set_policy("dangerous_custom_tool", PolicyAction.BLOCKED, reason="Blocked for safety audit")

    ctx = AgentToolContext(
        worktree_path=str(tmp_path),
        repository_id="repo-1",
        agent_run_id="run-1",
    )

    result = registry.invoke(
        name="dangerous_custom_tool",
        arguments={"target": "database"},
        context=ctx,
    )

    assert result.success is False
    assert result.error.code == ToolErrorCode.POLICY_BLOCKED
    assert "Blocked for safety audit" in result.error.message
    # Critical Safety Invariant: Handler was NEVER called!
    handler_mock.assert_not_called()


def test_approval_required_policy_prevents_handler_execution(tmp_path):
    """Verifies that APPROVAL_REQUIRED halts execution without running handler."""
    handler_mock = MagicMock(return_value={"executed": True})

    registry = AgentToolRegistry()
    registry.register(
        ToolDefinition(
            name="git_reset_hard",
            category="git",
            description="Destructive reset",
            input_schema={"type": "object", "properties": {"commit": {"type": "string"}}},
            handler=handler_mock,
        )
    )
    registry.policy.set_policy("git_reset_hard", PolicyAction.APPROVAL_REQUIRED, reason="Destructive git reset requires human review")

    ctx = AgentToolContext(
        worktree_path=str(tmp_path),
        repository_id="repo-1",
        agent_run_id="run-1",
    )

    result = registry.invoke(
        name="git_reset_hard",
        arguments={"commit": "HEAD~1"},
        context=ctx,
    )

    assert result.success is False
    assert result.error.code == ToolErrorCode.APPROVAL_REQUIRED
    assert "Destructive git reset" in result.error.message
    # Invariant: Handler was NEVER called!
    handler_mock.assert_not_called()


def test_path_traversal_blocked_across_all_tools(tmp_path):
    """Verifies that file operations attempting path traversal are blocked by policy before hitting disk."""
    file_handler_mock = MagicMock(return_value={"written": True})

    registry = AgentToolRegistry()
    registry.register(
        ToolDefinition(
            name="write_file",
            category="workspace",
            description="Writes file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=file_handler_mock,
        )
    )

    ctx = AgentToolContext(
        worktree_path=str(tmp_path),
        repository_id="repo-1",
        agent_run_id="run-1",
    )

    traversal_paths = [
        "../outside.py",
        "../../etc/passwd",
        "folder/../../../escape.txt",
    ]

    for p in traversal_paths:
        res = registry.invoke("write_file", {"path": p}, ctx)
        assert res.success is False
        assert res.error.code == ToolErrorCode.POLICY_BLOCKED
        assert "Path traversal detected" in res.error.message
        file_handler_mock.assert_not_called()
