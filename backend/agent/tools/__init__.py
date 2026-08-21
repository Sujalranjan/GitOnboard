"""
Agent Tools Package for GitOnBoard (Phase 2).

Provides the typed, policy-governed tool layer over deterministic GitOnBoard subsystems.
"""
from __future__ import annotations

from typing import Optional

from backend.agent.tools.contracts import (
    AgentToolContext,
    ToolDefinition,
    ToolError,
    ToolErrorCode,
    ToolResult,
)
from backend.agent.tools.git import GIT_TOOLS
from backend.agent.tools.policy import PolicyAction, PolicyDecision, ToolPolicy
from backend.agent.tools.registry import AgentToolRegistry
from backend.agent.tools.repository import REPOSITORY_TOOLS
from backend.agent.tools.terminal import TERMINAL_TOOLS
from backend.agent.tools.verification import VERIFICATION_TOOLS
from backend.agent.tools.workspace import WORKSPACE_TOOLS


def create_default_tool_registry(policy: Optional[ToolPolicy] = None) -> AgentToolRegistry:
    """
    Factory function initializing the central AgentToolRegistry populated
    with all Phase 2 approved tools and explicit default policies.
    """
    registry = AgentToolRegistry(policy=policy or ToolPolicy())

    # 1. Register Repository Tools (default: ALLOWED)
    for tool in REPOSITORY_TOOLS:
        registry.register(tool, default_policy=PolicyAction.ALLOWED)

    # 2. Register Workspace Tools (default: ALLOWED, delete_file defaults to APPROVAL_REQUIRED or ALLOWED)
    for tool in WORKSPACE_TOOLS:
        default_pol = PolicyAction.ALLOWED
        registry.register(tool, default_policy=default_pol)

    # 3. Register Terminal Tools (default: ALLOWED)
    for tool in TERMINAL_TOOLS:
        registry.register(tool, default_policy=PolicyAction.ALLOWED)

    # 4. Register Verification Tools (default: ALLOWED)
    for tool in VERIFICATION_TOOLS:
        registry.register(tool, default_policy=PolicyAction.ALLOWED)

    # 5. Register Git Tools (default: ALLOWED)
    for tool in GIT_TOOLS:
        registry.register(tool, default_policy=PolicyAction.ALLOWED)

    return registry


__all__ = [
    "AgentToolRegistry",
    "ToolPolicy",
    "PolicyAction",
    "PolicyDecision",
    "ToolDefinition",
    "ToolResult",
    "ToolError",
    "ToolErrorCode",
    "AgentToolContext",
    "create_default_tool_registry",
    "REPOSITORY_TOOLS",
    "WORKSPACE_TOOLS",
    "TERMINAL_TOOLS",
    "VERIFICATION_TOOLS",
    "GIT_TOOLS",
]
