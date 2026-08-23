"""
LLM-assisted intent classifier (Stage 2 of Intent Router).

Uses structured JSON generation with conservative fallback to CLARIFY
upon failure, timeout, or low confidence (< 0.60).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional
from pydantic import BaseModel, Field

from backend.agent.intent.contracts import Intent, IntentResult
from backend.ai.service import LLMService, build_default_service
from backend.ai.schemas import LLMRequest, Message, MessageRole

logger = logging.getLogger(__name__)

CLASSIFICATION_SYSTEM_PROMPT = """You are an intent classifier for a repository intelligence platform.
Classify the user's requirement into EXACTLY ONE of the following intents:
- chat: Greetings, pleasantries, polite chit-chat ("hi", "hello", "thanks").
- explore: Codebase navigation, finding files/symbols, inspecting repo layout ("show files", "where is auth?").
- explain: Conceptual explanations, architecture, or logic explanations ("how does auth work?", "why is this used?").
- plan: Architecture queries or change estimation without asking to write code immediately ("what would it take to add OAuth?").
- implement: Clear requests to write code, modify files, fix bugs, or build features ("add OAuth login", "fix bug in auth.py").
- clarify: Underspecified, ambiguous, or vague requests ("make auth better", "improve this", "clean it up").

IMPORTANT RULES:
1. If the user is asking HOW something works or HOW to fix something, classify as 'explain'.
2. If the user asks a question about what would be required, classify as 'plan'.
3. Only classify as 'implement' if the user is explicitly requesting code changes to be made now.
4. When in doubt or if the prompt is ambiguous, classify as 'clarify'.

Respond with ONLY valid JSON with keys:
- "intent": "<chat|explore|explain|plan|implement|clarify>"
- "confidence": <float between 0.0 and 1.0>
- "reason": "<short explanation>"
"""


class LLMIntentResponse(BaseModel):
    intent: str = Field(..., description="Classified intent")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    reason: str = Field(default="", description="Reason for classification")


def _extract_json_from_text(text: str) -> Optional[dict]:
    """Attempts to extract a JSON object from text."""
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


async def classify_with_llm_async(
    requirement: str,
    llm_service: Optional[LLMService] = None,
) -> IntentResult:
    """
    Asynchronously classifies requirement using LLMService.
    """
    service = llm_service or build_default_service()
    req = LLMRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content=CLASSIFICATION_SYSTEM_PROMPT),
            Message(role=MessageRole.USER, content=f"User request to classify:\n'''\n{requirement}\n'''"),
        ],
        temperature=0.0,
        max_tokens=256,
    )

    try:
        # Try structured generation first
        try:
            structured: LLMIntentResponse = await service.generate_structured(req, LLMIntentResponse)
            intent_str = structured.intent.strip().lower()
            confidence = float(structured.confidence)
            reason = structured.reason
        except Exception:
            # Fallback to plain text generation and JSON extraction
            resp = await service.generate(req)
            data = _extract_json_from_text(resp.content)
            if not data or "intent" not in data:
                raise ValueError(f"Could not parse valid intent JSON from response: {resp.content}")
            intent_str = str(data["intent"]).strip().lower()
            confidence = float(data.get("confidence", 0.7))
            reason = str(data.get("reason", "Parsed from text JSON"))

        # Normalize intent string
        try:
            matched_intent = Intent(intent_str)
        except ValueError:
            logger.warning(f"LLM returned invalid intent '{intent_str}'. Falling back to CLARIFY.")
            return IntentResult(
                intent=Intent.CLARIFY,
                confidence=0.5,
                reason=f"LLM returned unrecognized intent: '{intent_str}'",
                classification_method="fallback",
            )

        # Invariant: Low confidence falls back to CLARIFY
        if confidence < 0.60:
            logger.info(f"LLM intent '{matched_intent}' has low confidence ({confidence:.2f}). Forcing CLARIFY.")
            return IntentResult(
                intent=Intent.CLARIFY,
                confidence=confidence,
                reason=f"Low confidence ({confidence:.2f}) from LLM: {reason}",
                classification_method="llm",
            )

        return IntentResult(
            intent=matched_intent,
            confidence=confidence,
            reason=reason,
            classification_method="llm",
        )

    except Exception as err:
        logger.warning(f"LLM classifier failed or timed out: {err}. Safe fallback to CLARIFY.")
        return IntentResult(
            intent=Intent.CLARIFY,
            confidence=0.5,
            reason=f"LLM classification failure: {err}",
            classification_method="fallback",
        )


def classify_with_llm(
    requirement: str,
    llm_service: Optional[LLMService] = None,
) -> IntentResult:
    """
    Synchronous entry point for LLM classification.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    classify_with_llm_async(requirement, llm_service=llm_service),
                )
                return future.result()
        else:
            return loop.run_until_complete(
                classify_with_llm_async(requirement, llm_service=llm_service)
            )
    except RuntimeError:
        return asyncio.run(classify_with_llm_async(requirement, llm_service=llm_service))
