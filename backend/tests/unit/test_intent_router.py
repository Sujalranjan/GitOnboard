"""
Unit tests for Intent Router & Two-Stage Classification (Phase 2).
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from backend.agent.intent import (
    Intent,
    IntentResult,
    IntentRouter,
    classify_deterministic,
    classify_with_llm,
)
from backend.ai.service import LLMService
from backend.ai.schemas import LLMResponse, TokenUsage


# ──────────────────────────────────────────────────────────────────────────────
# 1. Deterministic Rule Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("hi", Intent.CHAT),
        ("hello there", Intent.CHAT),
        ("hey", Intent.CHAT),
        ("thanks!", Intent.CHAT),
        ("thank you very much", Intent.CHAT),
        ("what can you do?", Intent.CHAT),
        ("who are you?", Intent.CHAT),
        ("help", Intent.CHAT),
    ],
)
def test_deterministic_chat_greetings(prompt, expected_intent):
    result = classify_deterministic(prompt)
    assert result is not None
    assert result.intent == expected_intent
    assert result.confidence >= 0.90


@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("show repo tree", Intent.EXPLORE),
        ("show me the repository tree", Intent.EXPLORE),
        ("find AuthService", Intent.EXPLORE),
        ("where is authentication implemented?", Intent.EXPLORE),
        ("where is UserService defined?", Intent.EXPLORE),
        ("find references to DatabaseSession", Intent.EXPLORE),
        ("list all files", Intent.EXPLORE),
    ],
)
def test_deterministic_explore(prompt, expected_intent):
    result = classify_deterministic(prompt)
    assert result is not None
    assert result.intent == expected_intent
    assert result.confidence >= 0.90


@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("how does authentication work?", Intent.EXPLAIN),
        ("why is Zustand used?", Intent.EXPLAIN),
        ("explain the checkout flow", Intent.EXPLAIN),
        ("what does this module do?", Intent.EXPLAIN),
        ("why would I change auth.py?", Intent.EXPLAIN),
        ("how do I fix the login timeout?", Intent.EXPLAIN),  # Asking "how" is explanatory
        ("tell me about the database models", Intent.EXPLAIN),
    ],
)
def test_deterministic_explain(prompt, expected_intent):
    result = classify_deterministic(prompt)
    assert result is not None
    assert result.intent == expected_intent
    assert result.confidence >= 0.90


@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("what would it take to add OAuth?", Intent.PLAN),
        ("what would adding Stripe require?", Intent.PLAN),
        ("how should we implement payments?", Intent.PLAN),
        ("what files would need to change?", Intent.PLAN),
        ("could we add notifications?", Intent.PLAN),
        ("estimate the changes for redis caching", Intent.PLAN),
    ],
)
def test_deterministic_plan(prompt, expected_intent):
    result = classify_deterministic(prompt)
    assert result is not None
    assert result.intent == expected_intent
    assert result.confidence >= 0.90


@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("add Google OAuth", Intent.IMPLEMENT),
        ("implement payments", Intent.IMPLEMENT),
        ("fix the authentication bug", Intent.IMPLEMENT),
        ("modify backend/routers/auth.py", Intent.IMPLEMENT),
        ("refactor UserService", Intent.IMPLEMENT),
        ("create new endpoint for user profile", Intent.IMPLEMENT),
    ],
)
def test_deterministic_implement(prompt, expected_intent):
    result = classify_deterministic(prompt)
    assert result is not None
    assert result.intent == expected_intent
    assert result.confidence >= 0.90


@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("", Intent.CLARIFY),
        ("   ", Intent.CLARIFY),
        ("make auth better", Intent.CLARIFY),
        ("improve this", Intent.CLARIFY),
        ("clean this up", Intent.CLARIFY),
        ("make it faster", Intent.CLARIFY),
        ("fix the project", Intent.CLARIFY),
    ],
)
def test_deterministic_clarify(prompt, expected_intent):
    result = classify_deterministic(prompt)
    assert result is not None
    assert result.intent == expected_intent
    assert result.confidence >= 0.90


def test_negative_constraint_against_mutation():
    prompt = "Do not change anything, just explain how auth works."
    result = classify_deterministic(prompt)
    assert result is not None
    assert result.intent == Intent.EXPLAIN
    assert result.confidence >= 0.95


# ──────────────────────────────────────────────────────────────────────────────
# 2. LLM Classifier & Fallback Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_llm_classifier_structured_success():
    mock_service = MagicMock(spec=LLMService)
    
    async def mock_structured(request, schema):
        return schema(intent="explain", confidence=0.92, reason="User asks about architecture")
    
    mock_service.generate_structured = AsyncMock(side_effect=mock_structured)

    result = classify_with_llm("Can you explain how state transitions work?", llm_service=mock_service)
    assert result.intent == Intent.EXPLAIN
    assert result.confidence == 0.92
    assert result.classification_method == "llm"


def test_llm_classifier_low_confidence_forces_clarify():
    mock_service = MagicMock(spec=LLMService)
    
    async def mock_structured(request, schema):
        # Low confidence on implement
        return schema(intent="implement", confidence=0.45, reason="Unclear if user wants code changes")
    
    mock_service.generate_structured = AsyncMock(side_effect=mock_structured)

    result = classify_with_llm("maybe do something with auth", llm_service=mock_service)
    # Low confidence MUST NOT remain IMPLEMENT
    assert result.intent == Intent.CLARIFY
    assert result.confidence == 0.45


def test_llm_classifier_failure_safe_fallback():
    mock_service = MagicMock(spec=LLMService)
    mock_service.generate_structured = AsyncMock(side_effect=RuntimeError("Provider 503 Timeout"))
    mock_service.generate = AsyncMock(side_effect=RuntimeError("Provider 503 Timeout"))

    result = classify_with_llm("ambiguous requirement", llm_service=mock_service)
    # Failure MUST default to CLARIFY, NEVER IMPLEMENT
    assert result.intent == Intent.CLARIFY
    assert result.classification_method == "fallback"
    assert result.intent != Intent.IMPLEMENT


# ──────────────────────────────────────────────────────────────────────────────
# 3. IntentRouter Coordinator Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_intent_router_deterministic_priority():
    mock_service = MagicMock(spec=LLMService)
    router = IntentRouter(llm_service=mock_service)

    result = router.classify("hi")
    assert result.intent == Intent.CHAT
    assert result.classification_method == "deterministic"
    # LLM should not even be invoked on deterministic match
    mock_service.generate_structured.assert_not_called()


def test_intent_router_safety_invariant_no_uncertain_implement():
    mock_service = MagicMock(spec=LLMService)
    
    async def mock_structured(request, schema):
        return schema(intent="implement", confidence=0.55, reason="Tentative guess")
    
    mock_service.generate_structured = AsyncMock(side_effect=mock_structured)

    router = IntentRouter(llm_service=mock_service)
    result = router.classify("vague request")

    assert result.intent != Intent.IMPLEMENT
    assert result.intent == Intent.CLARIFY
