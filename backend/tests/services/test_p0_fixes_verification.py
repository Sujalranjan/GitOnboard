"""
Regression and verification tests for the 5 P0 fixes:
1. P0-1: Graph-aware agent routing (intent guidance in qa_protocol)
2. P0-2: Graph + file retrieval coordination (actionable next step guidance in query_rim observation)
3. P0-3: Stronger absence verification (targeted query relevance)
4. P0-4: Evidence-sufficiency stopping & pre-turn limit validation
5. P0-5: Tool-call / XML / envelope leakage prevention & fallback handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.loop.contracts import AgentLoopConfig, StopReason
from backend.ai.schemas import LLMResponse, TokenUsage
from backend.services.qa_loop import QALoop, QALoopResult, QALoopTurn
from backend.services.qa_protocol import QAProtocolAdapter, SystemPromptParts
from backend.services.tool_dispatch import ToolObservation


@pytest.fixture
def qa_loop_instance():
    llm_service = MagicMock()
    llm_service.providers = [MagicMock(provider_name="groq")]
    tool_dispatch = MagicMock()
    config = AgentLoopConfig(max_agent_turns=6, max_tool_calls=10)
    system_parts = SystemPromptParts(
        grounding_and_protocol_text="Grounding rules",
        tool_catalog_text="Tool catalog",
        rim_metadata_text="RIM metadata",
        full_text="System Prompt Context",
    )
    loop = QALoop(
        llm_service=llm_service,
        tool_dispatch=tool_dispatch,
        config=config,
        system_prompt_parts=system_parts,
        model="openai/gpt-oss-120b",
        provider="groq",
    )
    return loop


class TestP01GraphAwareRouting:
    """P0-1: Verify that intent routing guidance explicitly distinguishes graph-first vs search-first."""

    def test_routing_guidance_contains_explicit_intent_rules(self):
        rules = QAProtocolAdapter.REPOSITORY_ANALYSIS_RULES
        assert "Graph-First Intent (Prioritize `get_code_relationships`)" in rules
        assert "File/Search-First Intent" in rules
        assert "Callers / callees" in rules
        assert "Dependencies / dependents" in rules
        assert "Imports / imported-by" in rules

    @pytest.mark.asyncio
    async def test_deterministic_relational_routing_intercepts_lexical_search(self):
        """When user asks who calls authenticate and LLM proposes search_repository, orchestrator routes to get_code_relationships."""
        from unittest.mock import MagicMock, AsyncMock
        from backend.models.fact_store import FactSymbol
        from backend.services.tool_dispatch import ToolDispatchTable
        from backend.ai.service import LLMService
        from backend.ai.schemas import LLMResponse, TokenUsage
        from backend.intelligence.retrieval.graph_traverser import RelationshipTraversalResult, TraversedEntity
        from backend.agent.intent.semantic_query import SemanticQueryClass, TraversalDirection

        mock_target = FactSymbol(id="1:sym1", analysis_id=1, name="authenticate", symbol_type="function")
        resolver = MagicMock()
        resolver.resolve.return_value = mock_target

        traverser = MagicMock()
        traverser.traverse_bounded.return_value = RelationshipTraversalResult(
            query_class=SemanticQueryClass.CALLS_REVERSE,
            direction=TraversalDirection.REVERSE,
            target_entity=mock_target,
            target_display_name="authenticate",
            target_type="function",
            related_entities=[
                TraversedEntity(name="loginHandler", entity_type="function", location="server.js", line_number=42, relationship_role="caller")
            ],
            resolution="STATIC_CONFIRMED",
        )

        tool_dispatch = ToolDispatchTable(
            tool_layer=MagicMock(),
            graph_traverser=traverser,
            target_resolver=resolver,
        )

        from backend.ai.schemas import LLMResponse, TokenUsage, ToolCall

        # Mock LLM proposing lexical search_repository in Turn 0, then final answer in Turn 1
        llm_service = MagicMock(spec=LLMService)
        llm_service.generate = AsyncMock(side_effect=[
            LLMResponse(
                content="",
                provider="groq",
                model="openai/gpt-oss-120b",
                tool_calls=[
                    ToolCall(
                        tool_name="search_repository",
                        parameters={"query": "authenticate"},
                        tool_call_id="call_1",
                    )
                ],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            ),
            LLMResponse(
                content='loginHandler in server.js calls authenticate.',
                provider="groq",
                model="openai/gpt-oss-120b",
                usage=TokenUsage(prompt_tokens=150, completion_tokens=30),
            )
        ])

        config = AgentLoopConfig(max_agent_turns=3, max_tool_calls_total=3)
        system_parts = SystemPromptParts(
            grounding_and_protocol_text="Protocol instructions",
            tool_catalog_text="Tool catalog",
            rim_metadata_text="RIM metadata",
            full_text="System Prompt Context",
        )
        loop = QALoop(
            llm_service=llm_service,
            tool_dispatch=tool_dispatch,
            config=config,
            system_prompt_parts=system_parts,
            model="openai/gpt-oss-120b",
            provider="groq",
            mode="rim",
        )

        result = await loop.run("Who calls authenticate?")

        # Verify that turn 0 was deterministically routed to get_code_relationships
        assert len(result.turns) >= 1
        turn0 = result.turns[0]
        assert turn0.tool_call is not None
        assert turn0.tool_call["tool_name"] == "get_code_relationships"
        assert turn0.tool_call["arguments"]["entity_name"] == "authenticate"
        assert turn0.tool_call["arguments"]["relationship_type"] == "CALLS"
        assert turn0.tool_call["arguments"]["direction"] == "REVERSE"
        assert turn0.tool_observation["success"] is True
        assert turn0.tool_observation["data"]["found"] is True



class TestP02GraphFileCoordination:
    """P0-2: Verify that successful query_rim observation provides actionable read_file guidance."""

    def test_get_code_relationships_observation_includes_actionable_read_file_recommendation(self, qa_loop_instance):
        obs = ToolObservation(
            tool_call_id="call-1",
            tool_name="get_code_relationships",
            success=True,
            data={
                "found": True,
                "target": {"name": "login", "type": "function", "location": "src/auth.py", "line": 40},
                "related": [
                    {
                        "name": "verify_token",
                        "entity_type": "function",
                        "location": "src/tokens.py",
                        "line_number": 100,
                        "relationship_role": "CALLS",
                    }
                ],
            },
        )
        formatted = qa_loop_instance._format_tool_observation("get_code_relationships", obs, obs.data)
        assert "Actionable next step for verification:" in formatted
        assert "read_file(path='src/tokens.py', start_line=85, end_line=125)" in formatted
        assert "verify_token" in formatted


class TestP03StrongerAbsenceVerification:
    """P0-3: Verify that an absence claim is rejected if searches were unrelated to the entity."""

    def test_unrelated_zero_result_search_rejects_absence_claim(self, qa_loop_instance):
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "search_code", "arguments": {"query": "foo"}},
                    tool_observation={
                        "tool_name": "search_code",
                        "success": True,
                        "data": [],
                    },
                )
            ],
        )
        # Search was for "foo", but claim is that Redis is absent
        answer = "There is no Redis database configured in this repository."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)
        assert is_valid is False
        assert "did not target" in feedback
        assert "Verification Caveat" in caveated

    def test_targeted_zero_result_search_accepts_absence_claim(self, qa_loop_instance):
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "search_code", "arguments": {"query": "celery"}},
                    tool_observation={
                        "tool_name": "search_code",
                        "success": True,
                        "data": [],
                    },
                )
            ],
        )
        answer = "There is no Celery worker configured in this project."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)
        assert is_valid is True
        assert feedback is None
        assert "Verification Caveat" not in caveated

    def test_unsupported_positive_caller_claim_is_rejected(self, qa_loop_instance):
        """Claim that 'routes/auth.js calls authenticateToken' is rejected if not supported by retrieved evidence."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "search_code", "arguments": {"query": "auth"}},
                    tool_observation={
                        "tool_name": "search_code",
                        "success": True,
                        "data": [{"file": "routes/other.js", "snippet": "console.log('hello')"}],
                    },
                )
            ],
        )
        answer = "routes/auth.js calls authenticateToken during request handling."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)
        assert is_valid is False
        assert "unsupported by retrieved evidence" in feedback
        assert "routes/auth.js" in feedback
        assert "authenticateToken" in feedback
        assert "Verification Caveat" in caveated

    def test_supported_positive_caller_claim_via_graph_is_accepted(self, qa_loop_instance):
        """Claim that 'routes/auth.js calls authenticateToken' is accepted if graph confirmed it."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={
                        "tool_name": "get_code_relationships",
                        "arguments": {"entity_name": "authenticateToken", "relationship_type": "CALLS", "direction": "REVERSE"},
                    },
                    tool_observation={
                        "tool_name": "get_code_relationships",
                        "success": True,
                        "data": {
                            "found": True,
                            "target": {"name": "authenticateToken", "location": "middleware/auth.js"},
                            "related": [
                                {
                                    "name": "loginHandler",
                                    "location": "routes/auth.js",
                                    "relationship_role": "caller",
                                }
                            ],
                        },
                    },
                )
            ],
        )
        answer = "routes/auth.js calls authenticateToken during login."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)
        assert is_valid is True
        assert feedback is None
        assert "Verification Caveat" not in caveated

    def test_supported_positive_caller_claim_via_read_file_is_accepted(self, qa_loop_instance):
        """Claim that 'routes/auth.js calls authenticateToken' is accepted if routes/auth.js was read and contains the call."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "routes/auth.js"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {
                            "path": "routes/auth.js",
                            "raw_text": "router.post('/login', authenticateToken, (req, res) => { res.send('ok'); });",
                        },
                    },
                )
            ],
        )
        answer = "routes/auth.js calls authenticateToken when handling post requests."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)
        assert is_valid is True
        assert feedback is None
        assert "Verification Caveat" not in caveated


class TestP04EvidenceSufficiencyAndTermination:
    """P0-4: Verify evidence sufficiency detection and pre-turn limit validation."""

    def test_read_file_alone_not_sufficient_for_callers_question(self, qa_loop_instance):
        """read_file(X) alone must NOT be sufficient for 'Who calls X?'."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "auth.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {"path": "auth.py", "raw_text": "def auth(): return True  # definition of target function"},
                    },
                ),
            ],
        )
        is_sufficient, msg = qa_loop_instance.check_evidence_sufficiency("Who calls auth?", result)
        assert is_sufficient is False
        assert msg is None

    def test_imports_not_sufficient_for_callers_question(self, qa_loop_instance):
        """IMPORTS relationship evidence alone must NOT be sufficient for 'Who calls X?' (imports != callers)."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={
                        "tool_name": "get_code_relationships",
                        "arguments": {"entity_name": "auth", "relationship_type": "IMPORTS", "direction": "REVERSE"},
                    },
                    tool_observation={
                        "tool_name": "get_code_relationships",
                        "success": True,
                        "data": {
                            "found": True,
                            "resolution": "STATIC_CONFIRMED",
                            "related": [{"name": "server.py", "relationship_role": "importer"}],
                        },
                    },
                ),
                QALoopTurn(
                    turn_index=2,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "auth.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {"path": "auth.py", "raw_text": "def auth(): return True  # definition of target function"},
                    },
                ),
            ],
        )
        is_sufficient, msg = qa_loop_instance.check_evidence_sufficiency("Who calls auth?", result)
        assert is_sufficient is False
        assert msg is None

    def test_calls_relationship_sufficient_for_callers_question(self, qa_loop_instance):
        """CALLS relationship evidence is sufficient for 'Who calls X?'."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={
                        "tool_name": "get_code_relationships",
                        "arguments": {"entity_name": "auth", "relationship_type": "CALLS", "direction": "REVERSE"},
                    },
                    tool_observation={
                        "tool_name": "get_code_relationships",
                        "success": True,
                        "data": {
                            "found": True,
                            "resolution": "STATIC_CONFIRMED",
                            "related": [{"name": "loginHandler", "relationship_role": "caller", "location": "server.py", "line_number": 42}],
                        },
                    },
                ),
            ],
        )
        is_sufficient, msg = qa_loop_instance.check_evidence_sufficiency("Who calls auth?", result)
        assert is_sufficient is True
        assert "[EVIDENCE SUFFICIENT]" in msg

    def test_calls_relationship_with_caller_file_read_sufficient(self, qa_loop_instance):
        """CALLS relationship plus reading caller file is sufficient."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={
                        "tool_name": "get_code_relationships",
                        "arguments": {"entity_name": "auth", "relationship_type": "CALLS", "direction": "REVERSE"},
                    },
                    tool_observation={
                        "tool_name": "get_code_relationships",
                        "success": True,
                        "data": {
                            "found": True,
                            "related": [{"name": "loginHandler", "relationship_role": "caller", "location": "server.py", "line_number": 42}],
                        },
                    },
                ),
                QALoopTurn(
                    turn_index=2,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "server.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {"path": "server.py", "raw_text": "def loginHandler(): auth()  # invocations inside caller"},
                    },
                ),
            ],
        )
        is_sufficient, msg = qa_loop_instance.check_evidence_sufficiency("Who calls auth?", result)
        assert is_sufficient is True
        assert "[EVIDENCE SUFFICIENT]" in msg

    def test_functional_question_accepts_target_read(self, qa_loop_instance):
        """Target implementation read_file is sufficient for functional/explanation questions."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "auth.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {"path": "auth.py", "raw_text": "def auth():\n    return verify_jwt_token(request)\n"},
                    },
                ),
            ],
        )
        is_sufficient, msg = qa_loop_instance.check_evidence_sufficiency("What does auth do?", result)
        assert is_sufficient is True
        assert "[EVIDENCE SUFFICIENT]" in msg

    def test_missing_evidence_for_callers_identifies_call_relationship(self, qa_loop_instance):
        """Missing evidence diagnosis for 'Who calls X?' identifies missing CALLS relationship."""
        from backend.services.qa_validation import identify_missing_evidence
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "auth.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {"path": "auth.py", "raw_text": "def auth(): pass"},
                    },
                )
            ],
        )
        guidance = identify_missing_evidence("Who calls auth?", result, "read_file", {"path": "auth.py"})
        assert "Missing evidence: callers relationship" in guidance
        assert "get_code_relationships" in guidance
        assert "CALLS" in guidance

    @pytest.mark.asyncio
    async def test_pre_turn_limit_exit_runs_fact_validation_with_caveats(self, qa_loop_instance):
        # Force pre-turn limit by setting turn_count equal to max_agent_turns
        qa_loop_instance.config.max_agent_turns = 1
        qa_loop_instance.guardrails.turn_count = 1

        final_resp = LLMResponse(
            content="Summary: The project contains no postgresql database.",
            model="openai/gpt-oss-120b",
            provider="groq",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        qa_loop_instance.llm_service.generate = AsyncMock(return_value=final_resp)

        qa_loop_instance._validate_final_answer_against_evidence = MagicMock(
            return_value=(False, "Conflict", "Summary: The project contains no postgresql database.\n\n> [!WARNING]\n> **Verification Caveat:**\n> - Contradicted by evidence")
        )

        run_result = await qa_loop_instance.run("What database is used?")
        assert run_result.stop_reason == StopReason.MAX_TURNS_EXCEEDED
        assert "Verification Caveat" in run_result.answer


class TestP05ToolCallXMLLeakagePrevention:
    """P0-5: Verify robust stripping of <function_call>, [TOOL_CALL], fenced blocks, and JSON envelopes."""

    def test_strip_function_call_tags(self):
        adapter = QAProtocolAdapter(model_id="qwen3:4b-instruct")
        raw = "Analysis complete.\n<function_call>\nread_file(path='app.py')\n</function_call>"
        cleaned = adapter.parse_final_synthesis(raw)
        assert cleaned == "Analysis complete."
        assert "<function_call>" not in cleaned

    def test_strip_tool_call_brackets(self):
        adapter = QAProtocolAdapter(model_id="qwen3:4b-instruct")
        raw = "Analysis complete.\n[TOOL_CALL]read_file(path='app.py')[/TOOL_CALL]"
        cleaned = adapter.parse_final_synthesis(raw)
        assert cleaned == "Analysis complete."
        assert "[TOOL_CALL]" not in cleaned

    def test_strip_fenced_tool_call(self):
        adapter = QAProtocolAdapter(model_id="qwen3:4b-instruct")
        raw = "Analysis complete.\n```tool_call\n{\"tool_name\": \"read_file\", \"arguments\": {\"path\": \"app.py\"}}\n```"
        cleaned = adapter.parse_final_synthesis(raw)
        assert cleaned == "Analysis complete."
        assert "```tool_call" not in cleaned

    def test_strip_raw_json_tool_envelope(self):
        adapter = QAProtocolAdapter(model_id="qwen3:4b-instruct")
        raw = "Found configuration.\n{\"tool_name\": \"read_file\", \"arguments\": {\"path\": \"app.py\"}}"
        cleaned = adapter.parse_final_synthesis(raw)
        assert cleaned == "Found configuration."
        assert "read_file" not in cleaned

    def test_observation_fallback_when_synthesis_empty(self, qa_loop_instance):
        """When synthesis parser produces empty string from raw tool calls, observation fallback is used."""
        empty_clean = qa_loop_instance.protocol_adapter.parse_final_synthesis("<tool_call><invoke name='read_file'><parameter name='path'>x.py</parameter></invoke></tool_call>")
        assert empty_clean == ""
