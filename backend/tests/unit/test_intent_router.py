"""
Unit tests for Intent Router & Pure LLM Intent Classification.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from backend.agent.intent import (
    Intent,
    IntentResult,
    IntentRouter,
    classify_with_llm,
)
from backend.ai.service import LLMService
from backend.ai.schemas import LLMResponse, TokenUsage


def test_intent_router_empty_input():
    mock_service = MagicMock(spec=LLMService)
    router = IntentRouter(llm_service=mock_service)
    result = router.classify("   ")
    assert result.intent == Intent.CLARIFY
    mock_service.generate_structured.assert_not_called()


def test_intent_router_delegates_to_llm():
    mock_service = MagicMock(spec=LLMService)

    async def mock_structured(request, schema):
        return schema(intent="explain", confidence=0.95, reason="User asks to explain workflows")

    mock_service.generate_structured = AsyncMock(side_effect=mock_structured)

    router = IntentRouter(llm_service=mock_service)
    result = router.classify("what are github workflow doing in this project")
    assert result.intent == Intent.EXPLAIN
    assert result.confidence == 0.95
    assert result.classification_method == "llm"


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


def test_intent_router_safety_invariant_no_uncertain_implement():
    mock_service = MagicMock(spec=LLMService)
    
    async def mock_structured(request, schema):
        return schema(intent="implement", confidence=0.55, reason="Tentative guess")
    
    mock_service.generate_structured = AsyncMock(side_effect=mock_structured)

    router = IntentRouter(llm_service=mock_service)
    result = router.classify("vague request")

    assert result.intent != Intent.IMPLEMENT
    assert result.intent == Intent.CLARIFY
