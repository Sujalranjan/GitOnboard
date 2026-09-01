"""
Model-aware token counting for RIM comparison research.

Supports exact tokenization for Qwen (vendored tokenizer), Gemini (REST API),
OpenRouter (best-effort), and fallback heuristic (len/4).

Usage:
    from backend.ai.tokencount import count_tokens
    result = await count_tokens(text, provider="ollama", model="qwen2.5-coder:7b")
    print(f"{result.count} tokens ({result.method}, estimated={result.estimated})")
"""

from .base import TokenCountResult, TokenCounter
from .heuristic import HeuristicTokenCounter
from .registry import count_tokens

__all__ = [
    "TokenCountResult",
    "TokenCounter",
    "HeuristicTokenCounter",
    "count_tokens",
]
