"""
IntentRouter: Pure LLM-Assisted Intent Classification Coordinator.

Pipeline:
  User Requirement
         │
         ▼
  LLM Classifier ──► High Confidence ──► Classify
         │
   Low Conf (< 0.60) / Failure
         ▼
       CLARIFY (Never IMPLEMENT)
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.agent.intent.contracts import Intent, IntentResult
from backend.agent.intent.llm_classifier import classify_with_llm
from backend.ai.service import LLMService

logger = logging.getLogger(__name__)


class IntentRouter:
    """
    Coordinates LLM-assisted intent classification with conservative safety rules.
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service

    def classify(self, requirement: str) -> IntentResult:
        """
        Classifies user requirement using pure LLM understanding.
        Guarantees that uncertainty never defaults to IMPLEMENT.
        """
        if not requirement or not requirement.strip():
            return IntentResult(
                intent=Intent.CLARIFY,
                confidence=1.0,
                reason="Empty or whitespace-only requirement",
                classification_method="empty_check",
            )

        logger.info("IntentRouter: Classifying user requirement via LLM")
        llm_result = classify_with_llm(requirement, llm_service=self.llm_service)

        # Invariant: Any uncertain or low-confidence classification cannot be IMPLEMENT
        if llm_result.confidence < 0.60 and llm_result.intent == Intent.IMPLEMENT:
            logger.warning("IntentRouter Invariant Guard: Low confidence on IMPLEMENT forced to CLARIFY")
            return IntentResult(
                intent=Intent.CLARIFY,
                confidence=llm_result.confidence,
                reason=f"Uncertain implementation request forced to CLARIFY: {llm_result.reason}",
                classification_method="fallback",
            )

        return llm_result
