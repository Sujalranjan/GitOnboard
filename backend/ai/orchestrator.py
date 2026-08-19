"""
LLM Orchestrator — Central coordinator for LLM tasks across GitOnboard.
Owns task routing, context assembly, prompt selection, and synthesis formatting.
Delegates provider dispatch to LLMService and falls back to deterministic synthesis.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.ai.service import LLMService, get_llm_service
from backend.ai.schemas import LLMRequest, Message, MessageRole, NonRetriableError, RetriableError
from backend.ai.context.trace import TraceContextBuilder
from backend.ai.prompts.trace import TRACE_EXPLANATION_SYSTEM_PROMPT, TRACE_EXPLANATION_USER_TEMPLATE
from backend.ai.fallback import DeterministicFallbackSynthesizer

logger = logging.getLogger(__name__)


class LLMOrchestrator:
    """
    Coordinates task-specific context assembly, prompt formatting,
    provider dispatch via LLMService, and deterministic fallback handling.
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        db: Optional[Session] = None,
        analysis_id: Optional[int] = None,
        repo_name: Optional[str] = None,
        user_id: Optional[int] = None,
    ):
        self.llm = llm_service or get_llm_service()
        self.db = db
        self.analysis_id = analysis_id
        self.repo_name = repo_name
        self.user_id = user_id

    async def explain_trace(
        self,
        feature_query: str,
        trace_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generates a rich, source-grounded explanation for a feature trace.
        Falls back to DeterministicFallbackSynthesizer if providers fail.
        """
        # 1. Assemble Deep Context (Signatures + Routes + Source Snippets)
        ctx_builder = TraceContextBuilder(
            db=self.db,
            analysis_id=self.analysis_id,
            repo_name=self.repo_name,
            user_id=self.user_id
        )
        context_block = ctx_builder.build_context(trace_data)

        # 2. Build Formatted Request
        system_prompt = TRACE_EXPLANATION_SYSTEM_PROMPT.format(feature_query=feature_query)
        user_prompt = TRACE_EXPLANATION_USER_TEMPLATE.format(
            feature_query=feature_query,
            context_block=context_block
        )

        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=user_prompt),
            ],
            temperature=0.2,
            max_tokens=3000,
        )

        # 3. Execute via Provider Gateway with Fallback Handling
        try:
            response = await self.llm.generate(request)
            return {
                "explanation": response.content,
                "provider": response.provider,
                "ai_generated": True,
            }
        except Exception as e:
            logger.warning(
                f"LLMOrchestrator: All AI providers failed ({e}). Falling back to deterministic trace synthesizer."
            )
            return DeterministicFallbackSynthesizer.synthesize_trace_explanation(
                feature_query=feature_query,
                trace_data=trace_data
            )
