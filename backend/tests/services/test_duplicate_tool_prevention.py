"""
Tests for Stage 2: Prevent Repetitive Tool Loops.

Validates:
1. Identical tool calls repeated within a session are intercepted.
2. Equivalent arguments with different key ordering or nested structures are detected.
3. Different arguments for the same tool are not blocked.
4. Repeated calls following a failed or empty result are permitted (allows legitimate retries).
5. Duplicate detection across multiple turns (non-consecutive duplicates).
6. Legitimate tool calls still execute normally.
7. Agent receives constructive feedback and can proceed to synthesize a final answer after interception.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.loop.contracts import AgentLoopConfig, StopReason
from backend.agent.loop.guardrails import LoopGuardrails
from backend.ai.schemas import LLMResponse, TokenUsage
from backend.services.qa_loop import QALoop
from backend.services.qa_protocol import SystemPromptParts


class TestDuplicateCallDetectionGuardrails:
    """Unit tests for LoopGuardrails duplicate detection methods."""

    def test_normalize_arguments_key_order_independence(self):
        """Arguments with different key order must yield the exact same canonical signature."""
        args1 = {"path": "lib/auth.ts", "start_line": 1, "end_line": 100}
        args2 = {"end_line": 100, "path": "lib/auth.ts", "start_line": 1}

        sig1 = LoopGuardrails.normalize_arguments(args1)
        sig2 = LoopGuardrails.normalize_arguments(args2)

        assert sig1 == sig2
        assert sig1 == '{"end_line":100,"path":"lib/auth.ts","start_line":1}'

    def test_normalize_arguments_nested_structures(self):
        """Nested dictionaries and lists are normalized deterministically."""
        args1 = {"filter": {"tags": ["a", "b"], "active": True}, "limit": 10}
        args2 = {"limit": 10, "filter": {"active": True, "tags": ["a", "b"]}}

        sig1 = LoopGuardrails.normalize_arguments(args1)
        sig2 = LoopGuardrails.normalize_arguments(args2)

        assert sig1 == sig2

    def test_duplicate_call_detected_after_successful_execution(self):
        """A call with identical arguments after a successful, non-empty result is flagged as a duplicate."""
        guardrails = LoopGuardrails()
        tool_name = "read_file"
        args = {"path": "lib/auth.ts", "start_line": 1, "end_line": 100}

        # Before execution: not a duplicate
        is_dup, _ = guardrails.is_duplicate_call(tool_name, args)
        assert is_dup is False

        # Record successful result
        guardrails.record_tool_result(
            tool_name=tool_name,
            arguments=args,
            success=True,
            data="export const auth = () => {...}",
            turn_index=1,
        )

        # Subsequent identical call: is a duplicate
        is_dup, feedback = guardrails.is_duplicate_call(tool_name, args)
        assert is_dup is True
        assert "You already called 'read_file' with these exact arguments in Turn 1" in feedback
        assert "Do not repeat identical calls" in feedback

    def test_equivalent_arguments_different_order_detected_as_duplicate(self):
        """Calls with equivalent arguments in different key order are recognized as duplicates."""
        guardrails = LoopGuardrails()
        tool_name = "read_file"
        args_first = {"path": "lib/auth.ts", "start_line": 1, "end_line": 100}
        args_reordered = {"end_line": 100, "path": "lib/auth.ts", "start_line": 1}

        guardrails.record_tool_result(
            tool_name=tool_name,
            arguments=args_first,
            success=True,
            data="export const auth = () => {...}",
            turn_index=2,
        )

        is_dup, feedback = guardrails.is_duplicate_call(tool_name, args_reordered)
        assert is_dup is True
        assert "Turn 2" in feedback

    def test_different_arguments_same_tool_not_blocked(self):
        """Different arguments for the same tool are not blocked."""
        guardrails = LoopGuardrails()
        tool_name = "read_file"

        guardrails.record_tool_result(
            tool_name=tool_name,
            arguments={"path": "lib/auth.ts", "start_line": 1, "end_line": 100},
            success=True,
            data="lines 1-100",
            turn_index=1,
        )

        # Same file, different range -> NOT a duplicate
        is_dup, _ = guardrails.is_duplicate_call(
            tool_name, {"path": "lib/auth.ts", "start_line": 101, "end_line": 200}
        )
        assert is_dup is False

        # Different file -> NOT a duplicate
        is_dup, _ = guardrails.is_duplicate_call(
            tool_name, {"path": "lib/api.ts", "start_line": 1, "end_line": 100}
        )
        assert is_dup is False

    def test_repeated_call_after_failed_result_allowed(self):
        """If previous call failed (e.g. timeout, syntax error, not found), retry is permitted."""
        guardrails = LoopGuardrails()
        tool_name = "read_file"
        args = {"path": "lib/auth.ts", "start_line": 1, "end_line": 100}

        guardrails.record_tool_result(
            tool_name=tool_name,
            arguments=args,
            success=False,
            error={"type": "timeout", "message": "Read timed out"},
            turn_index=1,
        )

        # Should NOT be blocked; retry is permitted
        is_dup, _ = guardrails.is_duplicate_call(tool_name, args)
        assert is_dup is False

    def test_repeated_call_after_empty_result_allowed(self):
        """If previous call returned an empty list/string, retry or re-query is permitted."""
        guardrails = LoopGuardrails()
        tool_name = "search_repository"
        args = {"query": "auth_token"}

        # Search returned no results (empty list)
        guardrails.record_tool_result(
            tool_name=tool_name,
            arguments=args,
            success=True,
            data=[],
            turn_index=1,
        )

        is_dup, _ = guardrails.is_duplicate_call(tool_name, args)
        assert is_dup is False

    def test_duplicate_across_multiple_intervening_turns(self):
        """Duplicates are detected even if several other tool calls occurred in between."""
        guardrails = LoopGuardrails()

        # Turn 1: read_file lib/auth.ts (1-100)
        guardrails.record_tool_result(
            "read_file", {"path": "lib/auth.ts", "start_line": 1, "end_line": 100},
            success=True, data="content", turn_index=1
        )
        # Turn 2: search_repository query="login"
        guardrails.record_tool_result(
            "search_repository", {"query": "login"},
            success=True, data=["match1"], turn_index=2
        )
        # Turn 3: read_file lib/api.ts (1-50)
        guardrails.record_tool_result(
            "read_file", {"path": "lib/api.ts", "start_line": 1, "end_line": 50},
            success=True, data="api content", turn_index=3
        )

        # Turn 4: model attempts to repeat Turn 1!
        is_dup, feedback = guardrails.is_duplicate_call(
            "read_file", {"path": "lib/auth.ts", "start_line": 1, "end_line": 100}
        )
        assert is_dup is True
        assert "Turn 1" in feedback


class TestQALoopDuplicateCallInterception:
    """Integration tests verifying QALoop behavior when a model generates duplicate calls."""

    @pytest.fixture
    def mock_qa_loop(self):
        llm_service = MagicMock()
        tool_dispatch = MagicMock()
        config = AgentLoopConfig(max_turns=10, max_tool_calls=10)
        system_parts = SystemPromptParts(
            grounding_and_protocol_text="Grounding",
            tool_catalog_text="Catalog",
            rim_metadata_text="",
            full_text="System Prompt",
        )
        loop = QALoop(
            llm_service=llm_service,
            tool_dispatch=tool_dispatch,
            config=config,
            system_prompt_parts=system_parts,
            model="qwen3:4b-instruct",
            provider="ollama",
        )
        return loop

    @pytest.mark.asyncio
    async def test_duplicate_call_intercepted_without_tool_dispatch(self, mock_qa_loop):
        """
        When the model issues an exact duplicate of a previous successful tool call:
        - tool_dispatch is NOT invoked a second time.
        - The model receives helpful feedback pointing to existing findings.
        - The model can then synthesize and terminate with a final answer.
        """
        mock_observation = MagicMock(
            success=True,
            error=None,
            data="export function authenticate() { return true; }"
        )
        mock_qa_loop.tool_dispatch.dispatch = MagicMock(return_value=mock_observation)
        mock_qa_loop.tool_dispatch.specs = MagicMock(return_value=[])

        # Sequence of model outputs:
        # Turn 0: read_file(lib/auth.ts, 1, 100) -> executed
        # Turn 1: exact same read_file(lib/auth.ts, 1, 100) -> intercepted by guardrails!
        # Turn 2: final_answer based on findings -> succeeds
        resp0 = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">lib/auth.ts</parameter><parameter name="start_line">1</parameter><parameter name="end_line">100</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
        )
        resp1_duplicate = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">lib/auth.ts</parameter><parameter name="start_line">1</parameter><parameter name="end_line">100</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=150, completion_tokens=30, total_tokens=180),
        )
        resp2_final = LLMResponse(
            content='<tool_call><invoke name="final_answer"><parameter name="answer">The authentication function returns true.</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=40, total_tokens=240),
        )

        mock_qa_loop.llm_service.generate = AsyncMock(side_effect=[resp0, resp1_duplicate, resp2_final])

        result = await mock_qa_loop.run("How does authentication work?")

        # Tool dispatch was called only ONCE (for Turn 0, not Turn 1)
        assert mock_qa_loop.tool_dispatch.dispatch.call_count == 1
        # Final answer was successfully produced
        assert "The authentication function returns true." in result.answer
        assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
        # Verify that turn 1 recorded the duplicate prevention observation
        dup_turn = result.turns[1]
        assert dup_turn.tool_observation["error"]["type"] == "duplicate_call_prevented"
        assert "[DUPLICATE TOOL CALL]" in dup_turn.tool_observation["formatted_message"]

    @pytest.mark.asyncio
    async def test_duplicate_with_sufficient_evidence_triggers_immediate_final_synthesis(self, mock_qa_loop):
        """
        When evidence is already sufficient and model attempts a duplicate tool call:
        - The duplicate call is intercepted without tool dispatch.
        - The orchestrator immediately transitions to final answer synthesis turn.
        - The final answer is produced directly without letting the LLM wander in duplicate loops.
        """
        mock_observation = MagicMock(
            success=True,
            error=None,
            data="export function authenticate() { return true; }"
        )
        mock_qa_loop.tool_dispatch.dispatch = MagicMock(return_value=mock_observation)
        mock_qa_loop.tool_dispatch.specs = MagicMock(return_value=[])

        # Sequence of model outputs:
        # Turn 0: read_file(lib/auth.ts, 1, 100) -> executed, evidence is sufficient!
        # Turn 1: duplicate read_file(lib/auth.ts, 1, 100) -> duplicate with sufficient evidence!
        # Final answer turn: generated directly by _do_final_answer_turn!
        resp0 = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">lib/auth.ts</parameter><parameter name="start_line">1</parameter><parameter name="end_line">100</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
        )
        resp1_duplicate = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">lib/auth.ts</parameter><parameter name="start_line">1</parameter><parameter name="end_line">100</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=150, completion_tokens=30, total_tokens=180),
        )
        resp_final_synthesis = LLMResponse(
            content="Authentication validates the user token against the configured store.",
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=30, total_tokens=230),
        )

        mock_qa_loop.llm_service.generate = AsyncMock(side_effect=[resp0, resp1_duplicate, resp_final_synthesis])

        result = await mock_qa_loop.run("What does authenticate do?")

        # Tool dispatch only ran once (for Turn 0)
        assert mock_qa_loop.tool_dispatch.dispatch.call_count == 1
        # Loop terminated with final answer from synthesis
        assert "Authentication validates the user token" in result.answer
        assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
        assert mock_qa_loop.guardrails.state.evidence_sufficient is True
        assert mock_qa_loop.guardrails.state.answer_ready is True
        # Verify intercepted duplicate turn format
        dup_turn = result.turns[1]
        assert dup_turn.tool_observation["error"]["type"] == "duplicate_call_prevented"
        assert "[EVIDENCE SUFFICIENT]" in dup_turn.tool_observation["formatted_message"]

    @pytest.mark.asyncio
    async def test_duplicate_with_insufficient_evidence_provides_missing_evidence_guidance(self, mock_qa_loop):
        """
        When evidence is NOT sufficient (e.g. search found files but implementation not yet read)
        and model attempts a duplicate search call:
        - The duplicate call is intercepted without tool dispatch.
        - The agent receives targeted guidance identifying what evidence is missing (e.g. read_file).
        - The LLM can then perform the missing action.
        """
        mock_observation = MagicMock(
            success=True,
            error=None,
            data=[{"file_path": "lib/auth.ts", "line_number": 45, "snippet": "function verify()"}]
        )
        mock_qa_loop.tool_dispatch.dispatch = MagicMock(return_value=mock_observation)
        mock_qa_loop.tool_dispatch.specs = MagicMock(return_value=[])

        # Turn 0: search_repository query="verify" -> executed, evidence not sufficient yet (read_file missing)
        # Turn 1: duplicate search_repository query="verify" -> intercepted with missing evidence guidance
        # Turn 2: read_file(lib/auth.ts) -> executed
        # Turn 3: final_answer
        resp0 = LLMResponse(
            content='<tool_call><invoke name="search_repository"><parameter name="query">verify</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
        )
        resp1_duplicate = LLMResponse(
            content='<tool_call><invoke name="search_repository"><parameter name="query">verify</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=150, completion_tokens=30, total_tokens=180),
        )
        resp2_read = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">lib/auth.ts</parameter><parameter name="start_line">35</parameter><parameter name="end_line">75</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=30, total_tokens=230),
        )
        resp3_final = LLMResponse(
            content='<tool_call><invoke name="final_answer"><parameter name="answer">Verification confirms token signatures.</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=250, completion_tokens=30, total_tokens=280),
        )

        mock_qa_loop.llm_service.generate = AsyncMock(side_effect=[resp0, resp1_duplicate, resp2_read, resp3_final])

        read_observation = MagicMock(
            success=True,
            error=None,
            data="export function verify() { return jwt.verify(); }"
        )
        mock_qa_loop.tool_dispatch.dispatch = MagicMock(side_effect=[mock_observation, read_observation])

        result = await mock_qa_loop.run("How does verify work?")

        # Turn 1 intercepted as duplicate with missing evidence guidance
        dup_turn = result.turns[1]
        assert dup_turn.tool_observation["error"]["type"] == "duplicate_call_prevented"
        assert "[DUPLICATE TOOL CALL - EVIDENCE INCOMPLETE]" in dup_turn.tool_observation["formatted_message"]
        assert "Missing evidence needed:" in dup_turn.tool_observation["formatted_message"]
        assert "read_file" in dup_turn.tool_observation["formatted_message"]

        # Final answer succeeded after following missing evidence guidance
        assert "Verification confirms token signatures." in result.answer
        assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION

    def test_read_file_coverage_and_unread_slice_calculation(self):
        """
        Validates AgentState line-coverage interval tracking:
        1. Slices [1-25], [26-46], [47-67], [68-96] are recorded and merged to [1-96].
        2. When model asks for 1-200, system calculates unread slice as (97, 200).
        3. When entire range is already inspected (e.g. 1-50), get_unread_slice_for_request returns None.
        4. Summary reports exact read and unread intervals.
        """
        guardrails = LoopGuardrails()
        path = "app/controllers/trial.js"

        # Record successive sliced reads
        guardrails.record_tool_result("read_file", {"path": path, "start_line": 1, "end_line": 25}, success=True, data={"path": path, "start_line": 1, "end_line": 25, "total_lines": 158}, turn_index=1)
        guardrails.record_tool_result("read_file", {"path": path, "start_line": 26, "end_line": 46}, success=True, data={"path": path, "start_line": 26, "end_line": 46, "total_lines": 158}, turn_index=2)
        guardrails.record_tool_result("read_file", {"path": path, "start_line": 47, "end_line": 67}, success=True, data={"path": path, "start_line": 47, "end_line": 67, "total_lines": 158}, turn_index=3)
        guardrails.record_tool_result("read_file", {"path": path, "start_line": 68, "end_line": 96}, success=True, data={"path": path, "start_line": 68, "end_line": 96, "total_lines": 158}, turn_index=4)

        reads, unreads, total = guardrails.state.get_read_ranges_summary(path)
        assert reads == [(1, 96)]
        assert unreads == [(97, 158)]
        assert total == 158

        # If model requests 1-200, unread slice should be (97, 200)
        slice_result = guardrails.state.get_unread_slice_for_request(path, 1, 200)
        assert slice_result == (97, 200)

        # If model requests 1-96 (already read), slice is None
        assert guardrails.state.get_unread_slice_for_request(path, 1, 96) is None
        assert guardrails.state.get_unread_slice_for_request(path, 10, 50) is None

        # Duplicate feedback provides exact read/unread state
        is_dup, feedback = guardrails.is_duplicate_call("read_file", {"path": path, "start_line": 1, "end_line": 25})
        assert is_dup is True
        assert "Already inspected: lines 1-96" in feedback
        assert "Still unread: lines 97-158" in feedback
        assert "Do not repeat identical calls" in feedback

    @pytest.mark.asyncio
    async def test_qaloop_smart_read_adjusts_partially_read_file(self, mock_qa_loop):
        """
        When model has read lines 1-96 and later calls read_file with 1-200:
        QALoop automatically adjusts arguments to unread range (97-200)
        and executes the read instead of blocking as a duplicate!
        """
        # Pre-seed coverage in guardrails state
        path = "controllers/trial.js"
        mock_qa_loop.guardrails.state.record_read_range(path, 1, 96, total_lines=158)

        mock_observation = MagicMock(
            success=True,
            error=None,
            data={"path": path, "start_line": 97, "end_line": 158, "total_lines": 158, "raw_text": "lines 97-158"}
        )
        mock_qa_loop.tool_dispatch.dispatch = MagicMock(return_value=mock_observation)
        mock_qa_loop.tool_dispatch.specs = MagicMock(return_value=[])

        resp0_adjust = LLMResponse(
            content=f'<tool_call><invoke name="read_file"><parameter name="path">{path}</parameter><parameter name="start_line">1</parameter><parameter name="end_line">200</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
        )
        resp1_final = LLMResponse(
            content='<tool_call><invoke name="final_answer"><parameter name="answer">Analysis complete.</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=30, total_tokens=230),
        )

        mock_qa_loop.llm_service.generate = AsyncMock(side_effect=[resp0_adjust, resp1_final])

        result = await mock_qa_loop.run("Analyze trial.js")

        # Tool dispatch was called with start_line=97, NOT blocked!
        assert mock_qa_loop.tool_dispatch.dispatch.call_count == 1
        call_args = mock_qa_loop.tool_dispatch.dispatch.call_args[0][1]
        assert call_args["start_line"] == 97
        assert call_args["end_line"] == 200
        assert "Analysis complete." in result.answer
