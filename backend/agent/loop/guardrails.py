"""
Phase 6 Guardrails & Execution Limits for Engineering Agent Loop.

Enforces:
  - Max agent turns
  - Max total tool calls
  - Max command/terminal executions
  - Overall task execution timeout
  - Observation payload truncation
  - Repeated tool call loop detection via normalized signature hashing
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.agent.loop.contracts import AgentLoopConfig, StopReason

logger = logging.getLogger(__name__)

# Known terminal / command execution tools
COMMAND_TOOL_NAMES = {
    "execute_command",
    "sandbox_bash",
    "run_terminal_command",
    "run_tests",
    "run_build",
}


class LoopGuardrails:
    """
    Stateful execution monitor enforcing hard safety limits and loop detection.
    """

    def __init__(self, config: Optional[AgentLoopConfig] = None):
        self.config = config or AgentLoopConfig()
        self.turn_count = 0
        self.tool_call_count = 0
        self.command_count = 0
        self.start_time = time.perf_counter()
        self.recent_signatures: List[str] = []

    def record_turn(self) -> None:
        """Records the progression of an agent turn."""
        self.turn_count += 1

    def check_pre_turn_limits(self) -> Optional[StopReason]:
        """Checks turn and execution time limits before starting an agent turn."""
        elapsed = time.perf_counter() - self.start_time
        if elapsed >= self.config.max_execution_seconds:
            logger.warning(f"LoopGuardrails: Task timeout exceeded ({elapsed:.1f}s >= {self.config.max_execution_seconds}s)")
            return StopReason.EXECUTION_TIMEOUT

        if self.turn_count >= self.config.max_agent_turns:
            logger.warning(f"LoopGuardrails: Max turns exceeded ({self.turn_count} >= {self.config.max_agent_turns})")
            return StopReason.MAX_TURNS_EXCEEDED

        return None

    def record_tool_call(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Tuple[Optional[StopReason], bool]:
        """
        Records a tool invocation, validates execution caps, and inspects for repetition loops.
        
        Returns:
            Tuple[Optional[StopReason], bool]:
              - StopReason if a hard cap or repetition limit was violated (or None)
              - bool indicating if a repetition warning should be emitted to the model
        """
        self.tool_call_count += 1

        if self.tool_call_count > self.config.max_tool_calls:
            logger.warning(f"LoopGuardrails: Max tool calls exceeded ({self.tool_call_count} > {self.config.max_tool_calls})")
            return StopReason.MAX_TOOL_CALLS_EXCEEDED, False

        # Command-specific rate limiting
        if tool_name in COMMAND_TOOL_NAMES:
            self.command_count += 1
            if self.command_count > self.config.max_command_executions:
                logger.warning(f"LoopGuardrails: Max command executions exceeded ({self.command_count} > {self.config.max_command_executions})")
                return StopReason.MAX_COMMANDS_EXCEEDED, False

        # Normalized signature hashing
        try:
            sorted_args = json.dumps(arguments, sort_keys=True, default=str)
        except Exception:
            sorted_args = str(sorted(arguments.items()))

        sig = f"{tool_name}:{sorted_args}"
        self.recent_signatures.append(sig)

        # Check consecutive identical calls at the tail
        consecutive_count = 0
        for prior_sig in reversed(self.recent_signatures):
            if prior_sig == sig:
                consecutive_count += 1
            else:
                break

        if consecutive_count >= self.config.max_repeated_tool_calls:
            logger.warning(f"LoopGuardrails: Repeated tool call loop detected ({consecutive_count} consecutive identical calls for '{tool_name}')")
            return StopReason.REPEATED_TOOL_CALL_LIMIT, False

        should_warn = (consecutive_count == self.config.max_repeated_tool_calls - 1)
        return None, should_warn

    def sanitize_observation(self, data: Any) -> Any:
        """
        Truncates observation payloads exceeding max_observation_bytes to prevent token context blowup.
        """
        if data is None:
            return None

        max_bytes = self.config.max_observation_bytes

        if isinstance(data, str):
            if len(data.encode("utf-8", errors="ignore")) > max_bytes:
                truncated_text = data[: max_bytes // 2]
                return (
                    f"{truncated_text}\n\n"
                    f"... [OBSERVATION TRUNCATED: Original size exceeded {max_bytes} bytes limit. "
                    f"Please refine query or read specific ranges.]"
                )
            return data

        try:
            serialized = json.dumps(data, default=str)
            if len(serialized.encode("utf-8", errors="ignore")) > max_bytes:
                return {
                    "_truncated": True,
                    "preview": serialized[: max_bytes // 2],
                    "warning": f"Observation exceeded max byte size ({max_bytes} bytes).",
                }
        except Exception:
            pass

        return data
