"""Tests for OpenRouter native tool calling integration."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Any, Dict

from backend.ai.providers.openrouter import OpenRouterProvider
from backend.ai.schemas import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    Tool,
    ToolCall,
)


@pytest.fixture
def provider():
    """Create OpenRouter provider instance."""
    return OpenRouterProvider(api_key="test-key", model="gpt-4-turbo")


@pytest.fixture
def sample_tools():
    """Create sample tools for testing."""
    return [
        Tool(
            name="search_code",
            description="Search for code patterns",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path_pattern": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="read_file",
            description="Read a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        ),
    ]


@pytest.fixture
def sample_request(sample_tools):
    """Create a sample LLM request with tools."""
    return LLMRequest(
        messages=[
            Message(role=MessageRole.USER, content="Search for authentication code"),
        ],
        model="gpt-4-turbo",
        temperature=0.2,
        max_tokens=8192,
        tools=sample_tools,
    )


class TestOpenRouterBuildBody:
    """Tests for _build_body method with tools support."""

    def test_build_body_without_tools(self, provider):
        """Test request body building without tools."""
        request = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Hello")],
            model="gpt-4",
            temperature=0.2,
            max_tokens=1000,
        )
        body = provider._build_body(request)

        assert body["model"] == "gpt-4"
        assert body["temperature"] == 0.2
        assert body["max_tokens"] == 1000
        assert "tools" not in body

    def test_build_body_with_tools(self, provider, sample_request):
        """Test request body building with tools."""
        body = provider._build_body(sample_request)

        # Verify tools array exists and has correct structure
        assert "tools" in body
        assert len(body["tools"]) == 2

        # Verify first tool structure
        tool0 = body["tools"][0]
        assert tool0["type"] == "function"
        assert tool0["function"]["name"] == "search_code"
        assert tool0["function"]["description"] == "Search for code patterns"
        assert "parameters" in tool0["function"]

        # Verify second tool
        tool1 = body["tools"][1]
        assert tool1["type"] == "function"
        assert tool1["function"]["name"] == "read_file"

    def test_build_body_uses_default_model(self, provider):
        """Test that default model is used when request model is None."""
        request = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Hello")],
            model=None,
            temperature=0.2,
            max_tokens=1000,
        )
        body = provider._build_body(request)
        assert body["model"] == "gpt-4-turbo"  # provider's default

    def test_build_body_tools_parameter_schema(self, provider):
        """Test that tool parameters schemas are preserved correctly."""
        tool_with_enum = Tool(
            name="test_tool",
            description="Test tool",
            parameters={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["FORWARD", "REVERSE"],
                    }
                },
                "required": ["direction"],
            },
        )

        request = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4",
            temperature=0.2,
            max_tokens=1000,
            tools=[tool_with_enum],
        )
        body = provider._build_body(request)

        params = body["tools"][0]["function"]["parameters"]
        assert params["properties"]["direction"]["enum"] == ["FORWARD", "REVERSE"]


class TestOpenRouterResponseParsing:
    """Tests for response parsing with native tool calls."""

    @pytest.mark.asyncio
    async def test_parse_response_with_tool_call(self, provider, sample_request):
        """Test parsing response with native tool call."""
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "gpt-4-turbo",
            "choices": [
                {
                    "message": {
                        "content": None,  # Pure tool call, no text
                        "tool_calls": [
                            {
                                "id": "call_abc123",
                                "type": "function",
                                "function": {
                                    "name": "search_code",
                                    "arguments": '{"query": "authentication", "path_pattern": "backend/**"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            response = await provider.generate(sample_request)

        # Verify response structure
        assert response.content == ""  # No text content
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1

        # Verify tool call details
        tc = response.tool_calls[0]
        assert tc.tool_name == "search_code"
        assert tc.parameters == {"query": "authentication", "path_pattern": "backend/**"}
        assert tc.tool_call_id == "call_abc123"

        # Verify usage is preserved
        assert response.usage.prompt_tokens == 100
        assert response.usage.completion_tokens == 50

    @pytest.mark.asyncio
    async def test_parse_response_with_text_and_tool_call(self, provider, sample_request):
        """Test parsing response with both text and tool call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "gpt-4-turbo",
            "choices": [
                {
                    "message": {
                        "content": "Let me search for that...",
                        "tool_calls": [
                            {
                                "id": "call_xyz789",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path": "backend/auth.py"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            response = await provider.generate(sample_request)

        # Both content and tool_calls should be present
        assert response.content == "Let me search for that..."
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].tool_name == "read_file"

    @pytest.mark.asyncio
    async def test_parse_response_with_multiple_tool_calls(self, provider, sample_request):
        """Test parsing response with multiple tool calls (one-tool-per-turn will handle)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "gpt-4-turbo",
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "search_code",
                                    "arguments": '{"query": "auth"}',
                                },
                            },
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path": "main.py"}',
                                },
                            },
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            response = await provider.generate(sample_request)

        # Both tool calls should be captured (QALoop will consume only first)
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 2
        assert response.tool_calls[0].tool_name == "search_code"
        assert response.tool_calls[1].tool_name == "read_file"

    @pytest.mark.asyncio
    async def test_parse_response_text_only(self, provider):
        """Test parsing response with no tool calls (text-only response)."""
        request = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="What is Python?")],
            model="gpt-4",
            temperature=0.2,
            max_tokens=1000,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "gpt-4",
            "choices": [
                {
                    "message": {
                        "content": "Python is a programming language.",
                        "tool_calls": None,  # No tool calls
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            response = await provider.generate(request)

        assert response.content == "Python is a programming language."
        assert response.tool_calls is None  # No tool calls

    @pytest.mark.asyncio
    async def test_parse_response_arguments_as_dict(self, provider, sample_request):
        """Test parsing when arguments come as dict instead of JSON string."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "gpt-4-turbo",
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_dict",
                                "type": "function",
                                "function": {
                                    "name": "search_code",
                                    # Arguments already as dict, not JSON string
                                    "arguments": {"query": "auth", "path_pattern": "backend/**"},
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            response = await provider.generate(sample_request)

        tc = response.tool_calls[0]
        assert tc.parameters == {"query": "auth", "path_pattern": "backend/**"}

    @pytest.mark.asyncio
    async def test_parse_response_generates_tool_call_id(self, provider, sample_request):
        """Test that tool_call_id is generated when not provided by API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "gpt-4-turbo",
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                # No "id" field
                                "type": "function",
                                "function": {
                                    "name": "search_code",
                                    "arguments": '{"query": "auth"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            response = await provider.generate(sample_request)

        # Tool call ID should be generated
        tc = response.tool_calls[0]
        assert tc.tool_call_id == "openrouter-0"


class TestOpenRouterNoToolsRegression:
    """Regression tests to ensure backward compatibility when tools are not set."""

    @pytest.mark.asyncio
    async def test_generate_without_tools_unchanged(self, provider):
        """Verify that non-tool requests work exactly as before."""
        request = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Say hello")],
            model="gpt-4",
            temperature=0.2,
            max_tokens=1000,
            tools=None,  # No tools
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "gpt-4",
            "choices": [
                {
                    "message": {
                        "content": "Hello! How can I help you?",
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            response = await provider.generate(request)

        assert response.content == "Hello! How can I help you?"
        assert response.tool_calls is None
        assert response.provider == "openrouter"

    def test_build_body_without_tools_no_tools_key(self, provider):
        """Verify that 'tools' key is not in body when tools=None."""
        request = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Hello")],
            model="gpt-4",
            temperature=0.2,
            max_tokens=1000,
            tools=None,
        )
        body = provider._build_body(request)

        assert "tools" not in body
        assert body["model"] == "gpt-4"
        assert body["temperature"] == 0.2
