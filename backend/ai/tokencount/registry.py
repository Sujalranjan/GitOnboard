"""
Token counter registry: dispatch by provider, always returns a result (never raises).
"""

import logging

from .base import TokenCountResult
from .heuristic import HeuristicTokenCounter
from .qwen import QwenTokenCounter
from .gemini import GeminiTokenCounter
from .openrouter import OpenRouterTokenCounter

logger = logging.getLogger(__name__)

# Global counter instances (reused across calls for caching benefits)
_qwen_counter = QwenTokenCounter()
_gemini_counter = GeminiTokenCounter()
_openrouter_counter = OpenRouterTokenCounter()
_heuristic_counter = HeuristicTokenCounter()


async def count_tokens(text: str, provider: str, model: str) -> TokenCountResult:
    """
    Count tokens in text using the appropriate counter for the provider.

    Dispatch logic:
    - ollama + qwen model -> QwenTokenCounter (exact)
    - ollama + non-qwen -> HeuristicTokenCounter
    - gemini -> GeminiTokenCounter (exact via API)
    - openrouter -> OpenRouterTokenCounter (estimated=True always)
    - unknown -> HeuristicTokenCounter

    Never raises. Always returns a TokenCountResult, even on errors.

    Args:
        text: Text to count
        provider: LLM provider ("ollama", "gemini", "openrouter")
        model: Model name/version

    Returns:
        TokenCountResult with count, method, estimated flag, latency
    """
    try:
        if provider == "ollama":
            if "qwen" in model.lower():
                return await _qwen_counter.count(text, provider, model)
            else:
                return await _heuristic_counter.count(text, provider, model)

        elif provider == "gemini":
            return await _gemini_counter.count(text, provider, model)

        elif provider == "openrouter":
            return await _openrouter_counter.count(text, provider, model)

        else:
            logger.warning(f"[TokenCountRegistry] Unknown provider: {provider}, using heuristic")
            return await _heuristic_counter.count(text, provider, model)

    except Exception as e:
        logger.error(f"[TokenCountRegistry] Unexpected error in count_tokens: {e}, falling back to heuristic", exc_info=True)
        return await _heuristic_counter.count(text, provider, model)
