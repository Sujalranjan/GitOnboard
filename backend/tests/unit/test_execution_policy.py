"""
Unit tests for ExecutionPolicy (Phase 9: Human Approval & Safety Control).
"""
import pytest
from backend.agent.safety.contracts import (
    AgentSafetyConfig,
    CommandPolicyConfig,
    FilesystemPolicyConfig,
    GitPolicyConfig,
    PolicyDecision,
)
from backend.agent.safety.policy import ExecutionPolicy
from backend.agent.tools.contracts import AgentToolContext
from backend.models.implementation import PolicyAction, RiskLevel


@pytest.fixture
def context(tmp_path):
    return AgentToolContext(
        worktree_path=str(tmp_path),
        repository_id="repo-safe-1",
        agent_run_id="run-safe-1",
        task_id="task-safe-1",
    )


def test_read_only_tools_allowed(context):
    policy = ExecutionPolicy()
    for tool in ("read_file", "search_code", "get_symbol", "get_diff", "git_status", "detect_commands"):
        decision = policy.evaluate(tool, context, {"path": "main.py"})
        assert decision.action == PolicyAction.ALLOWED
        assert decision.risk_level == RiskLevel.LOW
        assert decision.approval_required is False


def test_workspace_modification_tools_allowed(context):
    policy = ExecutionPolicy()
    for tool in ("create_file", "modify_file", "apply_patch", "create_checkpoint"):
        decision = policy.evaluate(tool, context, {"path": "src/app.py", "content": "print('ok')"})
        assert decision.action == PolicyAction.ALLOWED
        assert decision.risk_level == RiskLevel.MEDIUM
        assert decision.approval_required is False


def test_path_traversal_escaping_worktree_blocked(context):
    policy = ExecutionPolicy()
    traversal_args = [
        {"path": "../secret.txt"},
        {"file_path": "../../etc/passwd"},
        {"target_file": "sub/../../escape.py"},
        {"files": ["valid.py", "../invalid.py"]},
    ]
    for args in traversal_args:
        decision = policy.evaluate("read_file", context, args)
        assert decision.action == PolicyAction.BLOCKED
        assert decision.risk_level == RiskLevel.CRITICAL
        assert "Path traversal detected" in decision.reason


def test_protected_files_blocked(context):
    policy = ExecutionPolicy()
    for prot in (".git/config", ".env", "id_rsa", ".ssh/authorized_keys"):
        decision = policy.evaluate("read_file", context, {"path": prot})
        assert decision.action == PolicyAction.BLOCKED
        assert "protected file" in decision.reason.lower()


def test_allowed_terminal_commands(context):
    policy = ExecutionPolicy()
    allowed_cmds = [
        "pytest tests/test_auth.py",
        "uv run pytest -v",
        "python -m pytest",
        "npm test",
        "npm run build",
        "cargo test",
        "go test ./...",
    ]
    for cmd in allowed_cmds:
        decision = policy.evaluate("execute_command", context, {"command": cmd})
        assert decision.action == PolicyAction.ALLOWED
        assert decision.risk_level == RiskLevel.LOW
        assert decision.approval_required is False


def test_destructive_terminal_commands_blocked(context):
    policy = ExecutionPolicy()
    blocked_cmds = [
        "sudo rm -rf /",
        "rm -rf *",
        "format C:",
        "dd if=/dev/zero of=/dev/sda",
        "mkfs.ext4 /dev/sda1",
        "dropdb production",
    ]
    for cmd in blocked_cmds:
        decision = policy.evaluate("execute_command", context, {"command": cmd})
        assert decision.action == PolicyAction.BLOCKED
        assert decision.risk_level == RiskLevel.CRITICAL
        assert decision.approval_required is False


def test_risky_commands_require_approval(context):
    policy = ExecutionPolicy()
    approval_cmds = [
        "git reset --hard HEAD~1",
        "git clean -fd",
        "git restore src/",
        "git checkout -- file.py",
        "rm -rf build/",
        "rm main.py",
    ]
    for cmd in approval_cmds:
        decision = policy.evaluate("execute_command", context, {"command": cmd})
        assert decision.action == PolicyAction.APPROVAL_REQUIRED
        assert decision.risk_level == RiskLevel.HIGH
        assert decision.approval_required is True


def test_destructive_tools_require_approval(context):
    policy = ExecutionPolicy()
    decision = policy.evaluate("delete_file", context, {"path": "main.py"})
    assert decision.action == PolicyAction.APPROVAL_REQUIRED
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.approval_required is True


def test_explicit_tool_override(context):
    policy = ExecutionPolicy()
    policy.set_tool_policy("read_file", PolicyAction.BLOCKED, reason="Auditing active")
    decision = policy.evaluate("read_file", context, {"path": "main.py"})
    assert decision.action == PolicyAction.BLOCKED
    assert decision.reason == "Auditing active"


def test_timeout_override_is_policy_controlled(context):
    config = AgentSafetyConfig(
        command_policy=CommandPolicyConfig(max_command_duration_sec=45.0)
    )
    policy = ExecutionPolicy(config=config)
    decision = policy.evaluate("execute_command", context, {"command": "pytest"})
    assert decision.timeout_override_sec == 45.0
