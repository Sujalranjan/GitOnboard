"""
LLMService — provider dispatcher with selective fallback.

Fallback rules:
  - Triggers on: RetriableError (timeouts, 502/503/504, 429 rate limit)
  - Does NOT trigger on: NonRetriableError (400 bad request, 401/403 auth, model refusals)
  - Maximum fallback chain: all configured providers, then raises the last error.
"""
from __future__ import annotations
import logging
import os
from typing import List, Optional, Type, TypeVar

from .interfaces import LLMProvider
from .schemas import LLMRequest, LLMResponse, NonRetriableError, RetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")

MAX_PROVIDER_RETRIES = 1  # Each provider is tried at most once per request


def build_default_service() -> "LLMService":
    """
    Construct LLMService from environment variables.
    Priority: OpenRouter -> NVIDIA -> Ollama
    Only providers with valid API keys are added (Ollama is always added as fallback).
    """
    from .providers.openrouter import OpenRouterProvider
    from .providers.nvidia import NvidiaProvider
    from .providers.ollama import OllamaProvider

    providers: List[LLMProvider] = []

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key:
        providers.append(OpenRouterProvider(api_key=openrouter_key))
        logger.info("LLMService: OpenRouter provider registered.")

    nvidia_key = os.environ.get("NVIDIA_API_KEY", "")
    if nvidia_key:
        providers.append(NvidiaProvider(api_key=nvidia_key))
        logger.info("LLMService: NVIDIA provider registered.")

    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
    ollama_timeout = float(os.environ.get("OLLAMA_TIMEOUT", "300.0"))
    providers.append(OllamaProvider(base_url=ollama_url, model=ollama_model, timeout=ollama_timeout))
    logger.info(f"LLMService: Ollama provider registered ({ollama_url}).")

    return LLMService(providers=providers)


class LLMService:
    """
    Orchestrates LLM calls across multiple providers with selective error-based fallback.

    Design:
        - Providers are tried in order.
        - RetriableError (rate limit, network timeout, 5xx) -> try next provider.
        - NonRetriableError (bad request, auth, schema) -> raise immediately, no fallback.
        - If all providers are exhausted, raise the last RetriableError.
    """

    def __init__(self, providers: List[LLMProvider]):
        if not providers:
            raise ValueError("LLMService requires at least one provider.")
        self.providers = providers

    async def generate(self, request: LLMRequest) -> LLMResponse:
        last_error: Optional[Exception] = None
        for provider in self.providers:
            try:
                logger.debug(f"LLMService: Attempting generate via {provider.provider_name}")
                response = await provider.generate(request)
                logger.info(f"LLMService: Success via {provider.provider_name} ({response.usage.total_tokens} tokens)")
                return response
            except NonRetriableError as e:
                logger.error(f"LLMService: Non-retriable error from {provider.provider_name}: {e}. Aborting.")
                raise
            except RetriableError as e:
                logger.warning(f"LLMService: Retriable error from {provider.provider_name}: {e}. Trying next provider.")
                last_error = e
                continue
        raise last_error or RuntimeError("LLMService: All providers failed.")

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        last_error: Optional[Exception] = None
        for provider in self.providers:
            try:
                logger.debug(f"LLMService: Attempting generate_structured via {provider.provider_name}")
                result = await provider.generate_structured(request, schema)
                logger.info(f"LLMService: Structured success via {provider.provider_name}")
                return result
            except NonRetriableError as e:
                logger.error(f"LLMService: Non-retriable error from {provider.provider_name}: {e}. Aborting.")
                raise
            except RetriableError as e:
                logger.warning(f"LLMService: Retriable error from {provider.provider_name}: {e}. Trying next provider.")
                last_error = e
                continue
        raise last_error or RuntimeError("LLMService: All providers failed (structured).")


# Module-level singleton — initialized lazily
_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """FastAPI dependency to get the shared LLMService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = build_default_service()
    return _service_instance
