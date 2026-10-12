"""
Agentic Q&A loop — shared canonical tool-calling infrastructure for all agents.

Single-turn-at-a-time loop: one LLM call → parse action → execute tool → repeat.
Enforces one tool call per turn (files fetched one-at-a-time), never pre-fetches.
Tracks tool calls, file reads, and RIM metadata access separately.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from backend.agent.loop.contracts import AgentLoopConfig, StopReason, ToolObservation
from backend.agent.loop.guardrails import LoopGuardrails
from backend.ai.service import LLMService
from backend.ai.schemas import LLMRequest, Message, MessageRole, Tool
from backend.ai.tokencount.registry import count_full_request
from backend.config import settings
from backend.agent.intent.semantic_query import (
    classify_semantic_query,
    SemanticQueryClass,
    TraversalDirection,
)
from backend.services.qa_budgeting import (
    compact_messages_deterministically,
    derive_provider_budget_profile,
    extract_read_file_metadata,
)
from backend.services.qa_formatters import format_tool_observation
from backend.services.qa_protocol import QAProtocolAdapter
from backend.services.qa_validation import (
    check_evidence_sufficiency,
    has_retrieval_been_performed,
    identify_missing_evidence,
    is_absence_claim,
    retrieval_evidence_supports_absence,
    validate_final_answer_against_evidence,
)

if TYPE_CHECKING:
    from backend.logging.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)


def strip_xml_tags(text: str) -> str:
    """Remove XML tags from text, keeping only markdown content."""
    # Remove <tool_call>...</tool_call> wrapper
    text = re.sub(r'<tool_call>|</tool_call>', '', text, flags=re.DOTALL)
    # Remove <invoke name="...">...</invoke> wrapper
    text = re.sub(r'<invoke[^>]*>|</invoke>', '', text, flags=re.DOTALL)
    # Remove <parameter name="...">...</parameter> tags
    text = re.sub(r'<parameter[^>]*>|</parameter>', '', text, flags=re.DOTALL)
    # Fix numbering format: join number on same line as content (e.g., "1.\nText" → "1. Text")
    text = re.sub(r'^(\d+\.)\s*\n\s*', r'\1 ', text, flags=re.MULTILINE)
    # Clean up extra whitespace and normalize paragraph breaks
    text = re.sub(r'\n\s*\n', '\n\n', text).strip()
    return text


def extract_json_answer(text: str) -> str:
    """Extract answer text from JSON-wrapped response."""
    import json

    # Try to parse as JSON and extract answer field
    try:
        # Handle case where response starts with {"action": "final_answer", "answer": "..."}
        data = json.loads(text)
        if isinstance(data, dict) and "answer" in data:
            return str(data["answer"]).strip()
    except (json.JSONDecodeError, ValueError):
        # Not JSON, return as-is
        pass

    return text.strip()


def _tool_specs_to_schema_tools(tool_specs: List[Any]) -> List[Tool]:
    """Convert ToolSpec objects from tool_dispatch to ai.schemas.Tool objects."""
    return [
        Tool(name=spec.name, description=spec.description, parameters=spec.parameters)
        for spec in tool_specs
    ]


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
    rim_entities_accessed: List[Dict[str, Any]] = field(default_factory=list)  # from get_code_relationships
    rim_relationship_types_used: List[str] = field(default_factory=list)  # from get_code_relationships
    latency_ms: Dict[str, float] = field(default_factory=dict)  # {"loop_total", "llm_total", "tool_total"}


@dataclass
class SystemPromptParts:
    """Decomposed system prompt for token accounting."""
    grounding_and_protocol_text: str  # static grounding + protocol instructions
    tool_catalog_text: str  # tool schemas
    rim_metadata_text: str  # RIM metadata block (empty string for baseline)
    full_text: str  # concatenation sent to LLM


class QALoop:
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
        provider: Optional[str] = None,
        structured_logger: Optional["StructuredLogger"] = None,
        request_id: Optional[str] = None,
        repository: Optional[str] = None,
        mode: Optional[str] = None,  # "baseline" or "rim"
        on_turn: Optional[Callable[["QALoopTurn"], Awaitable[None]]] = None,
    ):
        self.llm_service = llm_service
        self.tool_dispatch = tool_dispatch
        self.config = config
        self.system_prompt_parts = system_prompt_parts
        self.model = model
        self.provider = provider
        self.guardrails = LoopGuardrails(config)
        self.structured_logger = structured_logger
        self.request_id = request_id
        self.repository = repository
        self.mode = mode
        self.on_turn = on_turn
        # Create protocol adapter with model_id for format-specific parsing (Hermes XML for Qwen, JSON for others)
        self.protocol_adapter = QAProtocolAdapter(model_id=model)
        self.consecutive_malformed_count = 0  # Track malformed responses to terminate early
        self.verification_retries = 0  # Track validation rejection count to prevent infinite retry loops
        self.max_verification_retries = 2

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Backward compatibility helper delegating to protocol_adapter."""
        return self.protocol_adapter.parse_response(response_text)

    def _get_provider_budget_profile(self) -> Dict[str, Any]:
        """Derive provider budget profile using modular qa_budgeting helper."""
        return derive_provider_budget_profile(self.model, self.provider, self.llm_service)

    def _compact_messages_deterministically(self, messages: List[Dict[str, Any]], target_tokens: int) -> List[Dict[str, Any]]:
        """Deterministic context compaction using modular qa_budgeting helper."""
        return compact_messages_deterministically(messages, target_tokens)

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

        print(f"[QALoop:START] Loop starting at T+0ms for question: {question[:60]}...")

        while True:
            turn_index = len(result.turns)
            elapsed = (time.perf_counter() - loop_start) * 1000

            # Log conversation state for context window analysis
            import json as _json
            messages_size = sum(len(m.get("content", "")) for m in messages if isinstance(m, dict))
            messages_size_kb = messages_size / 1024
            print(f"[QALoop:TURN] T+{elapsed:.0f}ms turn_index={turn_index} context_messages={len(messages)} history_size_chars={messages_size} history_size_kb={messages_size_kb:.1f}")

            print(f"[QALoop:TURN] T+{elapsed:.0f}ms turn_index={turn_index} context_messages={len(messages)}")
            self.guardrails.record_turn()

            # 1. Check guardrails BEFORE turn
            stop_reason = self.guardrails.check_pre_turn_limits()
            if stop_reason:
                logger.info(f"[QALoop] Guardrail limit hit: {stop_reason}; forcing final answer")
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
                if self.on_turn:
                    await self.on_turn(turn)
                answer = self.protocol_adapter.parse_final_synthesis(turn.raw_model_output)
                if not answer:
                    answer = turn.raw_model_output
                # Run fact validation on pre-turn limit final answer and append caveats if needed
                _, _, caveated = self._validate_final_answer_against_evidence(answer, result)
                result.answer = caveated
                break

            # 2. Call LLM with current conversation
            logger.debug(f"[QALoop] Turn {turn_index}: calling LLM...")
            turn_start = time.perf_counter()

            try:
                # PROVIDER-AWARE TOKEN BUDGET & CONTEXT MANAGEMENT
                profile = self._get_provider_budget_profile()
                safe_budget = profile["safe_budget"]
                is_rim = self.mode == "rim"
                tool_specs = self.tool_dispatch.specs(include_rim=is_rim)
                schema_tools = _tool_specs_to_schema_tools(tool_specs) if tool_specs else None

                # Build draft request with compact state summary
                sys_text = self.system_prompt_parts.full_text
                if turn_index > 0:
                    state_summary = self.guardrails.state.get_compact_summary()
                    sys_text = f"{sys_text}\n\n{state_summary}"

                llm_messages = [
                    Message(role=MessageRole.SYSTEM, content=sys_text),
                ]
                for msg in messages:
                    try:
                        role_str = msg.get("role", "user").lower() if isinstance(msg, dict) else "user"
                        role = MessageRole(role_str) if role_str in ["system", "user", "assistant", "tool"] else MessageRole.USER
                        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                        tool_calls = msg.get("tool_calls") if isinstance(msg, dict) else None
                        llm_messages.append(Message(role=role, content=content, tool_calls=tool_calls))
                    except Exception as msg_err:
                        logger.error(f"[QALoop] Error processing message: {msg_err}")
                        raise

                request = LLMRequest(
                    messages=llm_messages,
                    model=self.model,
                    temperature=0.2,
                    max_tokens=settings.llm_max_tokens,
                    tools=schema_tools,
                )

                # Preflight check: count complete request tokens
                counted = await count_full_request(request, profile["provider"], profile["model"])
                # Provider-specific character estimate (e.g. Groq chars / 3.5 heuristic)
                request_chars = sum(len(m.content or "") for m in request.messages)
                if request.tools:
                    request_chars += sum(len(t.name) + len(t.description) + len(str(t.parameters)) for t in request.tools)
                provider_est_tokens = max(int(request_chars / 3.5), 1)

                effective_preflight_tokens = max(counted.total_tokens, provider_est_tokens)
                logger.debug(
                    f"[QALoop] Turn {turn_index}: Preflight count={counted.total_tokens} (provider_est={provider_est_tokens}, "
                    f"effective={effective_preflight_tokens}) vs safe_budget={safe_budget}"
                )

                # If request exceeds safe budget under either metric, apply deterministic multi-pass compaction
                if effective_preflight_tokens > safe_budget and len(messages) > 1:
                    logger.warning(
                        f"[QALoop] Turn {turn_index}: Request size (effective={effective_preflight_tokens} tokens) "
                        f"exceeds safe budget ({safe_budget} tokens). Running deterministic compaction..."
                    )
                    compacted_messages = self._compact_messages_deterministically(messages, safe_budget)
                    # Rebuild messages
                    llm_messages = [
                        Message(role=MessageRole.SYSTEM, content=self.system_prompt_parts.full_text),
                    ]
                    for msg in compacted_messages:
                        role_str = msg.get("role", "user").lower() if isinstance(msg, dict) else "user"
                        role = MessageRole(role_str) if role_str in ["system", "user", "assistant", "tool"] else MessageRole.USER
                        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                        tool_calls = msg.get("tool_calls") if isinstance(msg, dict) else None
                        llm_messages.append(Message(role=role, content=content, tool_calls=tool_calls))

                    request = LLMRequest(
                        messages=llm_messages,
                        model=self.model,
                        temperature=0.2,
                        max_tokens=settings.llm_max_tokens,
                        tools=schema_tools,
                    )
                    counted_after = await count_full_request(request, profile["provider"], profile["model"])
                    chars_after = sum(len(m.content or "") for m in request.messages)
                    if request.tools:
                        chars_after += sum(len(t.name) + len(t.description) + len(str(t.parameters)) for t in request.tools)
                    provider_est_after = max(int(chars_after / 3.5), 1)
                    effective_after = max(counted_after.total_tokens, provider_est_after)
                    logger.info(
                        f"[QALoop] Post-compaction request tokens: {effective_preflight_tokens} -> "
                        f"{effective_after} (counted={counted_after.total_tokens}, est={provider_est_after})"
                    )

                llm_response = await self.llm_service.generate(request)
                logger.debug(f"[QALoop] Turn {turn_index}: LLM response ({len(llm_response.content)} chars)")
                self._context_overflow_retries = 0  # Reset retry counter on success
            except Exception as e:
                err_str = str(e).lower()
                is_recoverable_limit = (
                    "exceeds the available context size" in err_str
                    or "exceed_context_size_error" in err_str
                    or "maximum context length" in err_str
                    or "context length exceeded" in err_str
                    or "rate_limit_exceeded" in err_str
                    or "tokens per minute" in err_str
                    or "tpm" in err_str
                    or "request too large" in err_str
                    or "413" in err_str
                    or "resource_exhausted" in err_str
                    or getattr(e, "status_code", None) == 413
                )
                retries = getattr(self, "_context_overflow_retries", 0)
                if is_recoverable_limit and retries < 2:
                    self._context_overflow_retries = retries + 1
                    logger.warning(
                        f"[QALoop] Recoverable provider limit/413 detected at turn {turn_index}. "
                        f"Compacting observations and retrying ({self._context_overflow_retries}/2)..."
                    )
                    # Emergency compaction of conversation history
                    messages = self._compact_messages_deterministically(messages, safe_budget // 2)
                    continue

                logger.error(f"[QALoop] LLM call failed: {e}", exc_info=True)
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

            # 3. Parse response: tool_call | final_answer | malformed (using format-specific parser)
            parsed = self.protocol_adapter.parse_response_from_llm_response(llm_response)

            # Log comprehensive turn diagnostics for debugging tool-calling issues
            if self.structured_logger and self.request_id:
                is_rim = self.mode == "rim"
                tool_specs = self.tool_dispatch.specs(include_rim=is_rim)
                available_tools = [spec.name for spec in tool_specs] if hasattr(tool_specs, '__iter__') else []
                protocol_format = "hermes_xml" if self.protocol_adapter.is_qwen else "json"

                self.structured_logger.log_turn_diagnostic(
                    turn_index=turn_index,
                    mode=self.mode,
                    input_query=messages[-1].get("content", "") if messages else None,
                    system_prompt_excerpt=self.system_prompt_parts.grounding_and_protocol_text[:1000],
                    available_tools=available_tools,
                    protocol_format=protocol_format,
                    raw_llm_response=llm_response.content,
                    parsed_action=parsed.get("action"),
                    parsed_tool_name=parsed.get("tool_name"),
                    parsed_arguments=parsed.get("arguments"),
                    parse_error=parsed.get("error"),
                )

            # Log all details to debug for troubleshooting
            elapsed = (time.perf_counter() - loop_start) * 1000
            if parsed["action"] == "tool_call":
                print(f"[QALoop:DECISION] T+{elapsed:.0f}ms turn={turn_index} -> tool_call: {parsed.get('tool_name')}")
                logger.debug(f"[QALoop] Turn {turn_index}: tool={parsed.get('tool_name')}")
            elif parsed["action"] == "final_answer":
                print(f"[QALoop:DECISION] T+{elapsed:.0f}ms turn={turn_index} -> FINAL_ANSWER")
                logger.debug(f"[QALoop] Turn {turn_index}: FINAL_ANSWER")
            else:
                pass

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
                self.consecutive_malformed_count = 0  # Reset on success
                answer_candidate = parsed.get("answer", llm_response.content)

                # Parse and clean candidate first using dedicated synthesis parser
                parsed_candidate = self.protocol_adapter.parse_final_synthesis(answer_candidate)
                if not parsed_candidate:
                    parsed_candidate = strip_xml_tags(answer_candidate)
                    parsed_candidate = extract_json_answer(parsed_candidate)

                # Stage 4 Fact Validation against tool results in the session
                is_valid, validation_feedback, caveated_answer = self._validate_final_answer_against_evidence(
                    parsed_candidate, result
                )

                if not is_valid:
                    # If verification attempts have not exceeded max retries and turns remain
                    if self.verification_retries < self.max_verification_retries and turn_index < self.config.max_agent_turns:
                        self.verification_retries += 1
                        logger.warning(
                            f"[ValidationGate] Final answer fact validation failed (attempt {self.verification_retries}/{self.max_verification_retries}); prompting correction"
                        )
                        messages.append({
                            "role": "assistant",
                            "content": llm_response.content,
                        })
                        messages.append({
                            "role": "user",
                            "content": validation_feedback or "[VERIFICATION REQUIRED] Your factual claims conflict with repository observations. Please verify or correct them.",
                        })
                        result.turns.append(turn)
                        if self.on_turn:
                            await self.on_turn(turn)
                        continue
                    else:
                        # Max retries reached: attach caveats and complete gracefully
                        logger.warning(
                            f"[ValidationGate] Max verification retries reached ({self.verification_retries}); appending caveats"
                        )
                        result.answer = caveated_answer
                        result.stop_reason = StopReason.COMPLETED_FOR_VERIFICATION
                        result.turns.append(turn)
                        if self.on_turn:
                            await self.on_turn(turn)
                        break

                # Answer passed validation
                result.answer = caveated_answer
                result.stop_reason = StopReason.COMPLETED_FOR_VERIFICATION
                result.turns.append(turn)
                if self.on_turn:
                    await self.on_turn(turn)
                logger.info(f"[QALoop] LLM provided validated final answer at turn {turn_index}")
                break

            elif parsed["action"] == "tool_call":
                self.consecutive_malformed_count = 0  # Reset on success
                # Extract first (and only) tool call from the normalized list
                tool_calls = parsed.get("tool_calls", [])
                if not tool_calls:
                    logger.error(f"[QALoop] tool_call action but no tool_calls in parsed response")
                    continue
                tool_call = tool_calls[0]
                tool_name = tool_call.get("tool_name", "")
                arguments = tool_call.get("arguments", {})

                # 4b. Deterministic Relational Routing:
                # If question has strong relational intent (e.g. who calls, what calls, who imports, what depends on,
                # what inherits, call path, dependency chain) and LLM chooses lexical search (search_repository/search_code)
                # in RIM mode, check if target symbol can be resolved and route to get_code_relationships first.
                if (
                    self.mode == "rim"
                    and tool_name in ("search_repository", "search_code")
                    and getattr(self.tool_dispatch, "target_resolver", None)
                    and getattr(self.tool_dispatch, "graph_traverser", None)
                ):
                    rel_intent = classify_semantic_query(question)
                    strong_rel_classes = (
                        SemanticQueryClass.CALLS_REVERSE,
                        SemanticQueryClass.CALLS_FORWARD,
                        SemanticQueryClass.IMPORTS_REVERSE,
                        SemanticQueryClass.IMPORTS_FORWARD,
                        SemanticQueryClass.INHERITS_REVERSE,
                        SemanticQueryClass.INHERITS_FORWARD,
                        SemanticQueryClass.DATABASE_ACCESS,
                    )
                    if rel_intent.query_class in strong_rel_classes and rel_intent.target_raw_name:
                        resolved_target = self.tool_dispatch.target_resolver.resolve(rel_intent.target_raw_name)
                        # Also check if lexical search argument query itself matches a known symbol
                        lexical_query = str(arguments.get("query", "")).strip()
                        if not resolved_target and lexical_query:
                            resolved_target = self.tool_dispatch.target_resolver.resolve(lexical_query)

                        if resolved_target:
                            # Map semantic query class to relationship_type and direction
                            target_name = getattr(resolved_target, "name", None) or rel_intent.target_raw_name
                            rel_type_map = {
                                SemanticQueryClass.CALLS_REVERSE: ("CALLS", "REVERSE"),
                                SemanticQueryClass.CALLS_FORWARD: ("CALLS", "FORWARD"),
                                SemanticQueryClass.IMPORTS_REVERSE: ("IMPORTS", "REVERSE"),
                                SemanticQueryClass.IMPORTS_FORWARD: ("IMPORTS", "FORWARD"),
                                SemanticQueryClass.INHERITS_REVERSE: ("INHERITS", "REVERSE"),
                                SemanticQueryClass.INHERITS_FORWARD: ("INHERITS", "FORWARD"),
                                SemanticQueryClass.DATABASE_ACCESS: ("DATABASE_ACCESS", "REVERSE"),
                            }
                            mapped_rel, mapped_dir = rel_type_map.get(
                                rel_intent.query_class, ("GENERIC", rel_intent.direction.value)
                            )
                            # Only reroute if get_code_relationships has not already been queried for this target & relationship
                            already_queried = any(
                                t.tool_call
                                and t.tool_call.get("tool_name") == "get_code_relationships"
                                and str(t.tool_call.get("arguments", {}).get("entity_name", "")).lower() == target_name.lower()
                                and str(t.tool_call.get("arguments", {}).get("relationship_type", "")).upper() == mapped_rel
                                for t in result.turns
                            )
                            if not already_queried:
                                logger.info(
                                    f"[QALoop:RelationalRouting] Strong relational intent detected ({rel_intent.query_class.value}). "
                                    f"Deterministically routing '{tool_name}' -> 'get_code_relationships' for entity '{target_name}'."
                                )
                                print(
                                    f"[QALoop:RELATIONAL_ROUTING] turn={turn_index} rerouting {tool_name} -> "
                                    f"get_code_relationships(entity_name={target_name}, relationship_type={mapped_rel}, direction={mapped_dir})"
                                )
                                tool_name = "get_code_relationships"
                                arguments = {
                                    "entity_name": target_name,
                                    "relationship_type": mapped_rel,
                                    "direction": mapped_dir,
                                    "scope": "LOCAL",
                                    "depth": 1,
                                    "limit": 15,
                                }
                                # Update tool_call dict so recording and observations reflect the routed tool
                                tool_call["tool_name"] = tool_name
                                tool_call["arguments"] = arguments

                # 4b. Smart read_file unread interval adjustment:
                # If model requested a range for a file that was partially read (e.g. read 1-96, requested 1-200),
                # calculate the unread portion (e.g. 97-200) and execute that directly instead of blocking as duplicate!
                if tool_name == "read_file" and isinstance(arguments, dict) and arguments.get("path"):
                    r_path = str(arguments.get("path", ""))
                    r_start = arguments.get("start_line")
                    r_end = arguments.get("end_line")
                    if r_start is not None and r_end is not None:
                        try:
                            s_int = int(r_start)
                            e_int = int(r_end)
                            unread_slice = self.guardrails.state.get_unread_slice_for_request(r_path, s_int, e_int)
                            if unread_slice is not None:
                                unread_s, unread_e = unread_slice
                                if (unread_s, unread_e) != (s_int, e_int):
                                    logger.info(
                                        f"[QALoop:SmartRead] Adjusting read_file({r_path}) from {s_int}-{e_int} to "
                                        f"unread range {unread_s}-{unread_e}."
                                    )
                                    arguments["start_line"] = unread_s
                                    arguments["end_line"] = unread_e
                                    tool_call["arguments"] = arguments
                        except (ValueError, TypeError):
                            pass

                # 5. Check duplicate tool call in current session with state awareness
                is_sufficient, suff_msg = self.check_evidence_sufficiency(question, result)
                self.guardrails.state.evidence_sufficient = is_sufficient
                is_duplicate, duplicate_feedback = self.guardrails.is_duplicate_call(
                    tool_name, arguments, is_evidence_sufficient=is_sufficient
                )
                if is_duplicate:
                    logger.warning(
                        f"[QALoop] Duplicate tool call detected at turn {turn_index}: {tool_name} with {arguments}"
                    )
                    has_relevant_evidence = is_sufficient or self.guardrails.state.evidence_sufficient or self.guardrails.state.answer_ready

                    if has_relevant_evidence:
                        # Better duplicate recovery: Branch YES -> Transition directly to final synthesis
                        logger.info(
                            f"[QALoop] Duplicate tool call with sufficient evidence at turn {turn_index}; "
                            f"transitioning directly to final answer synthesis."
                        )
                        self.guardrails.state.evidence_sufficient = True
                        self.guardrails.state.answer_ready = True

                        feedback_msg = duplicate_feedback or (
                            f"[DUPLICATE TOOL CALL] [EVIDENCE SUFFICIENT] Duplicate call to '{tool_name}' prevented. "
                            f"Relevant evidence is already collected in your conversation history. "
                            f"Synthesize and output your final answer now."
                        )
                        messages.append({
                            "role": "assistant",
                            "content": llm_response.content,
                        })
                        messages.append({
                            "role": "user",
                            "content": (
                                f"{suff_msg or '[EVIDENCE SUFFICIENT]'}\n"
                                f"{feedback_msg}\n"
                                "Do not make any further tool calls. Please synthesize and output your final answer now."
                            ),
                        })

                        turn.tool_call = {"tool_name": tool_name, "arguments": arguments}
                        turn.tool_observation = {
                            "tool_name": tool_name,
                            "success": False,
                            "error": {"type": "duplicate_call_prevented", "message": feedback_msg},
                            "data": None,
                            "formatted_message": feedback_msg,
                        }
                        result.turns.append(turn)
                        if self.on_turn:
                            await self.on_turn(turn)

                        final_turn = await self._do_final_answer_turn(
                            turn_index + 1, messages, llm_total_ms, tool_total_ms, loop_start
                        )
                        result.turns.append(final_turn)
                        if self.on_turn:
                            await self.on_turn(final_turn)
                        answer = self.protocol_adapter.parse_final_synthesis(final_turn.raw_model_output)
                        if not answer:
                            answer = final_turn.raw_model_output
                        _, _, caveated = self._validate_final_answer_against_evidence(answer, result)
                        result.answer = caveated
                        result.stop_reason = StopReason.COMPLETED_FOR_VERIFICATION
                        break
                    else:
                        # Better duplicate recovery: Branch NO -> Use state-aware duplicate feedback and targeted guidance
                        missing_guidance = identify_missing_evidence(question, result, tool_name, arguments)
                        base_feedback = duplicate_feedback or f"[DUPLICATE TOOL CALL] You already called '{tool_name}' with these arguments. Do not repeat identical calls."
                        if missing_guidance and "Do not repeat identical calls" not in missing_guidance:
                            targeted_feedback = (
                                f"[DUPLICATE TOOL CALL - EVIDENCE INCOMPLETE]\n"
                                f"{base_feedback}\n"
                                f"Missing evidence needed: {missing_guidance}"
                            )
                        else:
                            targeted_feedback = base_feedback

                        assistant_message = {
                            "role": "assistant",
                            "content": llm_response.content,
                        }
                        if llm_response.tool_calls:
                            assistant_message["tool_calls"] = [
                                {
                                    "type": "function",
                                    "id": tc.tool_call_id,
                                    "function": {
                                        "name": tc.tool_name,
                                        "arguments": tc.parameters if isinstance(tc.parameters, str) else json.dumps(tc.parameters),
                                    },
                                }
                                for tc in llm_response.tool_calls
                            ]
                        messages.append(assistant_message)
                        messages.append({
                            "role": "user",
                            "content": targeted_feedback,
                        })

                        turn.tool_call = {"tool_name": tool_name, "arguments": arguments}
                        turn.tool_observation = {
                            "tool_name": tool_name,
                            "success": False,
                            "error": {"type": "duplicate_call_prevented", "message": targeted_feedback},
                            "data": None,
                            "formatted_message": targeted_feedback,
                        }
                        result.turns.append(turn)
                        if self.on_turn:
                            await self.on_turn(turn)
                        # Do not increment result.tool_call_count because execution was intercepted
                        continue

                # 5b. Evidence-sufficiency advisory check:
                # Do NOT forcibly stop or hijack the agent if it is still proposing valid, non-duplicate tool calls.
                # Evidence sufficiency is purely informational; the LLM remains in control of deciding when to finalize.
                is_sufficient, suff_msg = self.check_evidence_sufficiency(question, result)
                if is_sufficient:
                    self.guardrails.state.evidence_sufficient = True
                    logger.debug(f"[QALoop] Evidence sufficiency advisory noted at turn {turn_index} (allowing agent tool call to proceed).")

                # 6. Check guardrails on tool call
                stop_reason, should_warn = self.guardrails.record_tool_call(tool_name, arguments)
                if stop_reason:
                    logger.warning(f"[QALoop] Tool call limit hit: {stop_reason}")
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
                    if self.on_turn:
                        await self.on_turn(turn)
                    result.turns.append(final_turn)
                    if self.on_turn:
                        await self.on_turn(final_turn)
                    # Parse the final answer response using dedicated synthesis parser
                    answer = self.protocol_adapter.parse_final_synthesis(final_turn.raw_model_output)
                    if not answer:
                        answer = final_turn.raw_model_output
                    # Run fact validation on tool-limit final answer and append caveats if needed
                    _, _, caveated = self._validate_final_answer_against_evidence(answer, result)
                    result.answer = caveated
                    break

                # 7. Execute tool with pre-calculated content token budget
                logger.debug(f"[QALoop] Turn {turn_index}: executing tool '{tool_name}'")
                tool_start = time.perf_counter()
                loop_elapsed = (tool_start - loop_start) * 1000
                print(f"[QALoop:EXEC] T+{loop_elapsed:.0f}ms turn={turn_index} executing {tool_name}")

                # Calculate remaining token budget available for tool output before execution
                profile = self._get_provider_budget_profile()
                control_res = profile.get("control_reservation", 60)
                safe_budget = profile["safe_budget"]
                # Approximate current conversation tokens
                current_chars = len(self.system_prompt_parts.full_text) + sum(len(m.get("content", "")) for m in messages if isinstance(m, dict))
                est_current_tokens = int(current_chars / 3.5)
                # For read_file, ensure a viable minimum token budget (>= 2000 tokens) so normal files (<= 200 lines)
                # can be inspected cleanly without forced ~25-line micro-clamping. Deterministic compaction handles context window limits.
                min_tool_floor = 2000 if tool_name == "read_file" else 500
                remaining_for_tool = max(min_tool_floor, safe_budget - est_current_tokens - control_res)

                try:
                    tool_observation = self.tool_dispatch.dispatch(
                        tool_name,
                        arguments,
                        max_content_tokens=remaining_for_tool,
                        control_reservation_tokens=control_res,
                    )
                except Exception as e:
                    logger.error(f"[QALoop] Tool dispatch error: {e}", exc_info=True)
                    tool_observation = ToolObservation(
                        tool_call_id=f"turn-{turn_index}",
                        tool_name=tool_name,
                        success=False,
                        error={"type": "dispatch_error", "message": str(e)},
                    )

                tool_elapsed = time.perf_counter() - tool_start
                tool_total_ms += tool_elapsed * 1000
                loop_elapsed_after = (time.perf_counter() - loop_start) * 1000
                print(f"[QALoop:RESULT] T+{loop_elapsed_after:.0f}ms turn={turn_index} {tool_name} -> success={tool_observation.success} elapsed={tool_elapsed*1000:.0f}ms")

                # Record execution result in guardrails for duplicate detection
                self.guardrails.record_tool_result(
                    tool_name=tool_name,
                    arguments=arguments,
                    success=tool_observation.success,
                    data=tool_observation.data,
                    error=tool_observation.error,
                    turn_index=turn_index,
                )

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
                elif tool_name == "get_code_relationships" and tool_observation.success:
                    # Track RIM access from get_code_relationships tool
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
                # Preserve native tool_calls from providers (e.g., OpenRouter, Gemini)
                assistant_message = {
                    "role": "assistant",
                    "content": llm_response.content,
                }
                if llm_response.tool_calls:
                    # Include native tool_calls for providers that support them
                    assistant_message["tool_calls"] = [
                        {
                            "type": "function",
                            "id": tc.tool_call_id,
                            "function": {
                                "name": tc.tool_name,
                                "arguments": tc.parameters if isinstance(tc.parameters, str) else json.dumps(tc.parameters),
                            },
                        }
                        for tc in llm_response.tool_calls
                    ]
                messages.append(assistant_message)

                obs_content = self._format_tool_observation(tool_name, tool_observation, sanitized_data)
                is_sufficient, suff_msg = self.check_evidence_sufficiency(question, result)
                if is_sufficient and suff_msg:
                    obs_content += f"\n\n{suff_msg}"

                messages.append({
                    "role": "user",
                    "content": obs_content,
                })

                # Record turn with tool info (include data and formatted message for later reconstruction)
                formatted_message = self._format_tool_observation(tool_name, tool_observation, sanitized_data)

                # Log tool result size for context analysis
                formatted_msg_size = len(formatted_message)
                formatted_msg_kb = formatted_msg_size / 1024
                data_size = len(str(sanitized_data)) if sanitized_data else 0
                print(f"[QALoop:TOOL_RESULT] T+{loop_elapsed_after:.0f}ms turn={turn_index} tool={tool_name} result_chars={formatted_msg_size} result_kb={formatted_msg_kb:.1f} data_chars={data_size}")

                turn.tool_call = {"tool_name": tool_name, "arguments": arguments}
                turn.tool_observation = {
                    "tool_name": tool_name,
                    "success": tool_observation.success,
                    "error": tool_observation.error,
                    "data": sanitized_data,  # Include actual result data for metrics/reconstruction
                    "formatted_message": formatted_message,  # Include formatted message for audit trail
                }
                result.turns.append(turn)
                if self.on_turn:
                    await self.on_turn(turn)
                result.tool_call_count += 1
                logger.debug(f"[QALoop] Turn {turn_index}: {tool_name} executed in {tool_elapsed*1000:.0f}ms")

            else:  # malformed
                self.consecutive_malformed_count += 1

                if self.structured_logger and self.request_id:
                    self.structured_logger.log_malformed_response(
                        raw_content=llm_response.content,
                        parse_error=parsed.get("error", "unknown"),
                        turn_index=turn_index,
                        consecutive_count=self.consecutive_malformed_count,
                        mode=self.mode,
                    )

                # Terminate after 5 consecutive malformed responses
                if self.consecutive_malformed_count >= 5:
                    logger.error(f"[QALoop] TERMINATING: 5 consecutive malformed responses. Model is stuck or out of context.")
                    if self.structured_logger and self.request_id:
                        self.structured_logger.log_malformed_response(
                            raw_content=llm_response.content,
                            parse_error=parsed.get("error", "unknown"),
                            turn_index=turn_index,
                            consecutive_count=self.consecutive_malformed_count,
                            mode=self.mode,
                            terminated=True,
                        )
                    result.answer = "[LOOP TERMINATED] Model produced 5 consecutive malformed responses and could not recover. The model may be stuck or out of context."
                    result.stop_reason = StopReason.MODEL_ERROR
                    result.turns.append(turn)
                    if self.on_turn:
                        await self.on_turn(turn)
                    break

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
                if self.on_turn:
                    await self.on_turn(turn)

        # Calculate latencies
        loop_elapsed = time.perf_counter() - loop_start
        result.latency_ms = {
            "loop_total": loop_elapsed * 1000,
            "llm_total": llm_total_ms,
            "tool_total": tool_total_ms,
        }

        # Log completion - show critical summary
        total_elapsed = (time.perf_counter() - loop_start) * 1000
        log_message = (f"[QALoop] Completed {len(result.turns)} turns | "
                      f"{result.tool_call_count} tool calls | "
                      f"{result.stop_reason} | "
                      f"Total time: {total_elapsed:.0f}ms")

        print(f"[QALoop:END] T+{total_elapsed:.0f}ms turns={len(result.turns)} tools={result.tool_call_count} reason={result.stop_reason.value}")

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
            # Build dedicated synthesis system prompt (do not send the tool-calling prompt!)
            final_system_prompt = (
                "You are an expert repository analysis assistant. "
                "The exploration phase is complete. Based strictly on the conversation history "
                "and tool observations above, provide a comprehensive, clear, and well-structured Markdown "
                "answer to the user's initial question. Do NOT attempt to call any tools or output tool syntax. "
                "Provide only your final answer in Markdown directly."
            )
            llm_messages = [
                Message(role=MessageRole.SYSTEM, content=final_system_prompt),
            ]

            # Context windowing: keep initial query and recent turns to prevent token explosion on rate-limited providers,
            # while ensuring verified file observations from earlier turns are preserved in the synthesis pool.
            window_size = 10
            msgs_to_include = messages
            if len(messages) > window_size and len(messages) > 1:
                recent_msgs = messages[-(window_size - 1):]
                # Identify any unique read_file evidence messages from older history not in recent_msgs
                older_evidence = []
                recent_ids = {id(m) for m in recent_msgs}
                seen_evidence_paths = set()
                # Check recent messages for paths already present
                for m in recent_msgs:
                    c = m.get("content", "") if isinstance(m, dict) else str(m)
                    meta = extract_read_file_metadata(c)
                    if meta and meta.get("path"):
                        seen_evidence_paths.add(meta["path"])

                for m in messages[1:-(window_size - 1)]:
                    if id(m) in recent_ids:
                        continue
                    c = m.get("content", "") if isinstance(m, dict) else str(m)
                    meta = extract_read_file_metadata(c)
                    # If this older message contains source evidence for a file not in recent messages, preserve it
                    if meta and meta.get("path") and meta["path"] not in seen_evidence_paths:
                        older_evidence.append(m)
                        seen_evidence_paths.add(meta["path"])

                msgs_to_include = [messages[0]] + older_evidence + recent_msgs

            # Enforce provider-aware budgeting on final answer turn as well
            profile = self._get_provider_budget_profile()
            safe_budget = profile["safe_budget"]

            # First apply deterministic compaction to msgs_to_include if conversation is heavy
            msgs_to_include = self._compact_messages_deterministically(msgs_to_include, safe_budget)

            for msg in msgs_to_include:
                try:
                    role_str = msg.get("role", "user").lower() if isinstance(msg, dict) else "user"
                    role = MessageRole(role_str) if role_str in ["system", "user", "assistant", "tool"] else MessageRole.USER
                    content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                    # If content is a tool observation, truncate if excessively long (>2000 chars)
                    if role == MessageRole.TOOL or "[read_file]" in content or "[search" in content:
                        if len(content) > 2000:
                            content = content[:2000] + "\n...[truncated for synthesis]..."
                    llm_messages.append(Message(role=role, content=content))
                except Exception as msg_err:
                    logger.error(f"[QALoop] Error processing message in final answer turn: {msg_err}")
                    raise

            # Add explicit instruction for final synthesis
            llm_messages.append(
                Message(
                    role=MessageRole.USER,
                    content=(
                        "Please provide your complete, final answer in Markdown now based on all the findings "
                        "and evidence gathered above. Do not call any tools."
                    ),
                )
            )

            request = LLMRequest(
                messages=llm_messages,
                model=self.model,
                temperature=0.2,
                max_tokens=settings.llm_max_tokens,
            )

            # Preflight check on final synthesis request
            counted_final = await count_full_request(request, profile["provider"], profile["model"])
            req_chars = sum(len(m.content or "") for m in request.messages)
            est_tokens_final = max(int(req_chars / 3.5), 1)
            effective_final = max(counted_final.total_tokens, est_tokens_final)
            logger.debug(
                f"[QALoop] Final answer preflight: {effective_final} tokens (counted={counted_final.total_tokens}, "
                f"est={est_tokens_final}) vs safe_budget={safe_budget}"
            )

            if effective_final > safe_budget and len(llm_messages) > 2:
                logger.warning(
                    f"[QALoop] Final synthesis request ({effective_final} tokens) exceeds safe budget "
                    f"({safe_budget} tokens). Compacting aggressively for synthesis..."
                )
                # Keep system prompt, initial user query, compact summaries, and final instruction
                emergency_msgs = [llm_messages[0], llm_messages[1]]
                for m in llm_messages[2:-1]:
                    c = m.content or ""
                    if len(c) > 500:
                        lines = c.splitlines()
                        hdr = lines[0] if lines else ""
                        c = f"{hdr}\n... [Evidence summary: {len(lines)} lines] ..."
                    emergency_msgs.append(Message(role=m.role, content=c))
                emergency_msgs.append(llm_messages[-1])
                request.messages = emergency_msgs

            llm_response = await self.llm_service.generate(request)

            raw_output = (llm_response.content or "").strip()
            # Parse final answer using dedicated synthesis parser
            parsed_answer = self.protocol_adapter.parse_final_synthesis(raw_output)

            # If model returned no content or returned only unexecuted tool calls in final turn, synthesize fallback from observations
            if not parsed_answer:
                logger.warning("[QALoop] Final turn produced no usable answer text; synthesizing summary from observations")
                obs_snippets = []
                for m in reversed(messages):
                    content = m.get("content", "") if isinstance(m, dict) else ""
                    if any(k in content for k in ["[read_file]", "[search", "routes", "export", "class ", "def "]):
                        lines = [line for line in content.splitlines() if line.strip() and not line.startswith("[")]
                        if lines:
                            obs_snippets.append("\n".join(lines[:12]))
                    if len(obs_snippets) >= 3:
                        break
                if obs_snippets:
                    raw_output = (
                        "### Key Repository Findings\n\n"
                        + "\n\n---\n\n".join(reversed(obs_snippets))
                    )
                else:
                    raw_output = "The repository analysis finished. Please review the collected evidence in the session."
            else:
                raw_output = parsed_answer

        except Exception as e:
            logger.error(f"[QALoop] Final answer LLM call failed: {e}", exc_info=True)
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
            raw_model_output=raw_output,
            prompt_tokens=llm_response.usage.prompt_tokens if llm_response.usage else 0,
            completion_tokens=llm_response.usage.completion_tokens if llm_response.usage else 0,
            provider=llm_response.provider,
            model=llm_response.model,
            duration_ms=(time.perf_counter() - turn_start) * 1000,
        )

    def _has_retrieval_been_performed(self, result: QALoopResult) -> bool:
        """Check if any repository retrieval has been performed in this execution."""
        return has_retrieval_been_performed(result)

    def check_evidence_sufficiency(self, question: str, result: QALoopResult) -> Tuple[bool, Optional[str]]:
        """Evaluate whether collected evidence is sufficient to answer the question."""
        return check_evidence_sufficiency(question, result)

    def _retrieval_evidence_supports_absence(self, result: QALoopResult, answer: str = "") -> Tuple[bool, str]:
        """Check if retrieval evidence supports an absence claim."""
        return retrieval_evidence_supports_absence(result, answer)

    def _is_absence_claim(self, answer: str) -> bool:
        """Detect if answer claims repository-wide absence."""
        return is_absence_claim(answer)

    def _validate_final_answer_against_evidence(
        self, answer: str, result: QALoopResult
    ) -> Tuple[bool, Optional[str], str]:
        """Validate factual claims in the final answer against tool results."""
        return validate_final_answer_against_evidence(answer, result)

    def _verify_absence_claim(self, answer: str, result: QALoopResult) -> bool:
        """Enforcement gate: absence claims must be backed by actual retrieval evidence."""
        if not self._is_absence_claim(answer):
            return True
        supported, _ = self._retrieval_evidence_supports_absence(result, answer)
        if not supported:
            logger.warning(f"[VerificationGate] Absence claim without supporting retrieval evidence: {answer[:100]}...")
            return False
        return True

    def _format_tool_observation(
        self, tool_name: str, observation: ToolObservation, data: Any
    ) -> str:
        """Format tool observation for appending to conversation."""
        return format_tool_observation(tool_name, observation, data)

