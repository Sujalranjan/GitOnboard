"""Integration tests for native tool calling support across providers."""
import pytest
from unittest.mock import MagicMock

from backend.ai.schemas import LLMResponse, ToolCall
from backend.services.qa_protocol import QAProtocolAdapter


class TestParseResponseFromLLMResponse:
    """Tests for QAProtocolAdapter.parse_response_from_llm_response() with native tool calls."""

    def test_native_tool_call_single(self):
        """Test parsing native tool call (e.g., from Gemini or OpenRouter)."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        # Simulate response with native tool_calls (from Gemini or OpenRouter)
        llm_response = LLMResponse(
            content="",
            model="gpt-4",
            provider="gemini",
            tool_calls=[
                ToolCall(
                    tool_name="search_code",
                    parameters={"query": "auth"},
                    tool_call_id="gemini-0",
                ),
            ],
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        assert result["action"] == "tool_call"
        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool_name"] == "search_code"
        assert result["tool_calls"][0]["arguments"] == {"query": "auth"}

    def test_native_tool_call_multiple_takes_first(self):
        """Test that multiple native tool calls returns only the first (one-tool-per-turn)."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        # Simulate response with multiple native tool_calls
        llm_response = LLMResponse(
            content="",
            model="gpt-4",
            provider="openrouter",
            tool_calls=[
                ToolCall(
                    tool_name="search_code",
                    parameters={"query": "auth"},
                    tool_call_id="openrouter-0",
                ),
                ToolCall(
                    tool_name="read_file",
                    parameters={"path": "main.py"},
                    tool_call_id="openrouter-1",
                ),
            ],
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        # Should return only first tool call (one-tool-per-turn semantics)
        assert result["action"] == "tool_call"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool_name"] == "search_code"

    def test_native_tool_call_empty_content(self):
        """Test native tool call with empty content (pure function call)."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        llm_response = LLMResponse(
            content="",  # Empty content
            model="gpt-4",
            provider="openrouter",
            tool_calls=[
                ToolCall(
                    tool_name="get_tree",
                    parameters={"path": "backend", "depth": 2},
                    tool_call_id="openrouter-0",
                ),
            ],
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        assert result["action"] == "tool_call"
        assert result["tool_calls"][0]["arguments"] == {"path": "backend", "depth": 2}

    def test_no_native_tools_falls_through_to_text_parsing(self):
        """Test that when tool_calls is None, falls through to text parsing."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        # Simulate response with text-format tool call (no native tool_calls)
        llm_response = LLMResponse(
            content='{"action": "tool_call", "tool_name": "search_code", "arguments": {"query": "auth"}}',
            model="gpt-4",
            provider="openrouter",
            tool_calls=None,  # No native tool calls
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        # Should parse the text and return wrapped in tool_calls list
        assert result["action"] == "tool_call"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool_name"] == "search_code"

    def test_final_answer_passed_through_unchanged(self):
        """Test that final_answer responses pass through unchanged."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        llm_response = LLMResponse(
            content='{"action": "final_answer", "answer": "The system uses FastAPI"}',
            model="gpt-4",
            provider="openrouter",
            tool_calls=None,
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        assert result["action"] == "final_answer"
        assert "answer" in result
        assert "tool_calls" not in result

    def test_malformed_response_passed_through_unchanged(self):
        """Test that malformed responses pass through unchanged."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        llm_response = LLMResponse(
            content="This is not valid JSON",
            model="gpt-4",
            provider="openrouter",
            tool_calls=None,
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        # Should pass through as malformed error
        assert result.get("action") == "malformed"
        assert "error" in result

    def test_qwen_hermes_xml_format_still_works(self):
        """Test that Qwen/Hermes XML parsing still works (backward compatibility)."""
        adapter = QAProtocolAdapter(model_id="qwen3:4b-instruct")

        # Simulate Qwen response with Hermes XML format
        hermes_response = """<tool_call>
<invoke name="search_code">
<parameter name="query">authentication</parameter>
</invoke>
</tool_call>"""

        llm_response = LLMResponse(
            content=hermes_response,
            model="qwen3:4b-instruct",
            provider="ollama",
            tool_calls=None,  # No native tool calls (Qwen uses text format)
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        assert result["action"] == "tool_call"
        assert result["tool_calls"][0]["tool_name"] == "search_code"

    def test_native_tools_override_text_parsing(self):
        """Test that native tool_calls take precedence over text content."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        # Response has both native tool_calls AND text content
        # Native tool_calls should be used
        llm_response = LLMResponse(
            content='{"action": "tool_call", "tool_name": "wrong_tool"}',
            model="gpt-4",
            provider="openrouter",
            tool_calls=[
                ToolCall(
                    tool_name="correct_tool",
                    parameters={"key": "value"},
                    tool_call_id="call_123",
                ),
            ],
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        # Should use the native tool call, not the text
        assert result["tool_calls"][0]["tool_name"] == "correct_tool"

    def test_empty_tool_calls_list_falls_through(self):
        """Test that empty tool_calls list falls through to text parsing."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        llm_response = LLMResponse(
            content='{"action": "final_answer", "answer": "No tools needed"}',
            model="gpt-4",
            provider="openrouter",
            tool_calls=[],  # Empty list
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        # Should fall through to text parsing
        assert result["action"] == "final_answer"


class TestProviderToolCallingBackwardCompatibility:
    """Tests to ensure existing provider behavior is preserved."""

    def test_openrouter_without_native_tools_unchanged(self):
        """Verify OpenRouter without tool_calls still works as before."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        # Simulate old-style OpenRouter response (text format)
        llm_response = LLMResponse(
            content='{"action": "tool_call", "tool_name": "search_code", "arguments": {"query": "test"}}',
            model="gpt-4",
            provider="openrouter",
            tool_calls=None,
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        assert result["action"] == "tool_call"
        assert result["tool_calls"][0]["tool_name"] == "search_code"

    def test_gemini_native_tools_format(self):
        """Test Gemini native tool calling format."""
        adapter = QAProtocolAdapter(model_id="claude-3-5-sonnet")

        # Simulate Gemini's native tool call format
        llm_response = LLMResponse(
            content="I'll search for that...",
            model="gemini-2.0-flash",
            provider="gemini",
            tool_calls=[
                ToolCall(
                    tool_name="query_rim",
                    parameters={"entity_name": "LLMService", "relationship_type": "IMPORTS"},
                    tool_call_id="gemini-0",
                ),
            ],
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        assert result["action"] == "tool_call"
        assert result["tool_calls"][0]["tool_name"] == "query_rim"
        assert result["tool_calls"][0]["arguments"]["entity_name"] == "LLMService"
