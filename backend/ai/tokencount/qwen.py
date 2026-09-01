"""
Qwen tokenizer: exact token counting for Qwen models via vendored tokenizer.json files.
"""

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .base import TokenCounter, TokenCountResult
from .heuristic import HeuristicTokenCounter

logger = logging.getLogger(__name__)


class QwenTokenCounter(TokenCounter):
    """
    Exact tokenization for Qwen models using vendored tokenizer.json files.

    Falls back to heuristic if tokenizer unavailable.
    """

    def __init__(self):
        self.heuristic = HeuristicTokenCounter()
        self._tokenizer_cache = {}

    @lru_cache(maxsize=4)
    def _load_tokenizer(self, tokenizer_path: str):
        """
        Load a tokenizer from vendored file (cached).

        Args:
            tokenizer_path: Path to tokenizer.json file

        Returns:
            Tokenizer object or None if load fails
        """
        try:
            from tokenizers import Tokenizer
            tokenizer = Tokenizer.from_file(tokenizer_path)
            logger.debug(f"[QwenTokenCounter] Loaded tokenizer from {tokenizer_path}")
            return tokenizer
        except Exception as e:
            logger.warning(f"[QwenTokenCounter] Failed to load tokenizer {tokenizer_path}: {e}")
            return None

    def _resolve_tokenizer_path(self, model: str) -> Optional[str]:
        """
        Resolve Qwen model name to vendored tokenizer.json path.

        Args:
            model: Model name (e.g., "qwen2.5-coder:7b", "qwen3:4b-instruct")

        Returns:
            Path to tokenizer.json or None if not found
        """
        # Try to match model name to a vendored family
        vendor_dir = Path(__file__).parent / "vendor"

        if "qwen3" in model.lower():
            path = vendor_dir / "qwen3" / "tokenizer.json"
            if path.exists():
                return str(path)
        elif "qwen2" in model.lower() or "qwen" in model.lower():
            path = vendor_dir / "qwen2.5" / "tokenizer.json"
            if path.exists():
                return str(path)

        # Generic qwen directory
        path = vendor_dir / "qwen" / "tokenizer.json"
        if path.exists():
            return str(path)

        logger.debug(f"[QwenTokenCounter] No vendored tokenizer found for model: {model}")
        return None

    async def count(self, text: str, provider: str, model: str) -> TokenCountResult:
        """
        Count tokens using exact Qwen tokenizer.

        Args:
            text: Text to tokenize
            provider: LLM provider (unused, always "ollama" for Qwen)
            model: Qwen model name

        Returns:
            TokenCountResult with exact count, or fallback to heuristic if tokenizer unavailable
        """
        start = time.perf_counter()

        # Try to resolve and load tokenizer
        tokenizer_path = self._resolve_tokenizer_path(model)
        if not tokenizer_path:
            logger.debug(f"[QwenTokenCounter] No tokenizer path for {model}, falling back to heuristic")
            return await self.heuristic.count(text, provider, model)

        tokenizer = self._load_tokenizer(tokenizer_path)
        if not tokenizer:
            logger.debug(f"[QwenTokenCounter] Failed to load tokenizer, falling back to heuristic")
            return await self.heuristic.count(text, provider, model)

        try:
            # Tokenize and count
            encoded = tokenizer.encode(text)
            count = len(encoded.ids)
            elapsed_ms = (time.perf_counter() - start) * 1000

            return TokenCountResult(
                count=count,
                method="qwen_tokenizer",
                estimated=False,
                provider="ollama",
                model=model,
                latency_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"[QwenTokenCounter] Tokenization failed: {e}, falling back to heuristic")
            return await self.heuristic.count(text, provider, model)
