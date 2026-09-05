"""
Agentic Q&A loop for RIM Comparison research — shared baseline/RIM infrastructure.

Single-turn-at-a-time loop: one LLM call → parse action → execute tool → repeat.
Enforces one tool call per turn (files fetched one-at-a-time), never pre-fetches.
Tracks tool calls, file reads, and RIM metadata access separately.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from backend.agent.loop.contracts import AgentLoopConfig, StopReason, ToolObservation
from backend.agent.loop.guardrails import LoopGuardrails
from backend.ai.service import LLMService
from backend.ai.schemas import LLMRequest, Message, MessageRole

if TYPE_CHECKING:
    from backend.logging.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)


@dataclass
class QALoopTurn:
    """Single turn in the loop: one LLM call + optional one tool call."""
    turn_index: int
    tool_call: Optional[Dict[str, Any]] = None  # {"tool_name": ..., "arguments": {...}}
    tool_observation: Optional[Dict[str, Any]] = None
    raw_model_output: str = ""
    prompt_tokens: int = 0  # real, from LLMResponse.usage
    completion_tokens: int = 0  # real, from LLMResponse.usage
    provider: str = ""
    model: str = ""
    duration_ms: float = 0.0


@dataclass
class QALoopResult:
    """Final result from one side of the RIM comparison."""
    answer: str
    stop_reason: StopReason
    turns: List[QALoopTurn] = field(default_factory=list)
    tool_call_count: int = 0
    files_read: List[str] = field(default_factory=list)
    symbols_read: List[str] = field(default_factory=list)
    files_searched: List[str] = field(default_factory=list)  # from search_code/search_repository
    symbols_searched: List[str] = field(default_factory=list)  # from search_repository
    rim_entities_accessed: List[Dict[str, Any]] = field(default_factory=list)  # from query_rim only
    rim_relationship_types_used: List[str] = field(default_factory=list)  # from query_rim only
    latency_ms: Dict[str, float] = field(default_factory=dict)  # {"loop_total", "llm_total", "tool_total"}


@dataclass
class SystemPromptParts:
    """Decomposed system prompt for token accounting."""
    grounding_and_protocol_text: str  # static grounding + protocol instructions
    tool_catalog_text: str  # tool schemas
    rim_metadata_text: str  # RIM metadata block (empty string for baseline)
    full_text: str  # concatenation sent to LLM


class RIMQALoop:
    """
    Agentic Q&A loop: LLM decides what tools to call, executes them one-at-a-time,
    builds answer incrementally. No code-editing semantics, pure question-answering.
    """

    def __init__(
        self,
        llm_service: LLMService,
        tool_dispatch: "ToolDispatchTable",
        config: AgentLoopConfig,
        system_prompt_parts: SystemPromptParts,
        model: Optional[str] = None,
        structured_logger: Optional["StructuredLogger"] = None,
        request_id: Optional[str] = None,
        repository: Optional[str] = None,
        mode: Optional[str] = None,  # "baseline" or "rim"
    ):
        self.llm_service = llm_service
        self.tool_dispatch = tool_dispatch
        self.config = config
        self.system_prompt_parts = system_prompt_parts
        self.model = model
        self.guardrails = LoopGuardrails(config)
        self.structured_logger = structured_logger
        self.request_id = request_id
        self.repository = repository
        self.mode = mode

    async def run(self, question: str) -> QALoopResult:
        """
        Run the agentic loop: question → LLM → tool dispatch → repeat until done.

        Returns QALoopResult with answer, all turns, metrics, and stop reason.
        """
        loop_start = time.perf_counter()
        llm_total_ms = 0.0
        tool_total_ms = 0.0

        result = QALoopResult(
            answer="",
            stop_reason=StopReason.EXECUTION_TIMEOUT,  # default, overridden below
        )

        # Conversation history: messages appended per turn
        messages: List[Dict[str, Any]] = []

        # Turn 0: add user question
        messages.append({
            "role": "user",
            "content": question,
        })

        while True:
            turn_index = len(result.turns)
            self.guardrails.record_turn()

            # 1. Check guardrails BEFORE turn
            stop_reason = self.guardrails.check_pre_turn_limits()
            if stop_reason:
                logger.info(f"[RIMQALoop] Guardrail limit hit: {stop_reason}; forcing final answer")
                result.stop_reason = stop_reason
                # Force a final-answer turn: send current conversation + instruction to answer now
                messages.append({
                    "role": "user",
                    "content": f"[LIMIT REACHED: {stop_reason.value}] You have reached execution limits. Provide your best answer based on what you have gathered so far.",
                })
                # Do one final LLM call (no tools allowed)
                turn = await self._do_final_answer_turn(
                    turn_index, messages, llm_total_ms, tool_total_ms, loop_start
                )
                result.turns.append(turn)
                result.answer = turn.raw_model_output
                break

            # 2. Call LLM with current conversation
            logger.debug(f"[RIMQALoop] Turn {turn_index}: calling LLM...")
            turn_start = time.perf_counter()

            try:
                # Build LLMRequest with system prompt as first message
                llm_messages = [
                    Message(role=MessageRole.SYSTEM, content=self.system_prompt_parts.full_text),
                ]
                for msg in messages:
                    try:
                        role_str = msg.get("role", "user").lower() if isinstance(msg, dict) else "user"
                        role = MessageRole(role_str) if role_str in ["system", "user", "assistant", "tool"] else MessageRole.USER
                        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                        llm_messages.append(Message(role=role, content=content))
                    except Exception as msg_err:
                        logger.error(f"[RIMQALoop] Error processing message: {msg_err}, msg type: {type(msg)}")
                        raise

                logger.debug(f"[RIMQALoop] Turn {turn_index}: Built {len(llm_messages)} messages (system + {len(messages)} conversation)")
                request = LLMRequest(
                    messages=llm_messages,
                    model=self.model,
                    temperature=0.2,
                    max_tokens=4096,
                )
                llm_response = await self.llm_service.generate(request)
                logger.debug(f"[RIMQALoop] Turn {turn_index}: LLM response ({len(llm_response.content)} chars)")
            except Exception as e:
                logger.error(f"[RIMQALoop] LLM call failed: {e}", exc_info=True)
                result.stop_reason = StopReason.MODEL_ERROR
                result.answer = f"[ERROR] LLM call failed: {str(e)}"

                # Log error if structured logger is available
                if self.structured_logger and self.request_id:
                    self.structured_logger.log_error(
                        stage=f"llm_call_turn_{turn_index}",
                        error=e,
                        context={"mode": self.mode, "turn": turn_index}
                    )
                break

            turn_elapsed = time.perf_counter() - turn_start
            llm_total_ms += turn_elapsed * 1000

            # Log LLM request and response if structured logger is available (after calculating latency)
            if self.structured_logger and self.request_id:
                is_rim = self.mode == "rim"
                user_message = messages[-1].get("content", "") if messages else ""
                tool_specs = self.tool_dispatch.specs(include_rim=is_rim)
                tools_available = [spec.name for spec in tool_specs] if hasattr(tool_specs, '__iter__') else []
                self.structured_logger.log_llm_request(
                    model=self.model or llm_response.model,
                    provider=llm_response.provider,
                    is_rim=is_rim,
                    system_prompt=self.system_prompt_parts.full_text,  # Log full system prompt
                    user_message=user_message,
                    tools_available=tools_available,
                    context_tokens=len(self.system_prompt_parts.full_text) + sum(len(m.get("content", "")) for m in messages)
                )
                self.structured_logger.log_llm_response(
                    response_text=llm_response.content,
                    stop_reason="end_turn",  # LLMResponse doesn't include stop_reason
                    prompt_tokens=llm_response.usage.prompt_tokens,
                    completion_tokens=llm_response.usage.completion_tokens,
                    latency_ms=turn_elapsed * 1000,
                    model=llm_response.model,
                    is_rim=is_rim
                )

            # 3. Parse response: tool_call | final_answer | malformed
            parsed = self._parse_response(llm_response.content)

            # Log all details to debug for troubleshooting
            if parsed["action"] == "tool_call":
                logger.debug(f"[RIMQALoop] Turn {turn_index}: tool={parsed.get('tool_name')}")
            elif parsed["action"] == "final_answer":
                logger.debug(f"[RIMQALoop] Turn {turn_index}: FINAL_ANSWER")
            else:
                logger.debug(f"[RIMQALoop] Turn {turn_index}: MALFORMED - {parsed.get('error')} | {llm_response.content[:100]}...")

            turn = QALoopTurn(
                turn_index=turn_index,
                raw_model_output=llm_response.content,
                prompt_tokens=llm_response.usage.prompt_tokens,
                completion_tokens=llm_response.usage.completion_tokens,
                provider=llm_response.provider,
                model=llm_response.model,
                duration_ms=turn_elapsed * 1000,
            )

            # 4. Handle action: tool_call | final_answer | malformed
            if parsed["action"] == "final_answer":
                answer_candidate = parsed.get("answer", llm_response.content)

                # PHASE 8A VERIFICATION GATE: Enforce retrieval for absence claims
                if not self._verify_absence_claim(answer_candidate, result):
                    # Gate violation: absence claim without retrieval
                    # Force a retrieval attempt
                    logger.info(f"[VerificationGate] Absence claim rejected; forcing retrieval")
                    messages.append({
                        "role": "assistant",
                        "content": llm_response.content,
                    })
                    messages.append({
                        "role": "user",
                        "content": "[VERIFICATION REQUIRED] You have claimed repository-wide absence without performing a search. You must search the repository or inspect relevant files before making absence claims. Please perform a search or file inspection to verify your claim.",
                    })
                    result.turns.append(turn)
                    # Continue loop to force retrieval
                    continue

                result.answer = answer_candidate
                result.stop_reason = StopReason.COMPLETED_FOR_VERIFICATION
                result.turns.append(turn)
                logger.info(f"[RIMQALoop] LLM provided final answer at turn {turn_index}")
                break

            elif parsed["action"] == "tool_call":
                tool_name = parsed.get("tool_name", "")
                arguments = parsed.get("arguments", {})

                # 5. Check guardrails on tool call
                stop_reason, should_warn = self.guardrails.record_tool_call(tool_name, arguments)
                if stop_reason:
                    logger.warning(f"[RIMQALoop] Tool call limit hit: {stop_reason}")
                    result.stop_reason = stop_reason
                    # Force final answer
                    messages.append({
                        "role": "assistant",
                        "content": llm_response.content,
                    })
                    messages.append({
                        "role": "user",
                        "content": f"[TOOL LIMIT REACHED] You have reached tool-call limits. Provide your best answer based on what you have gathered.",
                    })
                    final_turn = await self._do_final_answer_turn(
                        turn_index + 1, messages, llm_total_ms, tool_total_ms, loop_start
                    )
                    result.turns.append(turn)
                    result.turns.append(final_turn)
                    result.answer = final_turn.raw_model_output
                    break

                # 6. Execute tool
                logger.debug(f"[RIMQALoop] Turn {turn_index}: executing tool '{tool_name}'")
                tool_start = time.perf_counter()

                try:
                    tool_observation = self.tool_dispatch.dispatch(tool_name, arguments)
                except Exception as e:
                    logger.error(f"[RIMQALoop] Tool dispatch error: {e}", exc_info=True)
                    tool_observation = ToolObservation(
                        tool_call_id=f"turn-{turn_index}",
                        tool_name=tool_name,
                        success=False,
                        error={"type": "dispatch_error", "message": str(e)},
                    )

                tool_elapsed = time.perf_counter() - tool_start
                tool_total_ms += tool_elapsed * 1000

                # Log tool call if structured logger is available
                if self.structured_logger and self.request_id:
                    is_rim = self.mode == "rim"
                    self.structured_logger.log_tool_call(
                        tool_name=tool_name,
                        arguments=arguments,
                        is_rim=is_rim,
                        turn_number=turn_index,
                        execution_time_ms=tool_elapsed * 1000,
                        success=tool_observation.success,
                        result=tool_observation.data if tool_observation.success else None,
                        error=tool_observation.error.get("message") if tool_observation.error else None
                    )

                # 7. Sanitize observation to prevent context explosion
                sanitized_data = self.guardrails.sanitize_observation(tool_observation.data)

                # Track metadata from tools
                if tool_name == "read_file" and tool_observation.success:
                    path = arguments.get("path", "")
                    if path and path not in result.files_read:
                        result.files_read.append(path)
                elif tool_name == "get_symbol" and tool_observation.success:
                    name = arguments.get("name", "")
                    if name and name not in result.symbols_read:
                        result.symbols_read.append(name)
                elif tool_name == "search_code" and tool_observation.success:
                    # Track files found by search_code
                    data = tool_observation.data or []
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "file" in item:
                                file_path = item["file"]
                                if file_path and file_path not in result.files_searched:
                                    result.files_searched.append(file_path)
                elif tool_name == "search_repository" and tool_observation.success:
                    # Track files and symbols found by search_repository
                    data = tool_observation.data or []
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                if "file_path" in item:
                                    file_path = item["file_path"]
                                    if file_path and file_path not in result.files_searched:
                                        result.files_searched.append(file_path)
                                if "symbol_name" in item:
                                    symbol_name = item["symbol_name"]
                                    if symbol_name and symbol_name not in result.symbols_searched:
                                        result.symbols_searched.append(symbol_name)
                elif tool_name == "query_rim" and tool_observation.success:
                    # Track RIM access from query_rim tool
                    data = tool_observation.data or {}
                    if data.get("found"):
                        entity_name = arguments.get("entity_name", "")
                        rel_type = arguments.get("relationship_type", "GENERIC")
                        result.rim_entities_accessed.append({
                            "entity_name": entity_name,
                            "relationship_type": rel_type,
                            "direction": arguments.get("direction", "FORWARD"),
                            "related_count": len(data.get("related", [])),
                        })
                        if rel_type not in result.rim_relationship_types_used:
                            result.rim_relationship_types_used.append(rel_type)

                # 8. Append LLM response + tool observation to conversation
                messages.append({
                    "role": "assistant",
                    "content": llm_response.content,
                })
                messages.append({
                    "role": "user",
                    "content": self._format_tool_observation(tool_name, tool_observation, sanitized_data),
                })

                # Record turn with tool info (include data and formatted message for later reconstruction)
                formatted_message = self._format_tool_observation(tool_name, tool_observation, sanitized_data)
                turn.tool_call = {"tool_name": tool_name, "arguments": arguments}
                turn.tool_observation = {
                    "tool_name": tool_name,
                    "success": tool_observation.success,
                    "error": tool_observation.error,
                    "data": sanitized_data,  # Include actual result data for metrics/reconstruction
                    "formatted_message": formatted_message,  # Include formatted message for audit trail
                }
                result.turns.append(turn)
                result.tool_call_count += 1
                logger.debug(f"[RIMQALoop] Turn {turn_index}: {tool_name} executed in {tool_elapsed*1000:.0f}ms")

            else:  # malformed
                logger.warning(f"[RIMQALoop] Malformed response: {parsed.get('error', 'unknown')}")
                # Append response and ask LLM to clarify
                messages.append({
                    "role": "assistant",
                    "content": llm_response.content,
                })
                messages.append({
                    "role": "user",
                    "content": "[MALFORMED RESPONSE] Please respond with valid JSON: either {\"action\": \"tool_call\", \"tool_name\": \"...\", \"arguments\": {...}} or {\"action\": \"final_answer\", \"answer\": \"...\"}",
                })
                result.turns.append(turn)

        # Calculate latencies
        loop_elapsed = time.perf_counter() - loop_start
        result.latency_ms = {
            "loop_total": loop_elapsed * 1000,
            "llm_total": llm_total_ms,
            "tool_total": tool_total_ms,
        }

        # Log completion - show critical summary
        log_message = (f"[RIMQALoop] Completed {len(result.turns)} turns | "
                      f"{result.tool_call_count} tool calls | "
                      f"{result.stop_reason}")

        if result.tool_call_count == 0:
            logger.error(f"{log_message} | ❌ ERROR: No tools called - malformed JSON or protocol failure")
        else:
            logger.info(log_message)

        return result

    async def _do_final_answer_turn(
        self, turn_index: int, messages: List[Dict[str, Any]],
        llm_total_ms: float, tool_total_ms: float, loop_start: float
    ) -> QALoopTurn:
        """Execute one final LLM call (no tools) to generate answer."""
        turn_start = time.perf_counter()

        try:
            # Build LLMRequest with system prompt as first message
            llm_messages = [
                Message(role=MessageRole.SYSTEM, content=self.system_prompt_parts.full_text),
            ]
            for msg in messages:
                try:
                    role_str = msg.get("role", "user").lower() if isinstance(msg, dict) else "user"
                    role = MessageRole(role_str) if role_str in ["system", "user", "assistant", "tool"] else MessageRole.USER
                    content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                    llm_messages.append(Message(role=role, content=content))
                except Exception as msg_err:
                    logger.error(f"[RIMQALoop] Error processing message in final answer turn: {msg_err}")
                    raise

            request = LLMRequest(
                messages=llm_messages,
                model=self.model,
                temperature=0.2,
                max_tokens=4096,
            )
            llm_response = await self.llm_service.generate(request)
        except Exception as e:
            logger.error(f"[RIMQALoop] Final answer LLM call failed: {e}", exc_info=True)
            return QALoopTurn(
                turn_index=turn_index,
                raw_model_output=f"[ERROR] Failed to generate answer: {str(e)}",
                prompt_tokens=0,
                completion_tokens=0,
                provider="error",
                model="error",
                duration_ms=(time.perf_counter() - turn_start) * 1000,
            )

        return QALoopTurn(
            turn_index=turn_index,
            raw_model_output=llm_response.content,
            prompt_tokens=llm_response.usage.prompt_tokens,
            completion_tokens=llm_response.usage.completion_tokens,
            provider=llm_response.provider,
            model=llm_response.model,
            duration_ms=(time.perf_counter() - turn_start) * 1000,
        )

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """
        Parse LLM response for tool_call | final_answer | malformed.

        Returns {"action": "tool_call"|"final_answer"|"malformed", ...}
        """
        import json
        import re

        # Try to extract JSON object from response.
        # Search for '{' and attempt to parse from each position until successful.
        # This handles nested JSON (e.g., arguments with nested dicts).
        obj = None
        for match in re.finditer(r'\{', text):
            start_pos = match.start()
            # Find the matching closing brace by counting braces
            brace_count = 0
            end_pos = start_pos
            for i in range(start_pos, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break

            if brace_count == 0:  # Found matching close brace
                try:
                    # Try to parse just this JSON object
                    json_str = text[start_pos:end_pos]
                    obj = json.loads(json_str)
                    if isinstance(obj, dict):
                        # Successfully parsed a JSON object
                        # Verify it has the expected structure
                        action = obj.get("action", "").lower()
                        if action in ["tool_call", "final_answer"]:
                            # This is a valid action object
                            break
                except json.JSONDecodeError:
                    # This position didn't yield valid JSON, try next {
                    obj = None
                    continue

        if obj is None:
            # No valid JSON action object found
            return {"action": "malformed", "error": "no valid JSON action object found"}

        action = obj.get("action", "").lower()

        if action == "tool_call":
            return {
                "action": "tool_call",
                "tool_name": obj.get("tool_name", ""),
                "arguments": obj.get("arguments", {}),
            }
        elif action == "final_answer":
            return {
                "action": "final_answer",
                "answer": obj.get("answer", text),
            }
        else:
            return {"action": "malformed", "error": f"unknown action: {action}"}

    def _has_retrieval_been_performed(self, result: QALoopResult) -> bool:
        """
        Check if any repository retrieval has been performed in this execution.

        Verification-gate enforcement: absence claims require actual retrieval evidence.

        Returns True if: search_repository, read_file, or get_symbol was called and succeeded.
        """
        retrieval_tools = ["search_repository", "read_file", "get_symbol", "search_code"]

        for turn in result.turns:
            if turn.tool_call:
                tool_name = turn.tool_call.get("tool_name", "")
                if tool_name in retrieval_tools:
                    # Check if tool call succeeded
                    if turn.tool_observation and turn.tool_observation.get("success", False):
                        return True

        return False

    def _retrieval_evidence_supports_absence(self, result: QALoopResult) -> bool:
        """
        Check if the actual retrieval result data supports an absence claim.

        An absence claim is supported by retrieval evidence only if:
        - Retrieval tools were executed
        - AND all retrieval results were empty/not-found
        - AND no positive evidence of the claimed absence entity was discovered

        Returns True if absence is justified by the retrieval evidence.
        Returns False if retrieval found relevant results (contradicting absence).
        """
        retrieval_tools = ["search_repository", "read_file", "get_symbol", "search_code"]
        found_any_relevant_result = False
        checked_any_retrieval = False

        for turn in result.turns:
            if not turn.tool_call or not turn.tool_observation:
                continue

            tool_name = turn.tool_call.get("tool_name", "")
            if tool_name not in retrieval_tools:
                continue

            # Check if retrieval succeeded
            if not turn.tool_observation.get("success", False):
                # Failed retrieval doesn't prove absence
                continue

            checked_any_retrieval = True
            result_data = turn.tool_observation.get("data", None)

            # Analyze result based on tool type
            if tool_name == "search_repository":
                # search_repository returns list of matches
                if isinstance(result_data, list) and len(result_data) > 0:
                    # Found relevant results - contradicts absence
                    found_any_relevant_result = True
                    break

            elif tool_name == "search_code":
                # search_code returns list of matches
                if isinstance(result_data, list) and len(result_data) > 0:
                    found_any_relevant_result = True
                    break

            elif tool_name == "get_symbol":
                # get_symbol returns symbol data or None
                if result_data is not None and result_data:
                    # Symbol found - contradicts absence
                    found_any_relevant_result = True
                    break

            elif tool_name == "read_file":
                # read_file returns file content or None
                if result_data is not None and result_data:
                    # File found - contradicts absence
                    found_any_relevant_result = True
                    break

        # Evidence supports absence only if:
        # 1. We actually performed retrieval
        # 2. We found no relevant results
        if checked_any_retrieval and not found_any_relevant_result:
            return True

        # If no retrieval was performed, or retrieval found results
        return False

    def _is_absence_claim(self, answer: str) -> bool:
        """
        Improved heuristic: detect if answer claims repository-wide absence.

        Handles multiple formulations:
        - Direct negation: "does not X", "there is no X"
        - Soft negation: "doesn't appear", "seems not to"
        - Search-qualified: "found no X", "no results"
        - Question-response: "Is there X?" answered with "No"
        """
        answer_lower = answer.lower()

        # Direct negation patterns (primary)
        direct_negation = [
            "does not",
            "doesn't",
            "do not",
            "don't",
            "is not",
            "isn't",
            "was not",
            "wasn't",
            "are not",
            "aren't",
            "no function",
            "no module",
            "no package",
            "no component",
            "no service",
            "no feature",
            "no implementation",
            "no code",
            "there is no",
            "there are no",
            "there's no",
        ]

        # Soft/qualified negation (secondary)
        soft_negation = [
            "does not appear",
            "doesn't appear",
            "appears not",
            "appears to not",
            "doesn't seem",
            "does not seem",
            "seems not",
            "unable to find",
            "cannot find",
            "could not find",
            "couldn't find",
            "found no",
            "no evidence",
            "no mention",
            "no instances",
            "no references",
            "not found",
            "not present",
            "not implemented",
            "not detected",
            "no results",
        ]

        # Entity context (broadened)
        entity_context = [
            "function",
            "module",
            "package",
            "library",
            "component",
            "service",
            "feature",
            "class",
            "interface",
            "method",
            "implementation",
            "pattern",
            "dependency",
            "tool",
            "framework",
            "redis",
            "database",
            "cache",
            "authentication",
            "reset",
            "recovery",
        ]

        repo_context = [
            "repository",
            "codebase",
            "project",
            "code",
            "repo",
            "repository",
            "this repo",
            "this project",
        ]

        # Strategy: Detect absence if:
        # 1. Direct negation is present
        # 2. OR soft negation + entity/repo context
        # This catches most natural absence formulations

        has_direct = any(p in answer_lower for p in direct_negation)

        has_soft = any(p in answer_lower for p in soft_negation)
        has_context = (
            any(e in answer_lower for e in entity_context) or
            any(r in answer_lower for r in repo_context)
        )

        # Direct negation alone is usually sufficient
        # OR soft negation WITH entity/repo context
        return has_direct or (has_soft and has_context)

    def _verify_absence_claim(self, answer: str, result: QALoopResult) -> bool:
        """
        Enforcement gate: absence claims must be backed by actual retrieval evidence.

        Returns True if:
        - Answer does NOT claim absence, OR
        - Answer claims absence AND retrieval result data genuinely supports it

        Returns False if:
        - Answer claims absence but retrieval found contradicting evidence, OR
        - Answer claims absence but no retrieval was performed, OR
        - Answer claims absence but retrieval result data contradicts the claim
        """
        if not self._is_absence_claim(answer):
            # Not an absence claim, pass through
            return True

        # This is an absence claim; validate with retrieval evidence
        if self._retrieval_evidence_supports_absence(result):
            # Absence claim is backed by actual retrieval evidence (results were empty)
            return True

        # Absence claim NOT supported by evidence
        logger.warning(f"[VerificationGate] Absence claim without supporting retrieval evidence: {answer[:100]}...")
        return False

    def _format_tool_observation(
        self, tool_name: str, observation: ToolObservation, data: Any
    ) -> str:
        """Format tool observation for appending to conversation.

        Includes both summary and actual data so LLM can reason over results.
        """
        if not observation.success:
            error = observation.error or {}
            return f"[TOOL ERROR] {tool_name}: {error.get('message', 'unknown error')}"

        # Format with summary + actual data so LLM can use the results
        if tool_name == "read_file" and isinstance(data, dict):
            path = data.get('path', '')
            start_line = data.get('start_line', 1)
            end_line = data.get('end_line', 0)
            content = data.get('content', '')
            summary = f"[read_file] {path} lines {start_line}-{end_line}: {len(content)} chars\n"
            # Include actual file content so LLM can reason over code
            if content:
                return summary + content
            return summary
        elif tool_name == "query_rim" and isinstance(data, dict):
            if not data.get("found"):
                return f"[query_rim] Entity not found: {data.get('message', '')}"
            related = data.get("related", [])
            summary = f"[query_rim] Found {len(related)} related entities:\n"
            # Include actual entity details so LLM understands relationships
            for entity in related:
                name = entity.get("name", "?")
                entity_type = entity.get("entity_type", "?")
                location = entity.get("location", "?")
                line_num = entity.get("line_number", "?")
                role = entity.get("relationship_role", "?")
                summary += f"  - {name} ({entity_type}, {location}:{line_num}, role: {role})\n"
            return summary
        elif tool_name == "search_repository" and isinstance(data, list):
            summary = f"[search_repository] Found {len(data)} results:\n"
            for result in data[:10]:  # Include first 10 results
                if isinstance(result, dict):
                    file_path = result.get("file", result.get("path", "?"))
                    result_type = result.get("type", "")
                    # For symbol/code results, include additional context
                    if result_type == "symbol" and "symbol" in result:
                        summary += f"  - {file_path}: {result['symbol']} (lines {result.get('lines', '?')})\n"
                    elif result_type == "code" and "line" in result:
                        snippet = result.get("snippet", "")[:50]
                        summary += f"  - {file_path}:{result['line']} {snippet}\n"
                    else:
                        summary += f"  - {file_path}\n"
                else:
                    summary += f"  - {str(result)[:50]}\n"
            if len(data) > 10:
                summary += f"  ... and {len(data) - 10} more results\n"
            return summary
        elif tool_name == "get_symbol" and isinstance(data, list):
            summary = f"[get_symbol] Found {len(data)} symbols:\n"
            for symbol in data[:10]:  # Include first 10 symbols
                name = symbol.get("name", "?") if isinstance(symbol, dict) else str(symbol)[:50]
                summary += f"  - {name}\n"
            if len(data) > 10:
                summary += f"  ... and {len(data) - 10} more symbols\n"
            return summary
        else:
            # Generic summary with actual data included
            import json
            try:
                if isinstance(data, (dict, list)):
                    data_str = json.dumps(data, default=str)[:500]
                else:
                    data_str = str(data)[:500]
            except:
                data_str = str(data)[:500]
            return f"[{tool_name}] Result: {data_str}"
