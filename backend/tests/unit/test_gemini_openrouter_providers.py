"""Unit tests for GeminiProvider and OpenRouterProvider adapters."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from backend.ai.providers.gemini import GeminiProvider, MAX_REQUESTS_PER_MINUTE as GEMINI_RPM, MAX_TOKENS_PER_MINUTE as GEMINI_TPM
from backend.ai.providers.openrouter import OpenRouterProvider, MAX_REQUESTS_PER_MINUTE as OPENROUTER_RPM
from backend.ai.schemas import LLMRequest, Message, MessageRole, NonRetriableError, RetriableError, Tool


@pytest.fixture
def gemini_provider():
    provider = GeminiProvider(api_key="test-gemini-key")
    GeminiProvider._request_times = []
    GeminiProvider._token_usages = []
    GeminiProvider._cooldown_until = 0.0
    return provider


@pytest.fixture
def openrouter_provider():
    provider = OpenRouterProvider(api_key="test-openrouter-key")
    OpenRouterProvider._request_times = []
    OpenRouterProvider._cooldown_until = 0.0
    return provider


# ==============================================================================
# GeminiProvider Tests
# ==============================================================================

def test_gemini_provider_initialization():
    provider = GeminiProvider(api_key="my-key")
    assert provider.provider_name == "gemini"
    assert provider.default_model == "gemini-3.8-flash"
    assert GEMINI_RPM == 5
    assert GEMINI_TPM == 250000


@pytest.mark.asyncio
async def test_gemini_generate_success(gemini_provider):
    mock_response_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Hello from Gemini!"}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 20,
            "candidatesTokenCount": 10,
            "totalTokenCount": 30,
        },
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = httpx.Headers({})
    mock_resp.json.return_value = mock_response_data

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Hello")],
            temperature=0.2,
        )
        res = await gemini_provider.generate(req)

        assert res.content == "Hello from Gemini!"
        assert res.model == "gemini-3.8-flash"
        assert res.provider == "gemini"
        assert res.usage.total_tokens == 30
        assert res.usage.prompt_tokens == 20
        assert res.usage.completion_tokens == 10


@pytest.mark.asyncio
async def test_gemini_429_retry_with_cooldown_recovery(gemini_provider):
    """Verify GeminiProvider parses 429 retryDelay and recovers on retry."""
    rate_limit_resp = MagicMock(spec=httpx.Response)
    rate_limit_resp.status_code = 429
    rate_limit_resp.text = json.dumps({
        "error": {
            "code": 429,
            "message": "Resource has been exhausted",
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.RetryInfo",
                    "retryDelay": {"seconds": 0, "nanos": 50000000},
                }
            ],
        }
    })
    rate_limit_resp.headers = httpx.Headers({})

    success_resp = MagicMock(spec=httpx.Response)
    success_resp.status_code = 200
    success_resp.headers = httpx.Headers({})
    success_resp.json.return_value = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Recovered Gemini!"}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"totalTokenCount": 15},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [rate_limit_resp, success_resp]

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="Hi")])
        res = await gemini_provider.generate(req, max_retries=2)

        assert res.content == "Recovered Gemini!"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_gemini_413_raises_non_retriable(gemini_provider):
    """Verify HTTP 413 raises NonRetriableError so caller can prune context."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 413
    mock_resp.text = "Payload Too Large"
    mock_resp.headers = httpx.Headers({})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="huge prompt")])
        with pytest.raises(NonRetriableError) as exc_info:
            await gemini_provider.generate(req)

        assert exc_info.value.status_code == 413
        assert exc_info.value.retriable is False


# ==============================================================================
# OpenRouterProvider Tests
# ==============================================================================

def test_openrouter_provider_initialization():
    provider = OpenRouterProvider(api_key="my-key")
    assert provider.provider_name == "openrouter"
    assert provider.default_model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert OPENROUTER_RPM == 20


@pytest.mark.asyncio
async def test_openrouter_generate_success(openrouter_provider):
    mock_response_data = {
        "id": "gen-123",
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello from OpenRouter!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 6,
            "total_tokens": 18,
        },
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = httpx.Headers({})
    mock_resp.json.return_value = mock_response_data

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Hello")],
            temperature=0.2,
        )
        res = await openrouter_provider.generate(req)

        assert res.content == "Hello from OpenRouter!"
        assert res.model == "nvidia/nemotron-3-ultra-550b-a55b:free"
        assert res.provider == "openrouter"
        assert res.usage.total_tokens == 18


@pytest.mark.asyncio
async def test_openrouter_429_retry_with_cooldown_recovery(openrouter_provider):
    """Verify OpenRouterProvider parses 429 retry-after header and recovers."""
    rate_limit_resp = MagicMock(spec=httpx.Response)
    rate_limit_resp.status_code = 429
    rate_limit_resp.headers = httpx.Headers({"retry-after": "0.05"})
    rate_limit_resp.text = "Rate limit reached"

    success_resp = MagicMock(spec=httpx.Response)
    success_resp.status_code = 200
    success_resp.headers = httpx.Headers({})
    success_resp.json.return_value = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "Recovered OpenRouter!"},
            }
        ],
        "usage": {"total_tokens": 20},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [rate_limit_resp, success_resp]

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="Hi")])
        res = await openrouter_provider.generate(req, max_retries=2)

        assert res.content == "Recovered OpenRouter!"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_openrouter_413_raises_non_retriable(openrouter_provider):
    """Verify HTTP 413 raises NonRetriableError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 413
    mock_resp.text = "Context size exceeded"
    mock_resp.headers = httpx.Headers({})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = LLMRequest(messages=[Message(role=MessageRole.USER, content="too long")])
        with pytest.raises(NonRetriableError) as exc_info:
            await openrouter_provider.generate(req)

        assert exc_info.value.status_code == 413
        assert exc_info.value.retriable is False
