"""
Groq token counter using tiktoken o200k_harmony with estimated ChatML framing overhead.
"""

import json
import logging
import time
from typing import Any

from .base import TokenCounter, TokenCountResult, RequestTokenCount
from .heuristic import HeuristicTokenCounter

logger = logging.getLogger(__name__)


class GroqTokenCounter(TokenCounter):
    """
    Token counter for Groq openai/gpt-oss-120b using local tiktoken (o200k_harmony).

    Accounts for:
    - Message contents
    - Estimated ChatML envelope overhead (<|im_start|>{role}\\n...<|im_end|> -> ~4 tokens/msg)
    - Assistant tool calls (name and arguments)
    - Serialized tool schemas
    Marks is_exact=False because Groq's exact server-side formatting is proprietary.
    """

    def __init__(self):
        self.heuristic = HeuristicTokenCounter()
        self._encoding = None
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding("o200k_harmony")
        except Exception as e:
            logger.warning(f"[GroqTokenCounter] Failed to load o200k_harmony encoding: {e}")

    async def count(self, text: str, provider: str, model: str) -> TokenCountResult:
        """Count tokens in raw text using o200k_harmony."""
        start = time.perf_counter()
        if not self._encoding:
            return await self.heuristic.count(text, provider, model)

        try:
            tokens = len(self._encoding.encode(text))
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TokenCountResult(
                count=tokens,
                method="tiktoken_o200k_harmony",
                estimated=True,  # Server-side ChatML template introduces framing variance
                provider=provider or "groq",
                model=model,
                latency_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"[GroqTokenCounter] Tokenization error: {e}, falling back to heuristic")
            return await self.heuristic.count(text, provider, model)

    async def count_request(self, request: Any, provider: str, model: str) -> RequestTokenCount:
        """
        Count total tokens in full LLMRequest using o200k_harmony and ChatML framing estimates.
        """
        start = time.perf_counter()
        if not self._encoding:
            return await super().count_request(request, provider, model)

        try:
            total_tokens = 0
            message_tokens = 0
            framing_tokens = 0
            tool_schema_tokens = 0

            # 1. Message contents + ChatML framing
            messages = getattr(request, "messages", [])
            for m in messages:
                # ~4 tokens per message for <|im_start|>{role}\n...<|im_end|>\n
                framing_tokens += 4
                content = getattr(m, "content", "") or ""
                if content:
                    msg_tok = len(self._encoding.encode(content))
                    message_tokens += msg_tok

                # Assistant tool calls if present
                tool_calls = getattr(m, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            fn = tc.get("function", {})
                            name = fn.get("name", "")
                            args = fn.get("arguments", "")
                            framing_tokens += 4  # overhead for tool call envelope
                            if name:
                                message_tokens += len(self._encoding.encode(name))
                            if args:
                                if not isinstance(args, str):
                                    args = json.dumps(args)
                                message_tokens += len(self._encoding.encode(args))

            # 2. Tool schemas
            tools = getattr(request, "tools", None) or []
            for t in tools:
                tool_schema_tokens += len(self._encoding.encode(t.name))
                tool_schema_tokens += len(self._encoding.encode(t.description or ""))
                if hasattr(t, "parameters") and t.parameters:
                    params_str = json.dumps(t.parameters)
                    tool_schema_tokens += len(self._encoding.encode(params_str))
                # Function specification framing overhead
                tool_schema_tokens += 10

            # Priming overhead (assistant response initiation: <|im_start|>assistant\n)
            framing_tokens += 3

            total_tokens = message_tokens + framing_tokens + tool_schema_tokens
            elapsed_ms = (time.perf_counter() - start) * 1000

            return RequestTokenCount(
                total_tokens=total_tokens,
                message_tokens=message_tokens,
                tool_schema_tokens=tool_schema_tokens,
                framing_overhead_tokens=framing_tokens,
                is_exact=False,  # Framing is an estimate
                method="groq_tiktoken_o200k_estimated",
                provider=provider or "groq",
                model=model,
                latency_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"[GroqTokenCounter] Full request count failed: {e}, falling back to super")
            return await super().count_request(request, provider, model)
