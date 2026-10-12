"""
Base classes for token counting.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TokenCountResult:
    """Result of a token count operation on raw text."""
    count: int
    method: str  # "qwen_tokenizer" | "gemini_api" | "heuristic" | "error"
    estimated: bool  # True if not exact (heuristic or fallback)
    provider: str  # "ollama" | "gemini" | "openrouter" | "groq" | "error"
    model: str  # actual model name
    latency_ms: float = 0.0  # time taken by counter (e.g., API call)
    error: str = ""  # if method=="error", reason why


@dataclass
class RequestTokenCount:
    """Structured breakdown of tokens in a full LLMRequest."""
    total_tokens: int
    system_tokens: int = 0
    message_tokens: int = 0
    tool_schema_tokens: int = 0
    framing_overhead_tokens: int = 0
    is_exact: bool = False
    method: str = "heuristic"
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0


class TokenCounter(ABC):
    """Abstract base for token counting implementations."""

    @abstractmethod
    async def count(self, text: str, provider: str, model: str) -> TokenCountResult:
        """
        Count tokens in text.

        Args:
            text: Text to count
            provider: LLM provider name
            model: Model name/version

        Returns:
            TokenCountResult with count, method, estimated flag, latency
        """
        pass

    async def count_request(self, request: Any, provider: str, model: str) -> RequestTokenCount:
        """
        Count all tokens in an LLMRequest (system, messages, tools, framing).

        Default implementation counts message contents and tool descriptions with count().
        Subclasses should override for provider-specific structural tokenization.
        """
        text_parts = []
        for m in getattr(request, "messages", []):
            if hasattr(m, "content") and m.content:
                text_parts.append(m.content)
            if hasattr(m, "tool_calls") and m.tool_calls:
                import json
                text_parts.append(json.dumps(m.tool_calls))
        for t in getattr(request, "tools", []) or []:
            import json
            text_parts.append(t.name)
            text_parts.append(t.description)
            text_parts.append(json.dumps(t.parameters))

        res = await self.count("\n".join(text_parts), provider, model)
        return RequestTokenCount(
            total_tokens=res.count,
            message_tokens=res.count,
            is_exact=not res.estimated,
            method=res.method,
            provider=provider,
            model=model,
            latency_ms=res.latency_ms,
        )
