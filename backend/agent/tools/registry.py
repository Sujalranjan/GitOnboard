"""
AgentToolRegistry: The authoritative agent-facing tool gateway for GitOnBoard.

Responsibilities:
  - Register and catalog approved tools.
  - Validate tool names and input arguments.
  - Enforce ToolPolicy (ALLOWED, BLOCKED, APPROVAL_REQUIRED).
  - Enforce execution timeouts.
  - Invoke underlying deterministic handlers.
  - Normalize all outputs into structured ToolResult envelopes.
"""
from __future__ import annotations

import concurrent.futures
import jsonschema
import logging
import time
from typing import Any, Dict, List, Optional

from backend.agent.tools.contracts import (
    AgentToolContext,
    ToolDefinition,
    ToolErrorCode,
    ToolResult,
)
from backend.agent.tools.policy import PolicyAction, ToolPolicy

logger = logging.getLogger(__name__)


class AgentToolRegistry:
    """
    Central tool registry and execution dispatcher for the Engineering Agent.
    """

    def __init__(self, policy: Optional[ToolPolicy] = None):
        self.policy = policy or ToolPolicy()
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        tool: ToolDefinition,
        default_policy: Optional[PolicyAction] = None,
    ) -> None:
        """Registers a tool definition. Raises ValueError on duplicate tool name."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered in AgentToolRegistry")
        if not tool.handler:
            raise ValueError(f"Tool '{tool.name}' must have an internal handler callable")

        self._tools[tool.name] = tool
        if default_policy is not None:
            self.policy.set_policy(tool.name, default_policy)
        elif tool.name not in self.policy._tool_policies:
            self.policy.set_policy(tool.name, PolicyAction.ALLOWED)

        logger.debug(f"Registered agent tool '{tool.name}' (category: {tool.category})")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Retrieves registered ToolDefinition by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        """Returns list of all registered ToolDefinition instances."""
        return list(self._tools.values())

    def list_catalog(self) -> List[Dict[str, Any]]:
        """Returns safe, serializable catalog of tool definitions with policy metadata."""
        return [
            t.to_catalog_item(policy_state=self.policy.get_policy(t.name).value)
            for t in self._tools.values()
        ]

    def validate_arguments(self, tool: ToolDefinition, arguments: Dict[str, Any]) -> Optional[str]:
        """Validates arguments against tool input_schema. Returns error string if invalid."""
        if not tool.input_schema:
            return None
        try:
            jsonschema.validate(instance=arguments, schema=tool.input_schema)
            return None
        except jsonschema.ValidationError as err:
            return f"Invalid argument '{err.json_path}': {err.message}"
        except Exception as err:
            return f"Argument validation error: {err}"

    def invoke(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: AgentToolContext,
    ) -> ToolResult:
        """
        Executes a registered tool under policy and timeout controls.
        Returns a normalized ToolResult envelope.
        """
        start_time = time.time()

        # 1. Tool existence check
        tool = self.get_tool(name)
        if not tool:
            duration_ms = (time.time() - start_time) * 1000
            return ToolResult.fail(
                code=ToolErrorCode.TOOL_NOT_FOUND,
                message=f"Tool '{name}' is not registered in AgentToolRegistry",
                tool_name=name,
                duration_ms=duration_ms,
            )

        # 2. Input argument schema validation
        val_error = self.validate_arguments(tool, arguments)
        if val_error:
            duration_ms = (time.time() - start_time) * 1000
            return ToolResult.fail(
                code=ToolErrorCode.INVALID_ARGUMENTS,
                message=val_error,
                tool_name=name,
                duration_ms=duration_ms,
            )

        # 3. Policy evaluation
        decision = self.policy.evaluate(name, context, arguments)

        # Critical Invariant: Under BLOCKED or APPROVAL_REQUIRED, handler NEVER runs!
        if decision.action == PolicyAction.BLOCKED:
            duration_ms = (time.time() - start_time) * 1000
            return ToolResult.fail(
                code=ToolErrorCode.POLICY_BLOCKED,
                message=decision.reason or f"Tool '{name}' is blocked by policy",
                tool_name=name,
                duration_ms=duration_ms,
            )
        elif decision.action == PolicyAction.APPROVAL_REQUIRED:
            duration_ms = (time.time() - start_time) * 1000
            return ToolResult.fail(
                code=ToolErrorCode.APPROVAL_REQUIRED,
                message=decision.reason or f"Tool '{name}' requires explicit user approval",
                tool_name=name,
                duration_ms=duration_ms,
                details={"arguments": arguments},
            )

        # 4. Timeout configuration (Policy-controlled upper bound)
        timeout_sec = tool.default_timeout_sec
        if decision.timeout_override_sec is not None:
            timeout_sec = min(tool.default_timeout_sec, decision.timeout_override_sec)

        # 5. Handler execution with timeout protection
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(tool.handler, arguments, context)
                result_data = future.result(timeout=timeout_sec)

            duration_ms = (time.time() - start_time) * 1000
            return ToolResult.ok(
                data=result_data,
                tool_name=name,
                duration_ms=duration_ms,
            )
        except concurrent.futures.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            logger.warning(f"Tool '{name}' timed out after {timeout_sec}s")
            return ToolResult.fail(
                code=ToolErrorCode.TIMEOUT,
                message=f"Tool '{name}' timed out after {timeout_sec} seconds",
                tool_name=name,
                duration_ms=duration_ms,
            )
        except Exception as err:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Tool '{name}' raised an exception during execution: {err}", exc_info=True)
            return ToolResult.fail(
                code=ToolErrorCode.EXECUTION_FAILED,
                message=f"Tool execution failed: {err}",
                tool_name=name,
                details={"exception_type": err.__class__.__name__},
                duration_ms=duration_ms,
            )
