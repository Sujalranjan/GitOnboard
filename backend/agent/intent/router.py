"""
IntentRouter: Two-Stage Intent Classification Coordinator (Phase 2).

Pipeline:
  User Requirement
         │
  Deterministic Rules ──► Match (conf >= 0.85) ──► Accept
         │
     Ambiguous
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
from backend.agent.intent.deterministic import classify_deterministic
from backend.agent.intent.llm_classifier import classify_with_llm
from backend.ai.service import LLMService

logger = logging.getLogger(__name__)


class IntentRouter:
    """
    Coordinates deterministic and LLM-assisted intent classification with conservative safety rules.
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service

    def classify(self, requirement: str) -> IntentResult:
        """
        Classifies user requirement using two-stage pipeline.
        Guarantees that uncertainty never defaults to IMPLEMENT.
        """
        # Stage 1: Deterministic evaluation
        det_result = classify_deterministic(requirement)
        if det_result is not None and det_result.confidence >= 0.85:
            logger.info(
                f"IntentRouter: Deterministic match '{det_result.intent.value}' (confidence={det_result.confidence:.2f})"
            )
            return det_result

        # Stage 2: LLM classifier evaluation
        logger.info("IntentRouter: Deferring to LLM classifier for requirement classification")
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
