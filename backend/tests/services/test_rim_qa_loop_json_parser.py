"""
Tests for the fixed RIM QA Loop JSON parser.

This test suite validates that the JSON parser can handle nested objects
in tool arguments (which the old regex-based parser failed on).
"""
import pytest
from backend.services.rim_qa_loop import RIMQALoop
from backend.agent.loop.contracts import AgentLoopConfig
from backend.ai.service import LLMService
from backend.services.rim_tool_dispatch import ToolDispatchTable
from backend.services.rim_qa_protocol import SystemPromptParts


@pytest.fixture
def dummy_loop():
    """Create a RIMQALoop instance for testing (doesn't need real LLM/tools)."""
    # We only need to test _parse_response, which doesn't use these
    config = AgentLoopConfig()
    loop = RIMQALoop(
        llm_service=None,  # Not used in _parse_response
        tool_dispatch=None,  # Not used in _parse_response
        config=config,
        system_prompt_parts=SystemPromptParts(
            grounding_and_protocol_text="",
            tool_catalog_text="",
            rim_metadata_text="",
            full_text=""
        )
    )
    return loop


class TestJSONParserFlatObjects:
    """Test parsing of flat JSON objects (should always work)."""

    def test_parse_flat_final_answer(self, dummy_loop):
        """Parse a final_answer with flat JSON."""
        text = '{"action": "final_answer", "answer": "hello world"}'
        result = dummy_loop._parse_response(text)
        assert result["action"] == "final_answer"
        assert result["answer"] == "hello world"

    def test_parse_flat_tool_call(self, dummy_loop):
        """Parse a tool_call with simple string arguments."""
        text = '{"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "login"}}'
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "search_repository"
        assert result["arguments"] == {"query": "login"}


class TestJSONParserNestedObjects:
    """Test parsing of nested JSON objects (CRITICAL FIX)."""

    def test_parse_read_file_with_nested_args(self, dummy_loop):
        """Parse read_file tool call with nested arguments.

        This is the critical test case that was failing with the old regex parser.
        The old regex r'\{[^{}]*\}' couldn't match this because it forbids
        any { or } characters in the middle.
        """
        text = '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/main.py", "start_line": 1, "end_line": 100}}'
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "read_file"
        assert result["arguments"]["path"] == "src/main.py"
        assert result["arguments"]["start_line"] == 1
        assert result["arguments"]["end_line"] == 100

    def test_parse_query_rim_with_nested_args(self, dummy_loop):
        """Parse query_rim tool call with nested arguments."""
        text = '{"action": "tool_call", "tool_name": "query_rim", "arguments": {"entity_name": "authenticate", "relationship_type": "CALLS", "direction": "FORWARD"}}'
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "query_rim"
        assert result["arguments"]["entity_name"] == "authenticate"
        assert result["arguments"]["relationship_type"] == "CALLS"

    def test_parse_deeply_nested_json(self, dummy_loop):
        """Parse JSON with multiple levels of nesting."""
        # Hypothetical deeply nested structure
        text = '{"action": "tool_call", "tool_name": "custom_tool", "arguments": {"filters": {"type": "function", "scope": {"file": "main.py"}}}}'
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "custom_tool"
        assert result["arguments"]["filters"]["type"] == "function"
        assert result["arguments"]["filters"]["scope"]["file"] == "main.py"


class TestJSONParserWithSurroundingText:
    """Test parsing JSON embedded in surrounding text."""

    def test_parse_with_explanation_before(self, dummy_loop):
        """Model provides explanation, then JSON."""
        text = '''Let me search for the authentication logic.
        {"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "authentication"}}
        I think this will find the relevant code.'''
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["arguments"]["query"] == "authentication"

    def test_parse_with_explanation_after(self, dummy_loop):
        """Model provides JSON, then explanation."""
        text = '''{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/auth.py", "start_line": 1, "end_line": 50}}
        This should show me the authentication implementation.'''
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["arguments"]["path"] == "src/auth.py"

    def test_parse_with_markdown_code_fence(self, dummy_loop):
        """Model wraps JSON in markdown code fence."""
        text = '''Here's the tool call:
        ```json
        {"action": "tool_call", "tool_name": "get_symbol", "arguments": {"name": "login"}}
        ```'''
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["arguments"]["name"] == "login"


class TestJSONParserMalformed:
    """Test handling of malformed input."""

    def test_malformed_no_json(self, dummy_loop):
        """No JSON in response."""
        text = "The login system works by authenticating users."
        result = dummy_loop._parse_response(text)
        assert result["action"] == "malformed"
        assert "no valid" in result.get("error", "").lower() and "json" in result.get("error", "").lower()

    def test_malformed_no_action_field(self, dummy_loop):
        """JSON present but no 'action' field."""
        text = '{"tool_name": "search", "query": "auth"}'
        result = dummy_loop._parse_response(text)
        assert result["action"] == "malformed"

    def test_malformed_unknown_action(self, dummy_loop):
        """JSON has action field but unknown value."""
        text = '{"action": "edit_code", "code": "..."}'
        result = dummy_loop._parse_response(text)
        assert result["action"] == "malformed"

    def test_malformed_invalid_json(self, dummy_loop):
        """Invalid JSON syntax."""
        text = '{"action": "tool_call", "tool_name": "read_file", "arguments": {path: "src/main.py"}}'  # Missing quotes on 'path'
        result = dummy_loop._parse_response(text)
        assert result["action"] == "malformed"


class TestJSONParserRealWorldExamples:
    """Test with realistic model outputs."""

    def test_qwen_response_with_tool_call(self, dummy_loop):
        """Realistic Qwen model response with tool call."""
        text = '''Let me search for the authentication logic in the repository first.

{"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "login authenticate"}}'''
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "search_repository"
        assert "login" in result["arguments"]["query"]

    def test_qwen_response_with_final_answer(self, dummy_loop):
        """Realistic Qwen model response with final answer."""
        text = '''Based on examining the code, I found the following:

{"action": "final_answer", "answer": "The login component authenticates users by validating credentials against the user database and issuing a session token."}'''
        result = dummy_loop._parse_response(text)
        assert result["action"] == "final_answer"
        assert "authenticates" in result["answer"]

    def test_coder_response_with_multiple_args(self, dummy_loop):
        """Realistic Qwen Coder response with complex arguments."""
        text = '''Now I'll read the specific function:

{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/services/authentication.py", "start_line": 42, "end_line": 120}}

Let me examine the implementation details.'''
        result = dummy_loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["arguments"]["path"] == "src/services/authentication.py"
        assert result["arguments"]["start_line"] == 42
        assert result["arguments"]["end_line"] == 120


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
