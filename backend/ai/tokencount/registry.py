"""
Token counter registry: dispatch by provider, always returns a result (never raises).
"""

import logging
from typing import Any

from .base import TokenCountResult, RequestTokenCount
from .heuristic import HeuristicTokenCounter
from .qwen import QwenTokenCounter
from .gemini import GeminiTokenCounter
from .openrouter import OpenRouterTokenCounter
from .groq import GroqTokenCounter

logger = logging.getLogger(__name__)

# Global counter instances (reused across calls for caching benefits)
_qwen_counter = QwenTokenCounter()
_gemini_counter = GeminiTokenCounter()
_openrouter_counter = OpenRouterTokenCounter()
_groq_counter = GroqTokenCounter()
_heuristic_counter = HeuristicTokenCounter()


async def count_tokens(text: str, provider: str, model: str) -> TokenCountResult:
    """
    Count tokens in text using the appropriate counter for the provider.

    Dispatch logic:
    - groq -> GroqTokenCounter (tiktoken o200k_harmony)
    - ollama + qwen model -> QwenTokenCounter (exact)
    - ollama + non-qwen -> HeuristicTokenCounter
    - gemini -> GeminiTokenCounter (exact via API)
    - openrouter -> OpenRouterTokenCounter (estimated=True always)
    - unknown -> HeuristicTokenCounter

    Never raises. Always returns a TokenCountResult, even on errors.
    """
    try:
        p_lower = (provider or "").lower()
        if p_lower == "groq":
            return await _groq_counter.count(text, provider, model)

        elif p_lower == "ollama":
            if "qwen" in model.lower():
                return await _qwen_counter.count(text, provider, model)
            else:
                return await _heuristic_counter.count(text, provider, model)

        elif p_lower == "gemini":
            return await _gemini_counter.count(text, provider, model)

        elif p_lower == "openrouter":
            return await _openrouter_counter.count(text, provider, model)

        else:
            logger.warning(f"[TokenCountRegistry] Unknown provider: {provider}, using heuristic")
            return await _heuristic_counter.count(text, provider, model)

    except Exception as e:
        logger.error(f"[TokenCountRegistry] Unexpected error in count_tokens: {e}, falling back to heuristic", exc_info=True)
        return await _heuristic_counter.count(text, provider, model)


async def count_full_request(request: Any, provider: str, model: str) -> RequestTokenCount:
    """
    Count all tokens in an LLMRequest using the model/provider-appropriate counter.

    Never raises. Returns RequestTokenCount with full breakdown and exactness flag.
    """
    try:
        p_lower = (provider or "").lower()
        if p_lower == "groq":
            return await _groq_counter.count_request(request, provider, model)
        elif p_lower == "gemini":
            return await _gemini_counter.count_request(request, provider, model)
        elif p_lower == "openrouter":
            return await _openrouter_counter.count_request(request, provider, model)
        elif p_lower == "ollama" and "qwen" in (model or "").lower():
            return await _qwen_counter.count_request(request, provider, model)
        else:
            return await _heuristic_counter.count_request(request, provider, model)
    except Exception as e:
        logger.error(f"[TokenCountRegistry] count_full_request error: {e}, falling back to heuristic", exc_info=True)
        return await _heuristic_counter.count_request(request, provider, model)
