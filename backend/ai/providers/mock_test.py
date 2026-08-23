"""Deterministic Test Provider for offline and automated test execution."""
from __future__ import annotations
import logging
from typing import Type, TypeVar

from backend.ai.interfaces import LLMProvider
from backend.ai.schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")


class DeterministicTestProvider(LLMProvider):
    """
    Fast, deterministic LLM provider used in automated test environments
    to eliminate external Ollama/network dependencies and timeout delays.
    """
    provider_name = "test_mock"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=f"Deterministic test response for: {request.messages[-1].content[:60] if request.messages else ''}",
            provider=self.provider_name,
            model="mock-test-model",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        # Fallback to trigger deterministic pipeline synthesis in tests
        raise NonRetriableError(f"DeterministicTestProvider: schema '{getattr(schema, '__name__', str(schema))}' triggering deterministic fallback.")
