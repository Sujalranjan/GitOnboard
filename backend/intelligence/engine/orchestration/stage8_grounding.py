"""
Stage 8: LLM Integration & Grounding Validation

Calls existing LLMService with assembled repository context.
Implements deterministic grounding validation against provided evidence.
"""
import logging
import asyncio
import re
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from backend.ai.service import get_llm_service
from backend.ai.schemas import LLMRequest, Message
from backend.agent.context.contracts import RepositoryContext

logger = logging.getLogger(__name__)


@dataclass
class GroundingValidationResult:
    """Result from grounding validation."""
    query: str
    answer: str
    grounded_entities: List[str]
    grounding_status: str  # "grounded", "partial", "ungrounded", "insufficient_context"
    validation_errors: List[str]
    evidence_size_kb: float
    llm_latency: float


class GroundingValidator:
    """Validates that LLM answers are grounded in provided repository evidence."""

    def __init__(self, context: RepositoryContext):
        self.context = context
        self.file_names = set(context.relevant_files or [])
        self.symbol_names = set()
        self.entity_names = set()

        # Extract entity names from context
        if context.relevant_symbols:
            for sym in context.relevant_symbols:
                if isinstance(sym, dict):
                    self.symbol_names.add(sym.get("name", ""))
                    self.symbol_names.add(sym.get("full_name", ""))

        if context.evidence:
            for evidence in context.evidence:
                if evidence.source_id:
                    self.entity_names.add(evidence.source_id)
                if evidence.summary:
                    # Extract entity names from summary
                    words = evidence.summary.split()
                    for word in words:
                        if len(word) > 3 and word.isidentifier():
                            self.entity_names.add(word)

    def validate(self, answer: str) -> GroundingValidationResult:
        """
        Validate that answer references entities from provided context.

        Strategy:
        1. Extract file paths/symbols from answer using regex
        2. Check if extracted entities exist in context
        3. Classify grounding status

        Args:
            answer: LLM-generated answer

        Returns:
            GroundingValidationResult
        """
        # Extract potential file paths (heuristic: path-like strings with / or \)
        extracted_files = re.findall(r'[\w\-./\\]+\.[\w]+', answer)
        extracted_files = [f for f in extracted_files if '/' in f or '\\' in f]
        extracted_files = [f.replace('\\', '/') for f in extracted_files]

        # Extract potential symbol/function/class names (capitalized or snake_case)
        extracted_symbols = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b|\b[a-z_][a-z0-9_]*\([^)]*\)\b', answer)

        # Check grounding
        grounded_files = [f for f in extracted_files if f in self.file_names]
        grounded_symbols = [s for s in extracted_symbols if s in self.symbol_names or s in self.entity_names]

        grounded_entities = grounded_files + grounded_symbols
        errors = []

        # Determine grounding status
        if not self.context.evidence or len(self.context.evidence) < 2:
            status = "insufficient_context"
            errors.append("Context has no or minimal evidence")
        elif not extracted_files and not extracted_symbols:
            status = "ungrounded"
            errors.append("Answer contains no repository-specific references")
        elif len(grounded_entities) > 0:
            if len(grounded_entities) >= len(set(extracted_files + extracted_symbols)):
                status = "grounded"
            else:
                status = "partial"
                errors.append(f"Some references not grounded: {set(extracted_files + extracted_symbols) - set(grounded_entities)}")
        else:
            status = "ungrounded"
            errors.append("Extracted entities not found in provided context")

        return GroundingValidationResult(
            query=self.context.requirement,
            answer=answer,
            grounded_entities=grounded_entities,
            grounding_status=status,
            validation_errors=errors,
            evidence_size_kb=len(str(self.context.evidence)) / 1024 if self.context.evidence else 0.0,
            llm_latency=0.0,  # Set by caller
        )


class LLMGrounder:
    """Stage 8: Call LLMService with grounded repository context."""

    def __init__(self):
        self.llm_service = get_llm_service()

    async def ground(self, context: RepositoryContext, query: str) -> tuple[str, GroundingValidationResult]:
        """
        Call LLMService with repository context. Validate grounding.

        Args:
            context: RepositoryContext from Stage 7
            query: Original user query

        Returns:
            (answer: str, grounding_result: GroundingValidationResult)
        """
        import time
        start_time = time.time()

        # LOG: What context are we receiving from Stage 7?
        logger.info(f"\n[Stage 8] RECEIVED CONTEXT FROM STAGE 7:")
        logger.info(f"  Relevant files: {len(context.relevant_files or [])} - {context.relevant_files[:3]}")
        logger.info(f"  Relevant symbols: {len(context.relevant_symbols or [])}")
        logger.info(f"  Evidence items: {len(context.evidence or [])}")

        # Check for actual code in evidence
        code_evidence = []
        if context.evidence:
            for i, ev in enumerate(context.evidence[:5]):
                logger.info(f"  Evidence[{i}]: type={ev.source_type}, source_id={ev.source_id}")
                if ev.data and "content" in ev.data:
                    content_len = len(ev.data.get("content", ""))
                    code_evidence.append(f"{ev.source_id} ({content_len} chars)")
                    logger.info(f"    → HAS CODE: {content_len} chars")
                    logger.info(f"    → First 300 chars:\n{ev.data.get('content', '')[:300]}")
                else:
                    logger.info(f"    → NO CODE (only metadata)")

        logger.info(f"  Total evidence items with actual code: {len(code_evidence)}")

        # Build grounding message
        context_json = context.model_dump_json(indent=2) if hasattr(context, 'model_dump_json') else str(context)
        logger.info(f"\n[Stage 8] CONTEXT JSON SIZE: {len(context_json)} chars ({len(context_json)/1024:.1f}KB)")
        logger.info(f"  First 500 chars of context:\n{context_json[:500]}")

        # DEBUG: Check if source_excerpt items with code are in the JSON
        logger.info(f"\n[Stage 8] CHECKING FOR SOURCE CODE IN JSON:")
        if '"source_excerpt"' in context_json:
            logger.info(f"  ✓ Found source_excerpt items in JSON")
            # Count occurrences
            count = context_json.count('"source_excerpt"')
            logger.info(f"  ✓ Total source_excerpt items: {count}")
            # Check for actual code content
            if '"content"' in context_json:
                logger.info(f"  ✓ Found 'content' fields in JSON")
                # Check size - content should be substantial
                github_oauth_pos = context_json.find("github_oauth")
                if github_oauth_pos > 0:
                    sample = context_json[max(0, github_oauth_pos-100):min(len(context_json), github_oauth_pos+500)]
                    logger.info(f"  Sample around github_oauth: {sample}")
        else:
            logger.warning(f"  ❌ NO source_excerpt items found in JSON!")
            if '"content"' not in context_json:
                logger.warning(f"  ❌ NO 'content' fields found in JSON!")

        messages = [
            Message(
                role="system",
                content="""You are a code analyst with access to repository structure.

IMPORTANT:
1. Answer ONLY using the provided repository context.
2. If information is not in the context, say "This information is not available in the provided context."
3. Cite specific file paths and symbol names from the context when possible.
4. Do not make assumptions about code you have not seen.
5. Be concise and precise."""
            ),
            Message(
                role="user",
                content=f"""Repository Context (from retrieval + graph traversal):
{context_json}

Question: {query}

Answer based ONLY on the provided context. Cite specific files and symbols."""
            )
        ]

        # Call LLMService
        try:
            request = LLMRequest(
                messages=messages,
                temperature=0.2,  # Deterministic
                max_tokens=1024,
            )

            response = await self.llm_service.generate(request)
            answer = response.content if hasattr(response, 'content') else str(response)

            llm_latency = time.time() - start_time

            # LOG: What did LLM receive and respond with?
            logger.info(f"\n[Stage 8] LLM CALL COMPLETED:")
            logger.info(f"  Latency: {llm_latency:.2f}s")
            logger.info(f"  Query sent: {query}")
            logger.info(f"  Context size sent: {len(context_json)/1024:.1f}KB")
            logger.info(f"  Answer received ({len(answer)} chars):")
            logger.info(f"    {answer[:500]}")
            if len(answer) > 500:
                logger.info(f"    ... [truncated] ...")
                logger.info(f"    {answer[-300:]}")

            # Validate grounding
            validator = GroundingValidator(context)
            grounding_result = validator.validate(answer)
            grounding_result.llm_latency = llm_latency

            logger.info(
                f"[Stage 8] LLM answer generated: {len(answer)} chars, "
                f"grounding={grounding_result.grounding_status}, "
                f"latency={llm_latency:.2f}s"
            )

            return answer, grounding_result

        except Exception as e:
            logger.error(f"[Stage 8] LLMService failed: {e}")
            raise


def stage8_sync_wrapper(context: RepositoryContext, query: str) -> tuple[str, GroundingValidationResult]:
    """
    Synchronous wrapper for Stage 8 (for integration with sync validation scripts).

    Args:
        context: RepositoryContext from Stage 7
        query: Original user query

    Returns:
        (answer: str, grounding_result: GroundingValidationResult)
    """
    grounder = LLMGrounder()
    try:
        return asyncio.run(grounder.ground(context, query))
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            # Already in async context, use await instead
            logger.warning("[Stage 8] Already in event loop, cannot use asyncio.run()")
            raise
        raise
