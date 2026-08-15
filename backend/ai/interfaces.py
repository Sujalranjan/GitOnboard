"""LLMProvider Protocol — the contract every provider implementation must satisfy."""
from __future__ import annotations
from typing import Protocol, runtime_checkable, Type, TypeVar
from .schemas import LLMRequest, LLMResponse

T = TypeVar("T")


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal protocol all LLM provider adapters must implement."""

    provider_name: str

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a plain-text completion."""
        ...

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        """Generate a structured Pydantic model response."""
        ...
