"""Unit tests for GroqProvider adapter."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel

import httpx

from backend.ai.providers.groq import GroqProvider, DEFAULT_MODEL, MAX_REQUESTS_PER_MINUTE
from backend.ai.schemas import LLMRequest, Message, MessageRole, NonRetriableError, RetriableError, Tool


class SampleOutput(BaseModel):
    summary: str
    score: int


@pytest.fixture
def groq_provider():
    provider = GroqProvider(api_key="test-groq-key")
    # Reset request times and token usages for test isolation
    GroqProvider._request_times = []
    GroqProvider._token_usages = []
    GroqProvider._cooldown_until = 0.0
    return provider


def test_groq_provider_initialization():
    provider = GroqProvider(api_key="my-key")
    assert provider.provider_name == "groq"
    assert provider.default_model == "openai/gpt-oss-120b"
    assert provider.api_key == "my-key"

    custom_provider = GroqProvider(api_key="my-key", model="custom-model")
    assert custom_provider.default_model == "custom-model"


@pytest.mark.asyncio
async def test_groq_generate_success(groq_provider):
    mock_response_data = {
        "id": "chatcmpl-123",
        "model": "openai/gpt-oss-120b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello from Groq!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 8,
            "total_tokens": 23,
        },
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = httpx.Headers({
        "x-ratelimit-remaining-requests": "999",
        "x-ratelimit-remaining-tokens": "7980",
        "x-ratelimit-reset-requests": "2m30s",
        "x-ratelimit-reset-tokens": "5.2s",
    })
    mock_resp.json.return_value = mock_response_data

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Hello")],
            temperature=0.2,
            max_tokens=100,
        )
        res = await groq_provider.generate(req)

        assert res.content == "Hello from Groq!"
        assert res.model == "openai/gpt-oss-120b"
        assert res.provider == "groq"
        assert res.usage.total_tokens == 23
        assert res.usage.prompt_tokens == 15
        assert res.usage.completion_tokens == 8


@pytest.mark.asyncio
async def test_groq_generate_tool_calls(groq_provider):
    mock_response_data = {
        "id": "chatcmpl-tool",
        "model": "openai/gpt-oss-120b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "search_code",
                                "arguments": json.dumps({"query": "login"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = httpx.Headers({})
    mock_resp.json.return_value = mock_response_data

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        tool = Tool(
            name="search_code",
            description="Search repository code",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        req = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="find login")],
            tools=[tool],
        )
        res = await groq_provider.generate(req)

        assert res.tool_calls is not None
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0].tool_name == "search_code"
        assert res.tool_calls[0].parameters == {"query": "login"}
        assert res.tool_calls[0].tool_call_id == "call_123"


@pytest.mark.asyncio
async def test_groq_generate_structured(groq_provider):
    mock_response_data = {
        "id": "chatcmpl-struct",
        "model": "openai/gpt-oss-120b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"summary": "Great analysis", "score": 95}),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = httpx.Headers({})
    mock_resp.json.return_value = mock_response_data

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Evaluate this code")],
        )
        result = await groq_provider.generate_structured(req, SampleOutput)

        assert isinstance(result, SampleOutput)
        assert result.summary == "Great analysis"
        assert result.score == 95


@pytest.mark.asyncio
async def test_groq_rate_limit_429_retry_after(groq_provider):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit reached"
    mock_resp.headers = httpx.Headers({
        "retry-after": "2.5",
        "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-requests": "2.5s",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="hi")])
        with pytest.raises(RetriableError) as exc_info:
            await groq_provider.generate(req)

        assert exc_info.value.status_code == 429
        assert "retry_after=2.5s" in str(exc_info.value)
        assert exc_info.value.retriable is True


@pytest.mark.asyncio
async def test_groq_429_retry_with_cooldown_recovery(groq_provider):
    """Verify that GroqProvider waits out the cooldown and recovers on retry."""
    # Reset cooldown before test
    GroqProvider._cooldown_until = 0.0

    mock_resp_429 = MagicMock(spec=httpx.Response)
    mock_resp_429.status_code = 429
    mock_resp_429.text = "Rate limit reached"
    mock_resp_429.headers = httpx.Headers({
        "retry-after": "0.01",
        "x-ratelimit-remaining-requests": "0",
    })

    mock_resp_200 = MagicMock(spec=httpx.Response)
    mock_resp_200.status_code = 200
    mock_resp_200.headers = httpx.Headers({})
    mock_resp_200.json.return_value = {
        "id": "chatcmpl-retry-success",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Recovered after cooldown!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [mock_resp_429, mock_resp_200]

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="hi")])
        res = await groq_provider.generate(req)

        assert res.content == "Recovered after cooldown!"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_groq_auth_error_401(groq_provider):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Invalid API Key"
    mock_resp.headers = httpx.Headers({})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="hi")])
        with pytest.raises(NonRetriableError) as exc_info:
            await groq_provider.generate(req)

        assert exc_info.value.status_code == 401
        assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_groq_server_error_500(groq_provider):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.headers = httpx.Headers({})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="hi")])
        with pytest.raises(RetriableError) as exc_info:
            await groq_provider.generate(req)

        assert exc_info.value.status_code == 500
        assert exc_info.value.retriable is True


def test_router_models_in_prod_mode(monkeypatch):
    """Verify get_valid_models and get_models return Groq in PROD mode."""
    from backend.config import settings
    from backend.routers.llm import get_valid_models, get_models

    monkeypatch.setattr(settings, "deployment_type", "PROD")
    models = get_valid_models()
    assert settings.groq_model in models
    assert models[settings.groq_model] == f"Groq ({settings.groq_model})"
    assert settings.groq_model == "openai/gpt-oss-120b"

    res = get_models()
    assert res.deployment_type == "PROD"
    assert settings.groq_model in res.models


def test_groq_build_body_clamps_max_tokens(groq_provider):
    """Verify that GroqProvider clamps max_tokens to <= 65536 for openai/gpt-oss-120b."""
    req = LLMRequest(
        messages=[Message(role=MessageRole.USER, content="test")],
        max_tokens=100000,
    )
    body = groq_provider._build_body(req)
    assert body["max_tokens"] == 65536

    req2 = LLMRequest(
        messages=[Message(role=MessageRole.USER, content="test")],
        max_tokens=4096,
    )
    body2 = groq_provider._build_body(req2)
    assert body2["max_tokens"] == 4096


@pytest.mark.asyncio
async def test_groq_400_tool_use_failed_recovery(groq_provider):
    """Verify that GroqProvider recovers from HTTP 400 with tool_use_failed without raising NonRetriableError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 400
    mock_resp.headers = httpx.Headers({})
    mock_resp.json.return_value = {
        "error": {
            "message": "Tool choice is none, but model called a tool",
            "type": "invalid_request_error",
            "code": "tool_use_failed",
            "failed_generation": '{"name": "search_repository", "arguments": {"query": "docker-compose.yml", "limit": 20}}',
        }
    }
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="search for docker")])
        resp = await groq_provider.generate(req)

        assert resp.provider == "groq"
        assert resp.tool_calls is not None
        assert resp.tool_calls[0].tool_name == "search_repository"
        assert resp.tool_calls[0].parameters == {"query": "docker-compose.yml", "limit": 20}


@pytest.mark.asyncio
async def test_groq_413_raises_non_retriable(groq_provider):
    """Verify that HTTP 413 is treated as non-retriable context error rather than 429 rate limit."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 413
    mock_resp.text = '{"error":{"message":"Request too large","type":"tokens"}}'
    mock_resp.headers = httpx.Headers({})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="huge prompt")])
        with pytest.raises(NonRetriableError) as exc_info:
            await groq_provider.generate(req)

        assert exc_info.value.status_code == 413
        assert "413" in str(exc_info.value)
        # Should NOT trigger retry
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_groq_tpm_rate_limiting_wait(groq_provider):
    """Verify that exceeding 8,000 TPM triggers wait until capacity clears."""
    import time

    # Pre-populate token usage near limit (7,500 tokens used 30 seconds ago)
    now = time.time()
    GroqProvider._token_usages = [(now - 30.0, 7500)]
    GroqProvider._request_times = [now - 30.0]

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = httpx.Headers({})
    mock_resp.json.return_value = {
        "id": "chatcmpl-tpm",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 800, "completion_tokens": 100, "total_tokens": 900},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_post.return_value = mock_resp

        # Request estimated at 1,000 tokens (7500 + 1000 = 8500 > 8000 limit)
        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="x" * 3500)])
        res = await groq_provider.generate(req)

        assert res.content == "ok"
        # Must have slept to wait for the 60s window to clear
        assert mock_sleep.called
        # Recorded actual tokens (900)
        assert any(count == 900 for _, count in GroqProvider._token_usages)


@pytest.mark.asyncio
async def test_groq_header_token_sync(groq_provider):
    """Verify that x-ratelimit-remaining-tokens updates local rate limiter."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    # Groq says only 2000 tokens remain (so 6000 tokens were consumed)
    mock_resp.headers = httpx.Headers({
        "x-ratelimit-remaining-tokens": "2000",
    })
    mock_resp.json.return_value = {
        "id": "chatcmpl-hdr",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="hi")])
        await groq_provider.generate(req)

        # Total tokens in limiter should be at least 6000
        total_in_limiter = sum(count for _, count in GroqProvider._token_usages)
        assert total_in_limiter >= 6000



