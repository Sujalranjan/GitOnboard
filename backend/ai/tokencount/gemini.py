"""
Gemini token counter: use the Gemini REST API's :countTokens endpoint.
"""

import hashlib
import logging
import os
import time
from typing import Dict, Optional, Tuple

from .base import TokenCounter, TokenCountResult
from .heuristic import HeuristicTokenCounter

logger = logging.getLogger(__name__)


class GeminiTokenCounter(TokenCounter):
    """
    Token counting for Gemini via REST API :countTokens endpoint.

    Supports caching within a comparison run to avoid double-counting identical text.
    Falls back to heuristic on API errors.
    """

    def __init__(self):
        self.heuristic = HeuristicTokenCounter()
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.token_cache: Dict[Tuple[str, str], int] = {}  # (model, text_hash) -> count

    def _cache_key(self, model: str, text: str) -> Tuple[str, str]:
        """Generate cache key for text (model, sha256(text))."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        return (model, text_hash)

    async def count(self, text: str, provider: str, model: str) -> TokenCountResult:
        """
        Count tokens via Gemini :countTokens endpoint.

        Args:
            text: Text to count
            provider: LLM provider (unused, always "gemini")
            model: Gemini model name

        Returns:
            TokenCountResult with exact count from API, or fallback to heuristic on error
        """
        start = time.perf_counter()

        if not self.api_key:
            logger.warning("[GeminiTokenCounter] No GEMINI_API_KEY set, falling back to heuristic")
            return await self.heuristic.count(text, provider, model)

        # Check cache
        cache_key = self._cache_key(model, text)
        if cache_key in self.token_cache:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TokenCountResult(
                count=self.token_cache[cache_key],
                method="gemini_api",
                estimated=False,
                provider="gemini",
                model=model,
                latency_ms=elapsed_ms,
            )

        # Call Gemini :countTokens endpoint
        try:
            import httpx
            url = f"{self.base_url}/{model}:countTokens?key={self.api_key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": text}]}
                ]
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

            result = response.json()
            count = result.get("totalTokens", 0)

            # Cache the result
            self.token_cache[cache_key] = count
            elapsed_ms = (time.perf_counter() - start) * 1000

            logger.debug(f"[GeminiTokenCounter] Counted {count} tokens for {model} in {elapsed_ms:.1f}ms")

            return TokenCountResult(
                count=count,
                method="gemini_api",
                estimated=False,
                provider="gemini",
                model=model,
                latency_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning(f"[GeminiTokenCounter] API call failed: {e}, falling back to heuristic")
            return await self.heuristic.count(text, provider, model)
