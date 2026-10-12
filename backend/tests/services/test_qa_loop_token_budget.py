"""
Tests for token-budget context protection and preflight compaction in QALoop.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agent.loop.contracts import AgentLoopConfig, StopReason
from backend.ai.schemas import LLMRequest, LLMResponse, TokenUsage
from backend.services.qa_loop import QALoop, SystemPromptParts
from backend.services.qa_protocol import QAProtocolAdapter


@pytest.fixture
def qa_loop_instance():
    llm_service = MagicMock()
    llm_service.providers = [MagicMock(provider_name="groq")]
    tool_dispatch = MagicMock()
    config = AgentLoopConfig()
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


class TestQALoopTokenBudgeting:
    def test_provider_profile_derivation_groq(self, qa_loop_instance):
        """Verify the 4 distinct constraints are properly derived for Groq."""
        profile = qa_loop_instance._get_provider_budget_profile()
        assert profile["provider"] == "groq"
        assert profile["context_window"] == 65536
        assert profile["input_tpm"] == 8000
        assert profile["single_request_limit"] == 8000
        assert profile["safe_budget"] < 8000  # must leave safety margin + output + control
        assert profile["safe_budget"] > 0

    def test_deterministic_compaction_deduplicates_reads(self, qa_loop_instance):
        """Verify deterministic compaction deduplicates earlier file reads."""
        messages = [
            {"role": "user", "content": "What is the architecture?"},
            {"role": "assistant", "content": "read_file(path='ARCHITECTURE.md', start_line=1, end_line=50)"},
            {"role": "tool", "content": "Showing 50 lines of ARCHITECTURE.md: line 1 to 50\n" + ("code\n" * 40)},
            {"role": "assistant", "content": "read_file(path='ARCHITECTURE.md', start_line=51, end_line=100)"},
            {"role": "tool", "content": "Showing 50 lines of ARCHITECTURE.md: line 51 to 100\n" + ("code\n" * 40)},
        ]

        compacted = qa_loop_instance._compact_messages_deterministically(messages, target_tokens=1000)
        assert len(compacted) == len(messages)
        # First observation should have been deduplicated
        assert "[Deduplicated older observation" in compacted[2]["content"] or "[Older observation compacted" in compacted[2]["content"]
        # Latest observation should be retained
        assert "Showing 50 lines of ARCHITECTURE.md: line 51 to 100" in compacted[4]["content"]

    def test_deterministic_compaction_real_tool_format_and_coverage(self, qa_loop_instance):
        """Verify compaction handles [read_file] path lines format and retains coverage ranges."""
        messages = [
            {"role": "user", "content": "How does trial work?"},
            {"role": "assistant", "content": '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "controllers/trial.js", "start_line": 1, "end_line": 13}}'},
            {"role": "user", "content": "[read_file] controllers/trial.js lines 1-13: 566 chars (total: 158)\nconst jwt = require('jwt');\n" * 10},
            {"role": "assistant", "content": '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "controllers/trial.js", "start_line": 14, "end_line": 24}}'},
            {"role": "user", "content": "[read_file] controllers/trial.js lines 14-24: 1075 chars (total: 158)\nconst fingerprint = ...\n" * 15},
            {"role": "assistant", "content": '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "controllers/trial.js", "start_line": 25, "end_line": 158}}'},
            {"role": "user", "content": "[read_file] controllers/trial.js lines 25-158: 10604 chars (total: 158)\nexports.joinTrial = ...\n" * 50},
        ]

        compacted = qa_loop_instance._compact_messages_deterministically(messages, target_tokens=2000)
        assert len(compacted) == len(messages)
        # Earlier observations for controllers/trial.js should have deduplicated summary with coverage info
        assert "[Deduplicated older observation for 'controllers/trial.js'" in compacted[2]["content"]
        assert "1-13" in compacted[2]["content"]
        # Latest observation (lines 25-158) should be preserved
        assert "lines 25-158" in compacted[6]["content"]

    @pytest.mark.asyncio
    async def test_preflight_blocks_oversized_request_and_compacts(self, qa_loop_instance):
        """
        Verify that when a conversation reaches excessive tokens,
        preflight runs deterministic compaction before calling llm_service.generate.
        """
        # Huge tool output that would overflow Groq's 8K safe budget
        huge_observation = "line = value\n" * 2500  # ~30,000 characters ≈ 7,500 tokens
        qa_loop_instance.llm_service.generate = AsyncMock(
            return_value=LLMResponse(
                content='{"action": "final_answer", "answer": "Done"}',
                model="openai/gpt-oss-120b",
                provider="groq",
                usage=TokenUsage(prompt_tokens=4000, completion_tokens=50, total_tokens=4050),
            )
        )
        qa_loop_instance.tool_dispatch.specs = MagicMock(return_value=[])

        # Pre-seed loop with heavy history
        result = await qa_loop_instance.run("Explain system architecture")
        assert result.answer == "Done"
        assert qa_loop_instance.llm_service.generate.called
        # Check call arguments
        call_req = qa_loop_instance.llm_service.generate.call_args[0][0]
        assert isinstance(call_req, LLMRequest)

    def test_explicit_provider_routing_groq_not_affected_by_gemini_key(self, qa_loop_instance):
        """A. Groq request selects Groq token counter and GeminiTokenCounter is NOT called, even if GEMINI_API_KEY is set."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "AIzaSyFakeKeyWithHighPriority"}):
            with patch("backend.ai.tokencount.registry._groq_counter.count_request", new_callable=AsyncMock) as mock_groq_req:
                with patch("backend.ai.tokencount.registry._gemini_counter.count_request", new_callable=AsyncMock) as mock_gemini_req:
                    from backend.ai.tokencount.base import RequestTokenCount
                    mock_groq_req.return_value = RequestTokenCount(total_tokens=100, is_exact=False, method="groq_test")

                    qa_loop_instance.provider = "groq"
                    qa_loop_instance.model = "openai/gpt-oss-120b"
                    profile = qa_loop_instance._get_provider_budget_profile()

                    assert profile["provider"] == "groq"
                    assert profile["model"] == "openai/gpt-oss-120b"

    def test_explicit_provider_routing_gemini_uses_configured_model(self):
        """B. Gemini request selects gemini provider and uses exact configured model (e.g. gemini-3.8-flash)."""
        llm_service = MagicMock()
        llm_service.providers = [MagicMock(provider_name="gemini")]
        system_parts = SystemPromptParts(
            grounding_and_protocol_text="", tool_catalog_text="", rim_metadata_text="", full_text=""
        )
        loop = QALoop(
            llm_service=llm_service,
            tool_dispatch=MagicMock(),
            config=AgentLoopConfig(),
            system_prompt_parts=system_parts,
            model="gemini-3.8-flash",
            provider="gemini",
        )
        profile = loop._get_provider_budget_profile()
        assert profile["provider"] == "gemini"
        assert profile["model"] == "gemini-3.8-flash"
        assert profile["context_window"] == 1048576

    def test_missing_provider_does_not_silently_fallback_to_gemini(self):
        """D. Missing provider and unknown model raises ValueError, never silently defaults to Gemini."""
        llm_service = MagicMock()
        llm_service.providers = []  # No providers attached
        system_parts = SystemPromptParts(
            grounding_and_protocol_text="", tool_catalog_text="", rim_metadata_text="", full_text=""
        )
        with patch.dict("os.environ", {"GEMINI_API_KEY": "AIzaSyFakeKey"}):
            loop = QALoop(
                llm_service=llm_service,
                tool_dispatch=MagicMock(),
                config=AgentLoopConfig(),
                system_prompt_parts=system_parts,
                model=None,
                provider=None,
            )
            with pytest.raises(ValueError, match="Provider information is required"):
                loop._get_provider_budget_profile()
