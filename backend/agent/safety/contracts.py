"""
Typed safety and approval contracts for Phase 9 (Human Approval & Safety Control).

Guardrail 1: Enums are imported directly from backend.models.implementation to avoid duplication.
Guardrail 2: CANCELLED vs BLOCKED semantics are explicitly defined.
Guardrail 3: timeout_override_sec is policy-controlled.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.models.implementation import (
    ApprovalActionType,
    ApprovalStatus,
    PolicyAction,
    RiskLevel,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PolicyDecision(BaseModel):
    """
    Evaluation result for a proposed tool invocation or execution command.
    """
    action: PolicyAction
    reason: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.LOW
    approval_required: bool = False
    timeout_override_sec: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        return self.action == PolicyAction.ALLOWED

    @property
    def is_blocked(self) -> bool:
        return self.action == PolicyAction.BLOCKED

    @property
    def is_approval_required(self) -> bool:
        return self.action == PolicyAction.APPROVAL_REQUIRED


class CommandPolicyConfig(BaseModel):
    """
    Repository-specific and system terminal command safety policy.
    """
    allowed_command_prefixes: List[str] = Field(
        default_factory=lambda: [
            "pytest",
            "uv run pytest",
            "python -m pytest",
            "python -m unittest",
            "npm test",
            "npm run build",
            "npm run test",
            "cargo test",
            "go test",
            "python scripts/",
            "uv run python",
        ]
    )
    blocked_command_prefixes: List[str] = Field(
        default_factory=lambda: [
            "sudo",
            "rm -rf /",
            "rm -rf *",
            "format",
            "dd if=",
            "mkfs",
            "dropdb",
            "shutdown",
            ":(){ :|:& };:",
        ]
    )
    approval_command_prefixes: List[str] = Field(
        default_factory=lambda: [
            "git reset --hard",
            "git clean",
            "git restore",
            "git checkout --",
            "rm -rf",
            "rm ",
            "del ",
            "rmdir",
        ]
    )
    default_unrecognized_action: PolicyAction = PolicyAction.APPROVAL_REQUIRED
    max_command_duration_sec: float = 120.0


class GitPolicyConfig(BaseModel):
    """
    Policy governing git operations within the isolated worktree.
    """
    allowed_subcommands: List[str] = Field(
        default_factory=lambda: [
            "status",
            "diff",
            "branch",
            "log",
            "rev-parse",
        ]
    )
    approval_subcommands: List[str] = Field(
        default_factory=lambda: [
            "reset --hard",
            "clean",
            "restore",
            "checkout --",
        ]
    )
    blocked_subcommands: List[str] = Field(
        default_factory=lambda: [
            "push",
            "remote add",
            "config --global",
            "clone",
        ]
    )


class FilesystemPolicyConfig(BaseModel):
    """
    Policy governing filesystem isolation and worktree boundaries.
    """
    enforce_worktree_boundary: bool = True
    disallow_parent_traversal: bool = True
    protected_files: List[str] = Field(
        default_factory=lambda: [
            ".git",
            ".env",
            "id_rsa",
            "id_ed25519",
            ".ssh",
        ]
    )


class AgentSafetyConfig(BaseModel):
    """
    Comprehensive safety configuration for an EngineeringAgent run.
    """
    command_policy: CommandPolicyConfig = Field(default_factory=CommandPolicyConfig)
    git_policy: GitPolicyConfig = Field(default_factory=GitPolicyConfig)
    filesystem_policy: FilesystemPolicyConfig = Field(default_factory=FilesystemPolicyConfig)
    require_plan_approval: bool = True
    require_destructive_approval: bool = True
    max_execution_duration_sec: float = 600.0


class ApprovalRequestData(BaseModel):
    """
    Pydantic schema for creating/viewing approval requests.
    """
    approval_id: str
    agent_run_id: str
    task_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    action_type: ApprovalActionType
    action_description: str
    risk_level: RiskLevel
    requested_operation: Dict[str, Any] = Field(default_factory=dict)
    affected_files: List[str] = Field(default_factory=list)
    command: Optional[str] = None
    reason: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=_now)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    rejection_reason: Optional[str] = None


class ApprovalResolution(BaseModel):
    """
    User decision submitted for an approval request.
    """
    approved: bool
    resolved_by: str = "human_user"
    rejection_reason: Optional[str] = None
