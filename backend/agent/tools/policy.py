"""
ToolPolicy: Enforces explicit execution permissions and safety invariants for agent tools.

Safety Invariant:
  When policy evaluates to BLOCKED or APPROVAL_REQUIRED:
    1. A structured rejection ToolResult is returned immediately.
    2. The underlying tool handler NEVER executes.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from backend.agent.tools.contracts import AgentToolContext, ToolErrorCode, ToolResult

logger = logging.getLogger(__name__)


class PolicyAction(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class PolicyDecision(BaseModel):
    """Result of policy evaluation for a specific tool call."""
    action: PolicyAction
    reason: Optional[str] = None
    timeout_override_sec: Optional[float] = None


class ToolPolicy:
    """
    Centralized tool execution policy engine.
    Evaluates tool authorization, file path constraints, and approval requirements.
    """

    def __init__(self, default_action: PolicyAction = PolicyAction.ALLOWED):
        self.default_action = default_action
        self._tool_policies: Dict[str, PolicyAction] = {}
        self._policy_reasons: Dict[str, str] = {}

    def set_policy(
        self,
        tool_name: str,
        action: PolicyAction | str,
        reason: Optional[str] = None,
    ) -> None:
        """Sets the explicit policy action for a specific tool."""
        act = action if isinstance(action, PolicyAction) else PolicyAction(str(action))
        self._tool_policies[tool_name] = act
        if reason:
            self._policy_reasons[tool_name] = reason

    def get_policy(self, tool_name: str) -> PolicyAction:
        """Retrieves configured policy action for tool, falling back to default_action."""
        return self._tool_policies.get(tool_name, self.default_action)

    def evaluate(
        self,
        tool_name: str,
        context: AgentToolContext,
        arguments: Dict[str, Any],
    ) -> PolicyDecision:
        """
        Evaluates whether a tool invocation is permissible.
        Enforces path traversal safety and explicit policy category.
        """
        # Invariant 1: Path Traversal Isolation Guard
        for key in ("path", "file_path", "target_file"):
            if key in arguments and isinstance(arguments[key], str):
                p = arguments[key]
                if ".." in p or p.startswith("/") or (len(p) > 1 and p[1] == ":"):
                    # Check if absolute path escapes the assigned worktree
                    if context.worktree_path and not p.startswith(context.worktree_path) and (".." in p or p.startswith("/") or (len(p) > 1 and p[1] == ":")):
                        logger.warning(f"Path traversal detected in argument '{key}={p}' for tool '{tool_name}'")
                        return PolicyDecision(
                            action=PolicyAction.BLOCKED,
                            reason=f"Path traversal detected: argument '{key}' escapes assigned worktree boundary",
                        )

        # Invariant 2: Explicit Tool Policy Action
        action = self.get_policy(tool_name)
        reason = self._policy_reasons.get(tool_name)

        if action == PolicyAction.BLOCKED:
            return PolicyDecision(
                action=PolicyAction.BLOCKED,
                reason=reason or f"Tool '{tool_name}' is blocked by security policy",
            )
        elif action == PolicyAction.APPROVAL_REQUIRED:
            return PolicyDecision(
                action=PolicyAction.APPROVAL_REQUIRED,
                reason=reason or f"Tool '{tool_name}' requires explicit user approval before execution",
            )

        return PolicyDecision(action=PolicyAction.ALLOWED)
