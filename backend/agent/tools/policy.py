"""
ToolPolicy: Enforces explicit execution permissions and safety invariants for agent tools.
Delegates to ExecutionPolicy (Phase 9) while maintaining backward-compatible interface.

Safety Invariant:
  When policy evaluates to BLOCKED or APPROVAL_REQUIRED:
    1. A structured rejection ToolResult is returned immediately.
    2. The underlying tool handler NEVER executes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.agent.safety.contracts import AgentSafetyConfig, PolicyDecision
from backend.agent.safety.policy import ExecutionPolicy
from backend.agent.tools.contracts import AgentToolContext
from backend.models.implementation import PolicyAction, RiskLevel

logger = logging.getLogger(__name__)


class ToolPolicy:
    """
    Centralized tool execution policy engine.
    Wraps ExecutionPolicy to enforce context-aware safety, command validation, and path isolation.
    """

    def __init__(
        self,
        default_action: PolicyAction = PolicyAction.ALLOWED,
        safety_config: Optional[AgentSafetyConfig] = None,
    ):
        self.default_action = default_action
        self.execution_policy = ExecutionPolicy(config=safety_config)

    @property
    def _tool_policies(self) -> Dict[str, PolicyAction]:
        return self.execution_policy._tool_overrides

    @property
    def _policy_reasons(self) -> Dict[str, str]:
        return self.execution_policy._tool_reasons

    def set_policy(
        self,
        tool_name: str,
        action: PolicyAction | str,
        reason: Optional[str] = None,
    ) -> None:
        """Sets the explicit policy action for a specific tool."""
        act = action if isinstance(action, PolicyAction) else PolicyAction(str(action))
        self.execution_policy.set_tool_policy(tool_name, act, reason)

    def get_policy(self, tool_name: str) -> PolicyAction:
        """Retrieves configured policy action for tool, falling back to default_action."""
        act = self.execution_policy.get_tool_policy(tool_name)
        return act if act is not None else self.default_action

    def evaluate(
        self,
        tool_name: str,
        context: AgentToolContext,
        arguments: Dict[str, Any],
    ) -> PolicyDecision:
        """
        Evaluates whether a tool invocation is permissible.
        Enforces path traversal safety, terminal command safety, and approval requirements.
        """
        decision = self.execution_policy.evaluate(tool_name, context, arguments)
        return decision
