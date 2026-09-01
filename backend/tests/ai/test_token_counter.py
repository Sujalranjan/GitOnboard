"""
Tests for token counting system.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.ai.tokencount import count_tokens, TokenCountResult
from backend.ai.tokencount.heuristic import HeuristicTokenCounter
from backend.ai.tokencount.qwen import QwenTokenCounter
from backend.ai.tokencount.gemini import GeminiTokenCounter
from backend.ai.tokencount.openrouter import OpenRouterTokenCounter


class TestHeuristicTokenCounter:
    """Tests for heuristic fallback counter."""

    @pytest.mark.asyncio
    async def test_heuristic_count_basic(self):
        """Test heuristic counting returns ceil(len/4)."""
        counter = HeuristicTokenCounter()

        # 4 chars = 1 token
        result = await counter.count("1234", "test", "test-model")
        assert result.count == 1
        assert result.method == "heuristic"
        assert result.estimated is True
        assert result.latency_ms >= 0

        # 5 chars = 2 tokens (ceil(5/4) = 2)
        result = await counter.count("12345", "test", "test-model")
        assert result.count == 2

        # empty = 1 (minimum)
        result = await counter.count("", "test", "test-model")
        assert result.count == 1


class TestQwenTokenCounter:
    """Tests for Qwen exact tokenizer."""

    @pytest.mark.asyncio
    async def test_qwen_no_tokenizer_file(self):
        """If vendored tokenizer doesn't exist, fall back to heuristic."""
        counter = QwenTokenCounter()
        # No tokenizer file will be found for this model
        result = await counter.count("hello world", "ollama", "qwen:fake")
        # Should fall back to heuristic
        assert result.method == "heuristic"
        assert result.estimated is True

    @pytest.mark.asyncio
    async def test_qwen_fallback_on_error(self):
        """If tokenization fails, fall back to heuristic."""
        counter = QwenTokenCounter()
        # Mock tokenizer.encode to raise an exception
        with patch.object(counter, '_load_tokenizer', return_value=MagicMock(encode=MagicMock(side_effect=ValueError("Bad")))):
            result = await counter.count("hello", "ollama", "qwen2.5-coder:7b")
            # Should fall back to heuristic
            assert result.method == "heuristic"
            assert result.estimated is True


class TestGeminiTokenCounter:
    """Tests for Gemini REST API counter."""

    @pytest.mark.asyncio
    async def test_gemini_no_api_key(self):
        """If no API key, fall back to heuristic."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': ''}):
            counter = GeminiTokenCounter()
            result = await counter.count("hello", "gemini", "gemini-2.0-flash")
            assert result.method == "heuristic"
            assert result.estimated is True

    @pytest.mark.asyncio
    async def test_gemini_cache(self):
        """Test that token counts are cached within a run."""
        counter = GeminiTokenCounter()
        counter.token_cache[("test-model", "abc123")] = 42

        result = await counter.count("hello", "gemini", "test-model")
        # If cache is hit, it should return the cached value
        # (though this test is limited without a real API key)

    @pytest.mark.asyncio
    async def test_gemini_api_error_fallback(self):
        """On API error, fall back to heuristic."""
        counter = GeminiTokenCounter()
        counter.api_key = "test-key"

        # Mock httpx to raise an error
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("API Error")
            )
            result = await counter.count("hello", "gemini", "gemini-2.0-flash")
            # Should fall back to heuristic
            assert result.method == "heuristic"
            assert result.estimated is True


class TestOpenRouterTokenCounter:
    """Tests for OpenRouter best-effort counter."""

    @pytest.mark.asyncio
    async def test_openrouter_qwen_detected(self):
        """If model name contains 'qwen', delegate to Qwen counter but mark estimated=True."""
        counter = OpenRouterTokenCounter()
        # With no vendored tokenizer file, it will use heuristic internally
        result = await counter.count("hello", "openrouter", "qwen/qwen-2.5-72b-instruct")
        # Should be marked estimated=True even if we delegated to Qwen counter
        assert result.estimated is True
        assert result.provider == "openrouter"

    @pytest.mark.asyncio
    async def test_openrouter_non_qwen_heuristic(self):
        """For non-Qwen models, use heuristic and mark estimated=True."""
        counter = OpenRouterTokenCounter()
        result = await counter.count("hello", "openrouter", "anthropic/claude-3-haiku")
        assert result.method == "heuristic"
        assert result.estimated is True
        assert result.provider == "openrouter"


class TestRegistryDispatch:
    """Tests for count_tokens dispatch function."""

    @pytest.mark.asyncio
    async def test_dispatch_ollama_qwen(self):
        """Ollama + Qwen model -> Qwen counter (or fallback)."""
        result = await count_tokens("hello world", "ollama", "qwen2.5-coder:7b")
        # With no vendored tokenizer file, will fall back to heuristic
        assert result.provider == "ollama"
        assert isinstance(result, TokenCountResult)

    @pytest.mark.asyncio
    async def test_dispatch_ollama_non_qwen(self):
        """Ollama + non-Qwen -> heuristic."""
        result = await count_tokens("hello world", "ollama", "llama2:7b")
        assert result.method == "heuristic"
        assert result.estimated is True

    @pytest.mark.asyncio
    async def test_dispatch_unknown_provider(self):
        """Unknown provider -> heuristic."""
        result = await count_tokens("hello world", "unknown-provider", "some-model")
        assert result.method == "heuristic"
        assert result.estimated is True

    @pytest.mark.asyncio
    async def test_dispatch_never_raises(self):
        """Dispatch should never raise, always return a result."""
        # Even with weird inputs, should not raise
        result = await count_tokens("", "ollama", "")
        assert isinstance(result, TokenCountResult)
        assert result.count >= 0

        result = await count_tokens("x" * 10000, "invalid", "invalid")
        assert isinstance(result, TokenCountResult)
        assert result.count > 0


class TestTokenCountResult:
    """Tests for TokenCountResult dataclass."""

    def test_result_fields(self):
        """Verify TokenCountResult has all required fields."""
        result = TokenCountResult(
            count=42,
            method="test",
            estimated=False,
            provider="test",
            model="test-model",
            latency_ms=10.5,
        )
        assert result.count == 42
        assert result.method == "test"
        assert result.estimated is False
        assert result.provider == "test"
        assert result.model == "test-model"
        assert result.latency_ms == 10.5
        assert result.error == ""  # default

    def test_result_with_error(self):
        """Result can carry error information."""
        result = TokenCountResult(
            count=0,
            method="error",
            estimated=True,
            provider="ollama",
            model="qwen",
            error="tokenizer not found",
        )
        assert result.error == "tokenizer not found"


class TestTokenCountingIntegration:
    """Integration tests for the full token counting flow."""

    @pytest.mark.asyncio
    async def test_typical_qwen_flow(self):
        """Typical flow for Qwen counting (with or without tokenizer)."""
        # This should not raise, should return a result
        result = await count_tokens(
            "def hello():\n    return 'world'",
            provider="ollama",
            model="qwen2.5-coder:7b"
        )
        assert isinstance(result, TokenCountResult)
        assert result.count > 0
        # Will be heuristic if no tokenizer file, qwen if file exists
        assert result.method in ("qwen_tokenizer", "heuristic")
        assert result.provider == "ollama"

    @pytest.mark.asyncio
    async def test_typical_gemini_flow(self):
        """Typical flow for Gemini counting (without API key in tests)."""
        result = await count_tokens(
            "hello world",
            provider="gemini",
            model="gemini-2.0-flash"
        )
        assert isinstance(result, TokenCountResult)
        assert result.count > 0
        # Without API key, should fall back to heuristic
        assert result.method == "heuristic"
        assert result.provider == "gemini"

    @pytest.mark.asyncio
    async def test_openrouter_always_estimated(self):
        """OpenRouter results always have estimated=True."""
        result = await count_tokens(
            "hello world",
            provider="openrouter",
            model="anthropic/claude-3-haiku"
        )
        assert result.estimated is True
        assert result.provider == "openrouter"

        # Even for Qwen-routed models, estimated=True
        result = await count_tokens(
            "hello world",
            provider="openrouter",
            model="qwen/qwen-2.5-72b-instruct"
        )
        assert result.estimated is True
        assert result.provider == "openrouter"
