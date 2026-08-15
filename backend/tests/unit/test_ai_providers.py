"""
Unit tests for LLMService selective fallback logic.

All tests use mock providers — zero real API calls.
"""
import pytest
from typing import Type, TypeVar
from pydantic import BaseModel

from backend.ai.service import LLMService
from backend.ai.schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError, RetriableError, Message, MessageRole

T = TypeVar("T")


# ──────────────────────────────────────────────────────────────────────────────
# Mock providers
# ──────────────────────────────────────────────────────────────────────────────

class SuccessProvider:
    provider_name = "mock_success"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="ok", model="mock", provider="mock_success")

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        import json
        return schema.model_validate({"content": "ok"})


class RetriableFailProvider:
    """Simulates a rate limit or transient network failure."""
    provider_name = "mock_retriable_fail"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise RetriableError("Rate limited", status_code=429)

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        raise RetriableError("Rate limited", status_code=429)


class NonRetriableFailProvider:
    """Simulates an auth error — must NOT trigger fallback."""
    provider_name = "mock_non_retriable_fail"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NonRetriableError("Unauthorized", status_code=401)

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        raise NonRetriableError("Unauthorized", status_code=401)


def _make_request() -> LLMRequest:
    return LLMRequest(messages=[Message(role=MessageRole.USER, content="hello")])


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_provider_success():
    """Single provider returns successful response."""
    service = LLMService(providers=[SuccessProvider()])
    response = await service.generate(_make_request())
    assert response.content == "ok"
    assert response.provider == "mock_success"


@pytest.mark.asyncio
async def test_fallback_on_retriable_error():
    """Retriable error (429) triggers fallback to next provider."""
    service = LLMService(providers=[RetriableFailProvider(), SuccessProvider()])
    response = await service.generate(_make_request())
    assert response.provider == "mock_success"


@pytest.mark.asyncio
async def test_no_fallback_on_non_retriable_error():
    """Non-retriable error (401) must abort immediately — no fallback."""
    service = LLMService(providers=[NonRetriableFailProvider(), SuccessProvider()])
    with pytest.raises(NonRetriableError) as exc_info:
        await service.generate(_make_request())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_all_providers_fail_raises():
    """When all providers raise RetriableError, LLMService raises the last error."""
    service = LLMService(providers=[RetriableFailProvider(), RetriableFailProvider()])
    with pytest.raises(RetriableError):
        await service.generate(_make_request())


@pytest.mark.asyncio
async def test_provider_order_matters():
    """First non-failing provider wins; later providers are skipped."""
    call_log = []

    class LoggingSuccess:
        provider_name = "logging"
        async def generate(self, request):
            call_log.append("logging")
            return LLMResponse(content="done", model="m", provider="logging")
        async def generate_structured(self, request, schema):
            call_log.append("logging_structured")

    service = LLMService(providers=[LoggingSuccess(), SuccessProvider()])
    await service.generate(_make_request())
    assert call_log == ["logging"]


def test_service_requires_at_least_one_provider():
    with pytest.raises(ValueError):
        LLMService(providers=[])
