"""
OpenRouter token counter: best-effort, always marked estimated since underlying model may vary.
"""

import logging
import time

from .base import TokenCounter, TokenCountResult
from .heuristic import HeuristicTokenCounter
from .qwen import QwenTokenCounter

logger = logging.getLogger(__name__)


class OpenRouterTokenCounter(TokenCounter):
    """
    Token counting for OpenRouter-routed models.

    OpenRouter can route to different underlying models, so we can't guarantee exact counts.
    Best-effort strategy:
    - If model name contains "qwen", delegate to QwenTokenCounter but mark estimated=True
    - Otherwise, use heuristic

    All results marked estimated=True per user spec.
    """

    def __init__(self):
        self.heuristic = HeuristicTokenCounter()
        self.qwen_counter = QwenTokenCounter()

    async def count(self, text: str, provider: str, model: str) -> TokenCountResult:
        """
        Count tokens for an OpenRouter-routed model.

        Args:
            text: Text to count
            provider: "openrouter"
            model: OpenRouter model name (e.g., "qwen/qwen-2.5-72b-instruct")

        Returns:
            TokenCountResult with estimated=True always (since underlying model may differ)
        """
        start = time.perf_counter()

        # Try to detect if this is routed to a Qwen model
        if "qwen" in model.lower():
            logger.debug(f"[OpenRouterTokenCounter] Attempting Qwen tokenizer for {model}")
            result = await self.qwen_counter.count(text, "ollama", model)

            # Override estimated=True since we can't be sure OpenRouter uses the exact same tokenizer
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TokenCountResult(
                count=result.count,
                method=result.method,
                estimated=True,  # ALWAYS estimated for OpenRouter
                provider="openrouter",
                model=model,
                latency_ms=elapsed_ms,
            )

        # Fallback to heuristic for non-Qwen models
        logger.debug(f"[OpenRouterTokenCounter] Using heuristic for {model}")
        result = await self.heuristic.count(text, provider, model)

        # Update provider/model fields
        elapsed_ms = (time.perf_counter() - start) * 1000
        return TokenCountResult(
            count=result.count,
            method=result.method,
            estimated=True,  # ALWAYS estimated for OpenRouter
            provider="openrouter",
            model=model,
            latency_ms=elapsed_ms,
        )
