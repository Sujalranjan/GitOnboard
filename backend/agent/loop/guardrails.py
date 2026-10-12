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


class AgentState:
    """
    Deterministic Agent State tracker maintaining structured execution facts.
    """
    def __init__(self):
        self.completed_tools: List[Dict[str, Any]] = []
        self.successful_evidence: List[Dict[str, Any]] = []
        self.failed_tools: List[Dict[str, Any]] = []
        self.duplicate_attempts: List[Dict[str, Any]] = []
        self.evidence_sufficient: bool = False
        self.answer_ready: bool = False
        # File read coverage tracking: canonical_path -> list of (start_line, end_line)
        self.file_read_ranges: Dict[str, List[Tuple[int, int]]] = {}
        # File total lines: canonical_path -> total_lines
        self.file_total_lines: Dict[str, int] = {}

    def _normalize_file_path(self, path: str) -> str:
        """Normalizes file path for canonical coverage matching."""
        if not path:
            return ""
        return path.replace("\\", "/").strip("/").lower()

    def record_read_range(self, path: str, start_line: int, end_line: int, total_lines: Optional[int] = None) -> None:
        """Records a successfully inspected line interval and updates file line totals."""
        clean_path = self._normalize_file_path(path)
        if not clean_path or start_line <= 0 or end_line < start_line:
            return

        if total_lines and total_lines > 0:
            self.file_total_lines[clean_path] = total_lines

        existing = self.file_read_ranges.get(clean_path, [])
        existing.append((start_line, end_line))
        # Merge overlapping / contiguous intervals
        existing.sort(key=lambda x: x[0])
        merged: List[Tuple[int, int]] = []
        for s, e in existing:
            if not merged:
                merged.append((s, e))
            else:
                last_s, last_e = merged[-1]
                # Contiguous or overlapping: [1, 25] and [26, 46] merge to [1, 46]
                if s <= last_e + 1:
                    merged[-1] = (last_s, max(last_e, e))
                else:
                    merged.append((s, e))
        self.file_read_ranges[clean_path] = merged

    def get_read_ranges_summary(self, path: str) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]], Optional[int]]:
        """
        Returns (read_intervals, unread_intervals, total_lines) for a given file path.
        """
        clean_path = self._normalize_file_path(path)
        reads = self.file_read_ranges.get(clean_path, [])
        total = self.file_total_lines.get(clean_path)

        if not reads:
            unreads = [(1, total)] if total and total > 0 else []
            return [], unreads, total

        if not total or total <= 0:
            # If total_lines is unknown, last read interval end defines current known boundary
            return reads, [], total

        # Compute gaps in [1, total]
        unreads: List[Tuple[int, int]] = []
        curr = 1
        for s, e in reads:
            if s > curr:
                unreads.append((curr, min(s - 1, total)))
            curr = max(curr, e + 1)
        if curr <= total:
            unreads.append((curr, total))

        return reads, unreads, total

    def get_unread_slice_for_request(self, path: str, req_start: int, req_end: int) -> Optional[Tuple[int, int]]:
        """
        Calculates the first unread interval within a requested [req_start, req_end] range.
        If the entire requested range is already covered, returns None.
        If partially covered, returns the adjusted (start_line, end_line) of the unread portion.
        """
        clean_path = self._normalize_file_path(path)
        reads = self.file_read_ranges.get(clean_path, [])
        if not reads:
            return (req_start, req_end)

        # Check if req_start is inside any read interval
        for s, e in reads:
            if s <= req_start <= e:
                # req_start is already read. Does the unread portion continue past e?
                if req_end > e:
                    return (e + 1, req_end)
                else:
                    # Entire requested range is inside this interval!
                    return None

        # Check if requested range completely encloses a read interval or starts before it
        for s, e in reads:
            if req_start < s:
                # Unread portion from req_start up to s - 1 (or req_end)
                return (req_start, min(req_end, s - 1))

        return (req_start, req_end)

    def record_tool_result(self, tool_name: str, arguments: Dict[str, Any], success: bool, data: Any = None, error: Any = None, turn_index: int = 0):
        entry = {
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
            "turn_index": turn_index,
        }
        self.completed_tools.append(entry)
        if success:
            if tool_name == "read_file" and isinstance(data, dict):
                p = data.get("path") or arguments.get("path")
                s = data.get("start_line") or arguments.get("start_line", 1)
                e = data.get("end_line") or arguments.get("end_line")
                tot = data.get("total_lines")
                if p and s is not None and e is not None:
                    try:
                        self.record_read_range(str(p), int(s), int(e), int(tot) if tot else None)
                    except (ValueError, TypeError):
                        pass

            evidence_summary = self._summarize_data(tool_name, data)
            self.successful_evidence.append({
                "tool_name": tool_name,
                "summary": evidence_summary,
                "turn_index": turn_index,
                "data": data,
            })
        else:
            self.failed_tools.append({
                "tool_name": tool_name,
                "error": error,
                "turn_index": turn_index,
            })

    def record_duplicate(self, tool_name: str, arguments: Dict[str, Any], turn_index: int):
        self.duplicate_attempts.append({
            "tool_name": tool_name,
            "arguments": arguments,
            "turn_index": turn_index,
        })

    def _summarize_data(self, tool_name: str, data: Any) -> str:
        if isinstance(data, dict):
            if data.get("found"):
                rel = data.get("related", [])
                target = data.get("target", {}).get("name", "")
                return f"Found {len(rel)} relationships for '{target}'"
            if data.get("path"):
                return f"Inspected file '{data.get('path')}' ({data.get('start_line', 1)}-{data.get('end_line', '?')})"
        elif isinstance(data, list):
            return f"Found {len(data)} results"
        return "Observed evidence"

    def get_compact_summary(self) -> str:
        """Generates a small, deterministic current-state summary for each turn."""
        lines = ["[AGENT CURRENT STATE]"]
        lines.append(f"- Completed tool steps: {len(self.completed_tools)}")
        if self.successful_evidence:
            ev_summaries = [f"{e['tool_name']}: {e['summary']}" for e in self.successful_evidence[-3:]]
            lines.append(f"- Key evidence: {'; '.join(ev_summaries)}")
        if self.failed_tools:
            lines.append(f"- Failed tools: {len(self.failed_tools)}")
        if self.duplicate_attempts:
            lines.append(f"- Duplicate calls blocked: {len(self.duplicate_attempts)}")
        status = "READY FOR FINAL ANSWER" if (self.evidence_sufficient or self.answer_ready) else "GATHERING EVIDENCE"
        lines.append(f"- Status: {status}")
        return "\n".join(lines)


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
        # Session-wide history tracking: sig -> dict with call count, last_success, last_data, error
        self.executed_tools: Dict[str, Dict[str, Any]] = {}
        # Deterministic Agent State tracker
        self.state = AgentState()

    @staticmethod
    def normalize_arguments(arguments: Any) -> str:
        """
        Recursively normalize arguments into a canonical JSON string
        independent of key ordering or dictionary implementation.
        """
        import json

        def _sort_obj(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: _sort_obj(v) for k, v in sorted(obj.items())}
            elif isinstance(obj, list):
                return [_sort_obj(item) for item in obj]
            return obj

        try:
            sorted_obj = _sort_obj(arguments)
            return json.dumps(sorted_obj, sort_keys=True, separators=(',', ':'), default=str)
        except Exception:
            return str(sorted(arguments.items())) if isinstance(arguments, dict) else str(arguments)

    def get_tool_signature(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Returns the canonical normalized signature for a tool invocation."""
        norm_args = self.normalize_arguments(arguments)
        return f"{tool_name}:{norm_args}"

    def is_duplicate_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        is_evidence_sufficient: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks if the tool call with identical normalized arguments has already been executed
        in the current QA session and returned a successful, non-empty result.

        State-aware recovery:
        - If evidence is sufficient -> instructs model to synthesize the final answer immediately.
        - If evidence is insufficient -> instructs model specifically on missing path / alternatives.

        Returns:
            Tuple[bool, Optional[str]]:
              - bool indicating if this call is an unnecessary duplicate.
              - reason/feedback string for the model if it is a duplicate.
        """
        sig = self.get_tool_signature(tool_name, arguments)
        # Overlap-aware check for read_file:
        # If the requested range has already been fully read (even if exact arguments differ, e.g. [1, 50] inside [1, 96]),
        # treat as duplicate request with full state feedback.
        if tool_name == "read_file" and isinstance(arguments, dict) and arguments.get("path"):
            path = str(arguments.get("path", ""))
            r_start = arguments.get("start_line")
            r_end = arguments.get("end_line")
            if r_start is not None and r_end is not None:
                try:
                    s_int = int(r_start)
                    e_int = int(r_end)
                    unread_slice = self.state.get_unread_slice_for_request(path, s_int, e_int)
                    if unread_slice is None:
                        # Entire range is already inspected!
                        self.state.record_duplicate(tool_name, arguments, self.turn_count)
                        reads, unreads, total = self.state.get_read_ranges_summary(path)
                        read_str = ", ".join(f"{s}-{e}" for s, e in reads) if reads else "none"
                        unread_str = ", ".join(f"{s}-{e}" for s, e in unreads) if unreads else "all inspected"
                        tot_str = f" of {total} lines" if total else ""

                        if is_evidence_sufficient or self.state.evidence_sufficient or self.state.answer_ready:
                            feedback = (
                                f"[DUPLICATE TOOL CALL] [DUPLICATE REQUEST - EVIDENCE SUFFICIENT] [EVIDENCE SUFFICIENT]\n"
                                f"This file/range has already been inspected.\n"
                                f"File: {path} (lines {read_str}{tot_str}).\n"
                                f"Sufficient evidence is already in your conversation history. "
                                f"Do not call any more tools. Provide your final answer immediately using: "
                                f'{{"action": "final_answer", "answer": "..."}}'
                            )
                        else:
                            feedback = (
                                f"[DUPLICATE TOOL CALL] [DUPLICATE REQUEST]\n"
                                f"This file/range has already been inspected.\n"
                                f"File: {path}\n"
                                f"- Already inspected: lines {read_str}\n"
                                f"- Still unread: lines {unread_str}\n"
                                f"Do not repeat identical calls. Continue investigation using the unread range or investigate another relevant file."
                            )
                        return True, feedback
                except (ValueError, TypeError):
                    pass

        record = self.executed_tools.get(sig)
        if not record:
            return False, None

        # Do not block if the previous call failed or had an execution error
        if not record.get("success", False):
            return False, None

        # Do not block if previous result was unavailable or empty/not found
        data = record.get("data")
        if data is None:
            return False, None
        if isinstance(data, (list, dict, str)) and len(data) == 0:
            return False, None

        first_turn = record.get("turn_index", "earlier")
        self.state.record_duplicate(tool_name, arguments, self.turn_count)

        if tool_name == "read_file" and isinstance(arguments, dict) and arguments.get("path"):
            path = arguments.get("path", "")
            reads, unreads, total = self.state.get_read_ranges_summary(path)
            read_str = ", ".join(f"{s}-{e}" for s, e in reads) if reads else "none"
            unread_str = ", ".join(f"{s}-{e}" for s, e in unreads) if unreads else "all inspected"
            tot_str = f" of {total} lines" if total else ""

            if is_evidence_sufficient or self.state.evidence_sufficient or self.state.answer_ready:
                feedback = (
                    f"[DUPLICATE TOOL CALL] [DUPLICATE REQUEST - EVIDENCE SUFFICIENT] [EVIDENCE SUFFICIENT]\n"
                    f"You already called 'read_file' with these exact arguments in Turn {first_turn}.\n"
                    f"Already inspected: {path} (lines {read_str}{tot_str}).\n"
                    f"Sufficient evidence is already in your conversation history. "
                    f"Do not call any more tools. Provide your final answer immediately using: "
                    f'{{"action": "final_answer", "answer": "..."}}'
                )
            else:
                feedback = (
                    f"[DUPLICATE TOOL CALL] [DUPLICATE REQUEST]\n"
                    f"You already called 'read_file' with these exact arguments in Turn {first_turn}.\n"
                    f"File: {path}\n"
                    f"- Already inspected: lines {read_str}\n"
                    f"- Still unread: lines {unread_str}\n"
                    f"Do not repeat identical calls. Continue investigation using the unread range or investigate another relevant file."
                )
            return True, feedback

        if is_evidence_sufficient or self.state.evidence_sufficient or self.state.answer_ready:
            feedback = (
                f"[DUPLICATE TOOL CALL - EVIDENCE SUFFICIENT] [EVIDENCE SUFFICIENT] You already called '{tool_name}' with these exact arguments in Turn {first_turn}, "
                f"and sufficient evidence to answer the question is already in your conversation history. "
                f"Do not call any more tools. Provide your final answer immediately using: "
                f'{{"action": "final_answer", "answer": "..."}}'
            )
        else:
            feedback = (
                f"[DUPLICATE TOOL CALL] You already called '{tool_name}' with these exact arguments in Turn {first_turn}, "
                f"and the result is already available in your conversation history. "
                f"Do not repeat identical calls. If you need implementation details, call read_file on the discovered file and line range; "
                f"if looking for another symbol, search a different term; otherwise synthesize your final answer."
            )
        return True, feedback

    def record_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        success: bool,
        data: Any = None,
        error: Any = None,
        turn_index: Optional[int] = None,
    ) -> None:
        """
        Records the outcome of a tool execution for session-wide duplicate detection.
        """
        sig = self.get_tool_signature(tool_name, arguments)
        turn_idx = turn_index if turn_index is not None else self.turn_count
        self.executed_tools[sig] = {
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
            "data": data,
            "error": error,
            "turn_index": turn_idx,
            "call_count": self.executed_tools.get(sig, {}).get("call_count", 0) + 1,
        }
        self.state.record_tool_result(
            tool_name=tool_name,
            arguments=arguments,
            success=success,
            data=data,
            error=error,
            turn_index=turn_idx,
        )

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
        sig = self.get_tool_signature(tool_name, arguments)
        self.recent_signatures.append(sig)

        logger.debug(f"LoopGuardrails: Tool call #{self.tool_call_count}: {tool_name} (recent signatures: {len(self.recent_signatures)})")

        # Check consecutive identical calls at the tail
        consecutive_count = 0
        for prior_sig in reversed(self.recent_signatures):
            if prior_sig == sig:
                consecutive_count += 1
            else:
                break

        if consecutive_count >= self.config.max_repeated_tool_calls:
            logger.warning(f"LoopGuardrails: Repeated tool call loop detected ({consecutive_count} consecutive identical calls for '{tool_name}'). Last 5 signatures: {self.recent_signatures[-5:]}")
            return StopReason.REPEATED_TOOL_CALL_LIMIT, False

        should_warn = (consecutive_count == self.config.max_repeated_tool_calls - 1)
        if should_warn:
            logger.warning(f"LoopGuardrails: Warning - approaching repeated call limit ({consecutive_count} consecutive for '{tool_name}')")
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
