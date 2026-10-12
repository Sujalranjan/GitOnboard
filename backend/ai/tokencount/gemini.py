"""
Gemini token counter: use the Gemini REST API's :countTokens endpoint.
"""

import hashlib
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

from .base import TokenCounter, TokenCountResult, RequestTokenCount
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

        if not model or not model.strip():
            raise ValueError("[GeminiTokenCounter] Explicit model name is required; cannot count tokens with empty model.")

        model_clean = model.strip()

        # Check cache
        cache_key = self._cache_key(model_clean, text)
        if cache_key in self.token_cache:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TokenCountResult(
                count=self.token_cache[cache_key],
                method="gemini_api",
                estimated=False,
                provider="gemini",
                model=model_clean,
                latency_ms=elapsed_ms,
            )

        # Call Gemini :countTokens endpoint
        try:
            import httpx
            url = f"{self.base_url}/{model_clean}:countTokens?key={self.api_key}"
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

            logger.debug(f"[GeminiTokenCounter] Counted {count} tokens for {model_clean} in {elapsed_ms:.1f}ms")

            return TokenCountResult(
                count=count,
                method="gemini_api",
                estimated=False,
                provider="gemini",
                model=model_clean,
                latency_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"[GeminiTokenCounter] API call failed: {e}, falling back to heuristic")
            return await self.heuristic.count(text, provider, model_clean)

    async def count_request(self, request: Any, provider: str, model: str) -> RequestTokenCount:
        """
        Count total tokens in full LLMRequest via Gemini :countTokens API.
        Includes systemInstruction, contents (all message turns), and tools functionDeclarations.
        """
        start = time.perf_counter()

        if not model or not model.strip():
            raise ValueError("[GeminiTokenCounter] Explicit model name is required; cannot count tokens with empty model.")

        if not self.api_key:
            logger.warning("[GeminiTokenCounter] No GEMINI_API_KEY set, falling back to base request count")
            return await super().count_request(request, provider, model)

        try:
            import httpx
            url = f"{self.base_url}/{model.strip()}:countTokens?key={self.api_key}"

            contents = []
            system_instruction = None

            for m in getattr(request, "messages", []):
                role_val = m.role.value if hasattr(m.role, "value") else str(m.role)
                if role_val == "system":
                    system_instruction = {"parts": [{"text": m.content or ""}]}
                else:
                    role = "user" if role_val == "user" else "model"
                    contents.append({
                        "role": role,
                        "parts": [{"text": m.content or ""}]
                    })

            if not contents:
                contents = [{"role": "user", "parts": [{"text": "Hello"}]}]

            payload: Dict[str, Any] = {"contents": contents}
            if system_instruction:
                payload["systemInstruction"] = system_instruction

            tools = getattr(request, "tools", None)
            if tools:
                payload["tools"] = [{
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": t.parameters}
                        for t in tools
                    ]
                }]

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

            result = response.json()
            total_tokens = result.get("totalTokens", 0)
            elapsed_ms = (time.perf_counter() - start) * 1000

            return RequestTokenCount(
                total_tokens=total_tokens,
                is_exact=True,
                method="gemini_api_full",
                provider=provider or "gemini",
                model=model,
                latency_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"[GeminiTokenCounter] Full request count failed: {e}, falling back to base count")
            return await super().count_request(request, provider, model)
