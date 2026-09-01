"""
Heuristic token counter: len(text) / 4, always available fallback.
"""

import logging
import math
import time

from .base import TokenCounter, TokenCountResult

logger = logging.getLogger(__name__)


class HeuristicTokenCounter(TokenCounter):
    """Fallback heuristic: ceil(len(text) / 4). Always available, never fails."""

    async def count(self, text: str, provider: str, model: str) -> TokenCountResult:
        """
        Estimate tokens via heuristic.

        Args:
            text: Text to estimate
            provider: LLM provider (for logging)
            model: Model name (for logging)

        Returns:
            TokenCountResult with count = ceil(len(text)/4), estimated=True
        """
        start = time.perf_counter()

        count = max(1, math.ceil(len(text) / 4))
        elapsed_ms = (time.perf_counter() - start) * 1000

        return TokenCountResult(
            count=count,
            method="heuristic",
            estimated=True,
            provider=provider,
            model=model,
            latency_ms=elapsed_ms,
        )
