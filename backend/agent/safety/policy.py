"""
ExecutionPolicy: Centralized context-aware safety evaluation engine for Phase 9.

Guardrails:
  1. Every tool invocation passes through ExecutionPolicy before reaching any handler.
  2. Path traversal escaping worktree is strictly BLOCKED.
  3. Dangerous commands require human approval or are blocked.
  4. Timeouts are policy-controlled (tools/LLM cannot grant themselves arbitrary duration).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.agent.safety.contracts import (
    AgentSafetyConfig,
    CommandPolicyConfig,
    FilesystemPolicyConfig,
    GitPolicyConfig,
    PolicyDecision,
)
from backend.agent.tools.contracts import AgentToolContext
from backend.models.implementation import PolicyAction, RiskLevel

logger = logging.getLogger(__name__)


class ExecutionPolicy:
    """
    Evaluates whether an operation proposed by the Engineering Agent is permitted to execute.
    """

    def __init__(self, config: Optional[AgentSafetyConfig] = None):
        self.config = config or AgentSafetyConfig()
        self._tool_overrides: Dict[str, PolicyAction] = {}
        self._tool_reasons: Dict[str, str] = {}

    def set_tool_policy(
        self,
        tool_name: str,
        action: PolicyAction | str,
        reason: Optional[str] = None,
    ) -> None:
        """Sets an explicit policy action override for a specific tool."""
        act = action if isinstance(action, PolicyAction) else PolicyAction(str(action))
        self._tool_overrides[tool_name] = act
        if reason:
            self._tool_reasons[tool_name] = reason

    def get_tool_policy(self, tool_name: str) -> Optional[PolicyAction]:
        """Retrieves configured override for tool if any."""
        return self._tool_overrides.get(tool_name)

    def evaluate(
        self,
        tool_name: str,
        context: AgentToolContext,
        arguments: Dict[str, Any],
    ) -> PolicyDecision:
        """
        Evaluates a proposed tool call with context awareness across:
          - Worktree containment and filesystem paths
          - Explicit tool overrides
          - Terminal command safety (blocked vs approval vs allowed)
          - Git operation safety
        """
        # 1. Filesystem & Worktree Isolation Guard (Always enforced first)
        fs_decision = self._evaluate_filesystem(tool_name, context, arguments)
        if fs_decision:
            return fs_decision

        # 2. Check explicit tool override
        if tool_name in self._tool_overrides:
            action = self._tool_overrides[tool_name]
            reason = self._tool_reasons.get(tool_name, f"Tool '{tool_name}' has explicit override: {action.value}")
            risk = RiskLevel.HIGH if action == PolicyAction.BLOCKED else (RiskLevel.MEDIUM if action == PolicyAction.APPROVAL_REQUIRED else RiskLevel.LOW)
            return PolicyDecision(
                action=action,
                reason=reason,
                risk_level=risk,
                approval_required=(action == PolicyAction.APPROVAL_REQUIRED),
                timeout_override_sec=self.config.command_policy.max_command_duration_sec,
            )

        # 3. Terminal Command Policy
        if tool_name in ("execute_command", "run_command", "run_terminal", "execute_terminal"):
            return self._evaluate_command(arguments, context)

        # 4. Git Operations Policy
        if tool_name in ("git_command", "execute_git", "git_reset", "git_clean"):
            return self._evaluate_git_tool(tool_name, arguments, context)

        # 5. Dangerous tool classifications
        if tool_name in ("delete_file", "remove_file", "drop_table"):
            return PolicyDecision(
                action=PolicyAction.APPROVAL_REQUIRED,
                reason=f"Destructive operation '{tool_name}' requires human approval",
                risk_level=RiskLevel.HIGH,
                approval_required=True,
                timeout_override_sec=self.config.command_policy.max_command_duration_sec,
            )

        # 6. Read-only and standard modification tools inside worktree
        if tool_name in (
            "read_file", "search_code", "get_symbol", "get_diff", "find_files",
            "list_directory", "inspect_ast", "git_status", "detect_commands", "verify_static"
        ):
            return PolicyDecision(
                action=PolicyAction.ALLOWED,
                reason=f"Read-only tool '{tool_name}' matches repository inspection policy",
                risk_level=RiskLevel.LOW,
                approval_required=False,
                timeout_override_sec=self.config.command_policy.max_command_duration_sec,
            )

        if tool_name in ("create_file", "modify_file", "apply_patch", "create_checkpoint"):
            return PolicyDecision(
                action=PolicyAction.ALLOWED,
                reason=f"Workspace modification tool '{tool_name}' is permitted within worktree",
                risk_level=RiskLevel.MEDIUM,
                approval_required=False,
                timeout_override_sec=self.config.command_policy.max_command_duration_sec,
            )

        # Default fallback: ALLOWED with standard bounded timeout
        return PolicyDecision(
            action=PolicyAction.ALLOWED,
            reason=f"Tool '{tool_name}' permitted by default safety policy",
            risk_level=RiskLevel.LOW,
            approval_required=False,
            timeout_override_sec=self.config.command_policy.max_command_duration_sec,
        )

    def _evaluate_filesystem(
        self,
        tool_name: str,
        context: AgentToolContext,
        arguments: Dict[str, Any],
    ) -> Optional[PolicyDecision]:
        """Validates that file paths do not escape the assigned worktree boundary."""
        fs_config = self.config.filesystem_policy
        if not fs_config.enforce_worktree_boundary:
            return None

        path_keys = ("path", "file_path", "target_file", "files", "paths", "directory", "cwd")
        paths_to_check: List[str] = []

        for k in path_keys:
            if k in arguments:
                val = arguments[k]
                if isinstance(val, str):
                    paths_to_check.append(val)
                elif isinstance(val, list):
                    paths_to_check.extend([str(item) for item in val if isinstance(item, str)])

        wt = context.worktree_path
        for p_str in paths_to_check:
            # Traversal escape pattern
            if fs_config.disallow_parent_traversal and (".." in p_str):
                logger.warning(f"ExecutionPolicy: Path traversal detected in '{p_str}' for tool '{tool_name}'")
                return PolicyDecision(
                    action=PolicyAction.BLOCKED,
                    reason=f"Path traversal detected: '{p_str}' attempts to escape worktree boundary",
                    risk_level=RiskLevel.CRITICAL,
                    approval_required=False,
                )

            # Protected file check
            p_obj = Path(p_str)
            for prot in fs_config.protected_files:
                if prot in p_obj.parts or p_str.startswith(prot):
                    logger.warning(f"ExecutionPolicy: Access to protected file '{p_str}' rejected")
                    return PolicyDecision(
                        action=PolicyAction.BLOCKED,
                        reason=f"Access to protected file or directory '{prot}' is prohibited",
                        risk_level=RiskLevel.HIGH,
                        approval_required=False,
                    )

            # Absolute path check against worktree
            if wt and os.path.isabs(p_str):
                try:
                    rel = os.path.relpath(p_str, wt)
                    if rel.startswith(".."):
                        logger.warning(f"ExecutionPolicy: Absolute path '{p_str}' escapes worktree '{wt}'")
                        return PolicyDecision(
                            action=PolicyAction.BLOCKED,
                            reason=f"Absolute path '{p_str}' is outside assigned worktree boundary",
                            risk_level=RiskLevel.HIGH,
                            approval_required=False,
                        )
                except Exception:
                    pass

        return None

    def _evaluate_command(
        self,
        arguments: Dict[str, Any],
        context: AgentToolContext,
    ) -> PolicyDecision:
        """Evaluates a terminal shell command string."""
        cmd = str(arguments.get("command", "") or arguments.get("cmd", "")).strip()
        if not cmd:
            return PolicyDecision(
                action=PolicyAction.ALLOWED,
                reason="Empty command",
                risk_level=RiskLevel.LOW,
            )

        cmd_policy = self.config.command_policy

        # Check blocked command prefixes
        for blocked in cmd_policy.blocked_command_prefixes:
            if cmd == blocked or cmd.startswith(blocked + " ") or blocked in cmd:
                logger.warning(f"ExecutionPolicy: Blocked critical command '{cmd}' matching '{blocked}'")
                return PolicyDecision(
                    action=PolicyAction.BLOCKED,
                    reason=f"Command '{cmd}' contains prohibited destructive pattern '{blocked}'",
                    risk_level=RiskLevel.CRITICAL,
                    approval_required=False,
                )

        # Check approval command prefixes
        for req_app in cmd_policy.approval_command_prefixes:
            if cmd == req_app or cmd.startswith(req_app + " ") or req_app in cmd:
                logger.info(f"ExecutionPolicy: Command '{cmd}' requires human approval matching '{req_app}'")
                return PolicyDecision(
                    action=PolicyAction.APPROVAL_REQUIRED,
                    reason=f"Command '{cmd}' is potentially destructive and requires explicit human approval",
                    risk_level=RiskLevel.HIGH,
                    approval_required=True,
                    timeout_override_sec=cmd_policy.max_command_duration_sec,
                )

        # Check allowed command prefixes
        for allowed in cmd_policy.allowed_command_prefixes:
            if cmd == allowed or cmd.startswith(allowed + " "):
                return PolicyDecision(
                    action=PolicyAction.ALLOWED,
                    reason=f"Command matches allowed repository execution policy ('{allowed}')",
                    risk_level=RiskLevel.LOW,
                    approval_required=False,
                    timeout_override_sec=cmd_policy.max_command_duration_sec,
                )

        # Unrecognized command fallback
        action = cmd_policy.default_unrecognized_action
        return PolicyDecision(
            action=action,
            reason=f"Unrecognized command '{cmd}' requires approval under default policy",
            risk_level=RiskLevel.MEDIUM,
            approval_required=(action == PolicyAction.APPROVAL_REQUIRED),
            timeout_override_sec=cmd_policy.max_command_duration_sec,
        )

    def _evaluate_git_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: AgentToolContext,
    ) -> PolicyDecision:
        """Evaluates git tool calls."""
        subcmd = str(arguments.get("subcommand", "") or arguments.get("command", "")).strip()
        git_config = self.config.git_policy

        for blk in git_config.blocked_subcommands:
            if subcmd.startswith(blk):
                return PolicyDecision(
                    action=PolicyAction.BLOCKED,
                    reason=f"Git operation '{subcmd}' is blocked by policy",
                    risk_level=RiskLevel.HIGH,
                )

        for app in git_config.approval_subcommands:
            if subcmd.startswith(app) or tool_name in ("git_reset", "git_clean"):
                return PolicyDecision(
                    action=PolicyAction.APPROVAL_REQUIRED,
                    reason=f"Potentially destructive Git operation '{subcmd or tool_name}' requires approval",
                    risk_level=RiskLevel.HIGH,
                    approval_required=True,
                )

        return PolicyDecision(
            action=PolicyAction.ALLOWED,
            reason=f"Git operation '{subcmd or tool_name}' is permitted",
            risk_level=RiskLevel.LOW,
        )
