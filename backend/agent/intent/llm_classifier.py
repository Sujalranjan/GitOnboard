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
from backend.config import settings

logger = logging.getLogger(__name__)

CLASSIFICATION_SYSTEM_PROMPT = """You are an intelligent intent understanding engine for a repository intelligence platform.
Analyze the user's requirement and classify it into EXACTLY ONE of the following intents:
- chat: Greetings, pleasantries, polite chit-chat, casual conversational remarks, non-task talk ("hi", "hello", "hey", "thanks", "who are you", "what can you do").
- explain: Conceptual explanations, architecture overviews, workflow explanations, or questions about how/why something works ("what are github workflow doing in this project", "explain github actions used here", "how does auth work?", "what does please.py do?", "describe the project structure").
- explore: Targeted symbol or file discovery and navigation ("where is auth defined?", "find class Config", "list all files", "show repository tree").
- plan: Feature design or estimation requests without asking to modify code immediately ("how would we add stripe billing?", "what would it take to migrate to postgres?").
- implement: Actionable instructions to write code, modify files, fix bugs, or build features ("add OAuth login", "fix error in test_pls.py", "create endpoint /users").
- clarify: Completely ambiguous, underspecified, or unintelligible requests ("make it better", "do the thing", "fix it").

IMPORTANT RULES:
1. Questions asking WHAT something does, HOW something works, or to EXPLAIN any workflow/module MUST be classified as 'explain'.
2. Greetings and general pleasantries MUST be classified as 'chat'.
3. Only classify as 'implement' if the user is explicitly requesting code changes to be generated or applied.
4. Respond with ONLY valid JSON with keys:
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
        model=settings.model_intent_router,
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
