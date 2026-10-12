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

    def test_local_ollama_falls_through_to_text_parsing(self):
        """Test that for local ollama models (native_tools=False), text JSON is parsed."""
        adapter = QAProtocolAdapter(model_id="local-model", native_tools=False)

        # Simulate response with text-format tool call (no native tool_calls)
        llm_response = LLMResponse(
            content='{"action": "tool_call", "tool_name": "search_code", "arguments": {"query": "auth"}}',
            model="local-model",
            provider="ollama",
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
            content="The system uses FastAPI",
            model="gpt-4",
            provider="openrouter",
            tool_calls=None,
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        assert result["action"] == "final_answer"
        assert result["answer"] == "The system uses FastAPI"
        assert "tool_calls" not in result

    def test_cloud_models_no_fallback_treats_content_as_final_answer(self):
        """Test that cloud models (Groq, OpenRouter, Gemini) do NOT fall back to JSON text parsing."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        llm_response = LLMResponse(
            content="This is natural language answering the user directly.",
            model="gpt-4",
            provider="openrouter",
            tool_calls=None,
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        # For cloud models: no native tool call means it's a final answer directly (no fallback)
        assert result.get("action") == "final_answer"
        assert result.get("answer") == "This is natural language answering the user directly."

    def test_qwen_hermes_xml_format_still_works(self):
        """Test that local Qwen/Hermes XML parsing works for local ollama."""
        adapter = QAProtocolAdapter(model_id="qwen3:4b-instruct", native_tools=False)

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
            tool_calls=None,  # No native tool calls (local Qwen uses Hermes format)
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
        """Test that empty tool_calls list returns final_answer directly for cloud models."""
        adapter = QAProtocolAdapter(model_id="gpt-4")

        llm_response = LLMResponse(
            content="No tools needed",
            model="gpt-4",
            provider="openrouter",
            tool_calls=[],  # Empty list
        )

        result = adapter.parse_response_from_llm_response(llm_response)

        assert result["action"] == "final_answer"
        assert result["answer"] == "No tools needed"


class TestProviderToolCallingBackwardCompatibility:
    """Tests to ensure cloud providers use native tool calling."""

    def test_groq_native_tools_format(self):
        """Test Groq native tool calling format."""
        adapter = QAProtocolAdapter(model_id="openai/gpt-oss-120b")
        assert adapter.is_native is True
        assert adapter.is_qwen is False

        llm_response = LLMResponse(
            content="",
            model="openai/gpt-oss-120b",
            provider="groq",
            tool_calls=[
                ToolCall(
                    tool_name="read_file",
                    parameters={"path": "backend/config.py"},
                    tool_call_id="groq-0",
                ),
            ],
        )

        result = adapter.parse_response_from_llm_response(llm_response)
        assert result["action"] == "tool_call"
        assert result["tool_calls"][0]["tool_name"] == "read_file"
        assert result["tool_calls"][0]["arguments"]["path"] == "backend/config.py"

    def test_gemini_native_tools_format(self):
        """Test Gemini native tool calling format."""
        adapter = QAProtocolAdapter(model_id="gemini-2.0-flash")
        assert adapter.is_native is True

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

    def test_ollama_cloud_native_tools_format(self):
        """Test Ollama cloud native tool calling format."""
        adapter = QAProtocolAdapter(model_id="custom-cloud", provider="ollama_cloud")
        assert adapter.is_native is True

        llm_response = LLMResponse(
            content="",
            model="custom-cloud",
            provider="ollama_cloud",
            tool_calls=[
                ToolCall(
                    tool_name="get_tree",
                    parameters={},
                    tool_call_id="ollama-0",
                ),
            ],
        )

        result = adapter.parse_response_from_llm_response(llm_response)
        assert result["action"] == "tool_call"
        assert result["tool_calls"][0]["tool_name"] == "get_tree"

