"""
Base classes for token counting.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TokenCountResult:
    """Result of a token count operation."""
    count: int
    method: str  # "qwen_tokenizer" | "gemini_api" | "heuristic" | "error"
    estimated: bool  # True if not exact (heuristic or fallback)
    provider: str  # "ollama" | "gemini" | "openrouter" | "error"
    model: str  # actual model name
    latency_ms: float = 0.0  # time taken by counter (e.g., API call)
    error: str = ""  # if method=="error", reason why


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
