"""Helper functions for assembling comparison sides and calculating metrics."""

from __future__ import annotations
import time
from typing import Optional

from backend.ai.tokencount import count_tokens
from backend.config import settings
from backend.intelligence.retrieval import HybridRetriever
from backend.services.qa_loop import QALoopResult
from backend.services.rim_comparison_models import (
    ComparisonSide,
    RetrievalMetrics,
    LLMEfficiencyMetrics,
    AnswerMetrics,
)


def combine_context_blocks(repository_context_block: str, rim_metadata_block: str) -> str:
    """
    Combine repository context and RIM metadata blocks for RIM side.

    Args:
        repository_context_block: Formatted repository context from ContextAssembler
        rim_metadata_block: RIM relationship facts from graph traversal

    Returns:
        Combined block with both context types
    """
    if not repository_context_block and not rim_metadata_block:
        return ""

    combined = []

    # Add repository context first
    if repository_context_block:
        combined.append(repository_context_block)

    # Add RIM metadata second
    if rim_metadata_block:
        combined.append("")
        combined.append("### RIM_RELATIONSHIPS")
        combined.append("")
        combined.append(rim_metadata_block)

    return "\n".join(combined)


async def assemble_comparison_side(
    question: str,
    loop_result: QALoopResult,
    prompt_parts,
    elapsed_ms: float,
    rim_metadata_block: Optional[str] = None,
    retriever: Optional[HybridRetriever] = None,
) -> ComparisonSide:
    """Assemble ComparisonSide from loop result with token accounting."""

    # Compute token accounting
    actual_prompt_tokens = sum(turn.prompt_tokens for turn in loop_result.turns)
    actual_completion_tokens = sum(turn.completion_tokens for turn in loop_result.turns)
    actual_total_tokens = actual_prompt_tokens + actual_completion_tokens

    # In PROD mode, skip token estimation and use API-returned tokens only
    if settings.deployment_type == "PROD":
        estimated_system = None
        estimated_other = None
        estimated_rim = None
        estimated_source = None
        token_counting_ms = 0.0
        reconciliation_diff = 0
    else:
        # Estimate token breakdown (LOCAL mode only)
        t0_counting = time.perf_counter()

        estimated_system = await count_tokens(prompt_parts.grounding_and_protocol_text, "ollama", "qwen")
        estimated_other = await count_tokens(prompt_parts.tool_catalog_text + question, "ollama", "qwen")
        estimated_rim = await count_tokens(rim_metadata_block or "", "ollama", "qwen") if rim_metadata_block else None

        # Source tokens are estimated by accumulating tool observations
        source_texts = []
        for turn in loop_result.turns:
            if turn.tool_observation:
                # Use formatted message (actual text sent to LLM) for source token estimation
                obs = turn.tool_observation
                if obs.get("error"):
                    source_texts.append(str(obs.get("error")))
                else:
                    # Use the formatted message that was actually sent to the LLM
                    formatted_msg = obs.get("formatted_message", "")
                    if formatted_msg:
                        source_texts.append(formatted_msg)

        estimated_source = await count_tokens("\n".join(source_texts), "ollama", "qwen") if source_texts else None

        token_counting_ms = (time.perf_counter() - t0_counting) * 1000

        # Reconciliation
        est_total = (
            (estimated_system.count if estimated_system else 0)
            + (estimated_other.count if estimated_other else 0)
            + (estimated_rim.count if estimated_rim else 0)
            + (estimated_source.count if estimated_source else 0)
        )
        reconciliation_diff = actual_prompt_tokens - est_total

    # Build source context block (concatenation of actual tool observations sent to LLM)
    source_context_lines = []
    for turn in loop_result.turns:
        if turn.tool_call and turn.tool_observation:
            # Use formatted message that was actually sent to the LLM
            obs = turn.tool_observation.get("formatted_message", "")
            if obs:
                source_context_lines.append(f"{obs[:500]}")

    source_context_block = "\n".join(source_context_lines[:100])  # Cap at 100 lines

    # Build tool call transcript
    tool_call_transcript = [
        {
            "turn": turn.turn_index,
            "tool_name": turn.tool_call.get("tool_name", "") if turn.tool_call else None,
            "arguments": turn.tool_call.get("arguments", {}) if turn.tool_call else {},
            "observation_summary": turn.tool_observation.get("formatted_message", "") if turn.tool_observation else "",
        }
        for turn in loop_result.turns
        if turn.tool_call
    ]

    return ComparisonSide(
        answer=loop_result.answer,
        retrieval_metrics=RetrievalMetrics(
            tool_call_count=loop_result.tool_call_count,
            files_retrieved=len(loop_result.files_read),
            symbols_retrieved=len(loop_result.symbols_read),
            rim_entities_accessed_count=len(loop_result.rim_entities_accessed),
            rim_relationship_types_used=loop_result.rim_relationship_types_used,
            retrieval_latency_ms=loop_result.latency_ms.get("tool_total", 0),  # Actual tool execution time only
            semantic_degradation=(
                retriever.semantic_degradation
                if retriever and hasattr(retriever, "semantic_degradation")
                else None
            ),
        ),
        llm_efficiency_metrics=LLMEfficiencyMetrics(
            provider=loop_result.turns[0].provider if loop_result.turns else "",
            model=loop_result.turns[0].model if loop_result.turns else "",
            actual_prompt_tokens=actual_prompt_tokens,
            actual_completion_tokens=actual_completion_tokens,
            actual_total_tokens=actual_total_tokens,
            estimated_system_tokens=estimated_system.count if estimated_system else 0,
            estimated_rim_tokens=estimated_rim.count if estimated_rim else 0,
            estimated_source_tokens=estimated_source.count if estimated_source else 0,
            estimated_other_tokens=estimated_other.count if estimated_other else 0,
            token_estimation_method="api_response" if settings.deployment_type == "PROD" else "heuristic",
            token_estimation_is_approximate=False if settings.deployment_type == "PROD" else True,
            token_reconciliation_diff=reconciliation_diff,
            llm_latency_ms=loop_result.latency_ms.get("llm_total", 0),
            retrieval_latency_ms=loop_result.latency_ms.get("tool_total", 0),
            token_counting_latency_ms=token_counting_ms,
            total_latency_ms=elapsed_ms,
        ),
        answer_metrics=AnswerMetrics(),
        rim_metadata_block=rim_metadata_block,
        source_context_block=source_context_block,
        tool_call_transcript=tool_call_transcript,
        stop_reason=loop_result.stop_reason.value if loop_result.stop_reason else "unknown",
    )
