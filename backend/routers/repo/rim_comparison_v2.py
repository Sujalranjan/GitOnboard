"""RIM Comparison research endpoint (v2 - agentic loop-based)."""
import logging
import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.services.rim_comparison_service_v2 import (
    RIMComparisonService,
    RIMComparisonResult,
    ComparisonSide,
    RetrievalMetrics,
    LLMEfficiencyMetrics,
    AnswerMetrics,
    ContextDiff,
    RIMTrace
)
from backend.summary.audit import redact_secrets, sanitize_dict_or_list
from backend.services.crash_logger import get_crash_logger

logger = logging.getLogger(__name__)

rim_comparison_router = APIRouter(tags=["rim-comparison"])


# ──────────────────────────────────────────────────────────────────────────
# Pydantic request/response models
# ──────────────────────────────────────────────────────────────────────────

class RIMComparisonRequest(BaseModel):
    question: str


class RetrievalMetricsResponse(BaseModel):
    tool_call_count: int = 0
    files_retrieved: int = 0
    symbols_retrieved: int = 0
    rim_entities_accessed_count: int = 0
    rim_relationship_types_used: List[str] = []
    retrieval_latency_ms: float = 0.0


class LLMEfficiencyMetricsResponse(BaseModel):
    provider: str = ""
    model: str = ""
    actual_prompt_tokens: int = 0
    actual_completion_tokens: int = 0
    actual_total_tokens: int = 0
    estimated_system_tokens: int = 0
    estimated_rim_tokens: int = 0
    estimated_source_tokens: int = 0
    estimated_other_tokens: int = 0
    token_estimation_method: str = "heuristic"
    token_estimation_is_approximate: bool = True
    token_reconciliation_diff: int = 0
    llm_latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    token_counting_latency_ms: float = 0.0
    total_latency_ms: float = 0.0


class AnswerMetricsResponse(BaseModel):
    correctness: Optional[str] = None
    grounding: Optional[str] = None
    notes: str = ""


class ComparisonSideResponse(BaseModel):
    answer: str
    retrieval_metrics: RetrievalMetricsResponse
    llm_efficiency_metrics: LLMEfficiencyMetricsResponse
    answer_metrics: AnswerMetricsResponse
    rim_metadata_block: Optional[str] = None
    source_context_block: str = ""
    tool_call_transcript: List[Dict[str, Any]] = []
    stop_reason: str = ""


class ContextDiffResponse(BaseModel):
    files_only_without_rim: List[str] = []
    shared_files: List[str] = []
    files_only_with_rim: List[str] = []


class RIMTraceResponse(BaseModel):
    """Comprehensive RIM execution trace showing navigation flow."""
    enabled: bool = False
    query: str = ""
    anchor_count: int = 0
    anchors: List[Dict[str, Any]] = []
    expansion_count: int = 0
    expanded_entities: List[Dict[str, Any]] = []
    graph_depth: int = 0
    total_nodes_expanded: int = 0
    relationships: List[Dict[str, Any]] = []
    relationship_types: List[str] = []
    selected_files: List[str] = []
    selected_symbols: List[Dict[str, Any]] = []
    source_locations: List[Dict[str, Any]] = []
    # Legacy fields for backward compatibility
    rim_metadata_seed_entities: List[Dict[str, Any]] = []
    rim_metadata_relationships: List[Dict[str, Any]] = []
    query_rim_call_log: List[Dict[str, Any]] = []


class RIMComparisonResponse(BaseModel):
    """Complete comparison result."""
    without_rim: ComparisonSideResponse
    with_rim: ComparisonSideResponse

    repository: str
    branch: Optional[str] = None
    commit: Optional[str] = None
    analysis_id: Optional[int] = None

    context_diff: ContextDiffResponse
    trace: RIMTraceResponse


# ──────────────────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────────────────

@rim_comparison_router.post("/{repo_name}/rim-comparison/compare")
async def compare_rim(
    repo_name: str,
    req: RIMComparisonRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> RIMComparisonResponse:
    """
    Compare repository Q&A with and without RIM structural metadata.

    Runs the same question through two identical agentic Q&A loops,
    differing only in whether RIM metadata + query_rim tool are available.
    Both sides use identical retrieval capabilities and LLM model.

    Returns full comparison including:
    - Answer from each side
    - Separate token accounting (actual vs estimated breakdown)
    - Tool call transcript (proof of iterative one-file-at-a-time retrieval)
    - RIM metadata and query_rim call log (for "What Did RIM Add?" section)
    """
    try:
        service = RIMComparisonService(db=db, repo_name=repo_name, current_user=current_user)
        result = await service.run_comparison(req.question)
    except Exception as exc:
        # Log the crash for debugging
        crash_logger = get_crash_logger()
        crash_logger.log_exception(
            exception=exc,
            endpoint=f"POST /api/repos/{repo_name}/rim-comparison/compare",
            user_id=current_user.id if current_user else None,
            repository_id=repo_name,
            request_body={"question": req.question},
        )
        # Re-raise to let FastAPI return 500
        raise

    # Redact secrets from contexts and trace before sending to frontend
    result.without_rim.source_context_block = redact_secrets(result.without_rim.source_context_block)
    result.with_rim.source_context_block = redact_secrets(result.with_rim.source_context_block)
    result.with_rim.rim_metadata_block = redact_secrets(result.with_rim.rim_metadata_block or "")

    # Sanitize trace objects
    result.trace.rim_metadata_seed_entities = sanitize_dict_or_list(result.trace.rim_metadata_seed_entities)
    result.trace.rim_metadata_relationships = sanitize_dict_or_list(result.trace.rim_metadata_relationships)
    result.trace.query_rim_call_log = sanitize_dict_or_list(result.trace.query_rim_call_log)

    # Sanitize tool call transcripts
    result.without_rim.tool_call_transcript = sanitize_dict_or_list(result.without_rim.tool_call_transcript)
    result.with_rim.tool_call_transcript = sanitize_dict_or_list(result.with_rim.tool_call_transcript)

    # Convert to response model
    return RIMComparisonResponse(
        without_rim=ComparisonSideResponse(
            answer=result.without_rim.answer,
            retrieval_metrics=RetrievalMetricsResponse(
                tool_call_count=result.without_rim.retrieval_metrics.tool_call_count,
                files_retrieved=result.without_rim.retrieval_metrics.files_retrieved,
                symbols_retrieved=result.without_rim.retrieval_metrics.symbols_retrieved,
                rim_entities_accessed_count=result.without_rim.retrieval_metrics.rim_entities_accessed_count,
                rim_relationship_types_used=result.without_rim.retrieval_metrics.rim_relationship_types_used,
                retrieval_latency_ms=result.without_rim.retrieval_metrics.retrieval_latency_ms
            ),
            llm_efficiency_metrics=LLMEfficiencyMetricsResponse(
                provider=result.without_rim.llm_efficiency_metrics.provider,
                model=result.without_rim.llm_efficiency_metrics.model,
                actual_prompt_tokens=result.without_rim.llm_efficiency_metrics.actual_prompt_tokens,
                actual_completion_tokens=result.without_rim.llm_efficiency_metrics.actual_completion_tokens,
                actual_total_tokens=result.without_rim.llm_efficiency_metrics.actual_total_tokens,
                estimated_system_tokens=result.without_rim.llm_efficiency_metrics.estimated_system_tokens,
                estimated_rim_tokens=result.without_rim.llm_efficiency_metrics.estimated_rim_tokens,
                estimated_source_tokens=result.without_rim.llm_efficiency_metrics.estimated_source_tokens,
                estimated_other_tokens=result.without_rim.llm_efficiency_metrics.estimated_other_tokens,
                token_estimation_method=result.without_rim.llm_efficiency_metrics.token_estimation_method,
                token_estimation_is_approximate=result.without_rim.llm_efficiency_metrics.token_estimation_is_approximate,
                token_reconciliation_diff=result.without_rim.llm_efficiency_metrics.token_reconciliation_diff,
                llm_latency_ms=result.without_rim.llm_efficiency_metrics.llm_latency_ms,
                retrieval_latency_ms=result.without_rim.llm_efficiency_metrics.retrieval_latency_ms,
                token_counting_latency_ms=result.without_rim.llm_efficiency_metrics.token_counting_latency_ms,
                total_latency_ms=result.without_rim.llm_efficiency_metrics.total_latency_ms
            ),
            answer_metrics=AnswerMetricsResponse(
                correctness=result.without_rim.answer_metrics.correctness,
                grounding=result.without_rim.answer_metrics.grounding,
                notes=result.without_rim.answer_metrics.notes
            ),
            rim_metadata_block=result.without_rim.rim_metadata_block,
            source_context_block=result.without_rim.source_context_block,
            tool_call_transcript=result.without_rim.tool_call_transcript,
            stop_reason=result.without_rim.stop_reason
        ),
        with_rim=ComparisonSideResponse(
            answer=result.with_rim.answer,
            retrieval_metrics=RetrievalMetricsResponse(
                tool_call_count=result.with_rim.retrieval_metrics.tool_call_count,
                files_retrieved=result.with_rim.retrieval_metrics.files_retrieved,
                symbols_retrieved=result.with_rim.retrieval_metrics.symbols_retrieved,
                rim_entities_accessed_count=result.with_rim.retrieval_metrics.rim_entities_accessed_count,
                rim_relationship_types_used=result.with_rim.retrieval_metrics.rim_relationship_types_used,
                retrieval_latency_ms=result.with_rim.retrieval_metrics.retrieval_latency_ms
            ),
            llm_efficiency_metrics=LLMEfficiencyMetricsResponse(
                provider=result.with_rim.llm_efficiency_metrics.provider,
                model=result.with_rim.llm_efficiency_metrics.model,
                actual_prompt_tokens=result.with_rim.llm_efficiency_metrics.actual_prompt_tokens,
                actual_completion_tokens=result.with_rim.llm_efficiency_metrics.actual_completion_tokens,
                actual_total_tokens=result.with_rim.llm_efficiency_metrics.actual_total_tokens,
                estimated_system_tokens=result.with_rim.llm_efficiency_metrics.estimated_system_tokens,
                estimated_rim_tokens=result.with_rim.llm_efficiency_metrics.estimated_rim_tokens,
                estimated_source_tokens=result.with_rim.llm_efficiency_metrics.estimated_source_tokens,
                estimated_other_tokens=result.with_rim.llm_efficiency_metrics.estimated_other_tokens,
                token_estimation_method=result.with_rim.llm_efficiency_metrics.token_estimation_method,
                token_estimation_is_approximate=result.with_rim.llm_efficiency_metrics.token_estimation_is_approximate,
                token_reconciliation_diff=result.with_rim.llm_efficiency_metrics.token_reconciliation_diff,
                llm_latency_ms=result.with_rim.llm_efficiency_metrics.llm_latency_ms,
                retrieval_latency_ms=result.with_rim.llm_efficiency_metrics.retrieval_latency_ms,
                token_counting_latency_ms=result.with_rim.llm_efficiency_metrics.token_counting_latency_ms,
                total_latency_ms=result.with_rim.llm_efficiency_metrics.total_latency_ms
            ),
            answer_metrics=AnswerMetricsResponse(
                correctness=result.with_rim.answer_metrics.correctness,
                grounding=result.with_rim.answer_metrics.grounding,
                notes=result.with_rim.answer_metrics.notes
            ),
            rim_metadata_block=result.with_rim.rim_metadata_block,
            source_context_block=result.with_rim.source_context_block,
            tool_call_transcript=result.with_rim.tool_call_transcript,
            stop_reason=result.with_rim.stop_reason
        ),
        repository=result.repository,
        branch=result.branch,
        commit=result.commit,
        analysis_id=result.analysis_id,
        context_diff=ContextDiffResponse(
            files_only_without_rim=result.context_diff.files_only_without_rim,
            shared_files=result.context_diff.shared_files,
            files_only_with_rim=result.context_diff.files_only_with_rim
        ),
        trace=RIMTraceResponse(
            enabled=result.trace.enabled,
            query=result.trace.query,
            anchor_count=result.trace.anchor_count,
            anchors=result.trace.anchors,
            expansion_count=result.trace.expansion_count,
            expanded_entities=result.trace.expanded_entities,
            graph_depth=result.trace.graph_depth,
            total_nodes_expanded=result.trace.total_nodes_expanded,
            relationships=result.trace.relationships,
            relationship_types=result.trace.relationship_types,
            selected_files=result.trace.selected_files,
            selected_symbols=result.trace.selected_symbols,
            source_locations=result.trace.source_locations,
            rim_metadata_seed_entities=result.trace.rim_metadata_seed_entities,
            rim_metadata_relationships=result.trace.rim_metadata_relationships,
            query_rim_call_log=result.trace.query_rim_call_log
        )
    )


@rim_comparison_router.post("/{repo_name}/rim-comparison/compare-stream")
async def compare_rim_stream(
    repo_name: str,
    req: RIMComparisonRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stream RIM comparison results progressively.

    Events:
    - without_rim_start: WITHOUT RIM processing started
    - without_rim_complete: WITHOUT RIM result ready
    - with_rim_start: WITH RIM processing started
    - with_rim_complete: WITH RIM result ready and comparison metrics
    - error: Error occurred
    """
    async def stream_generator():
        try:
            service = RIMComparisonService(db=db, repo_name=repo_name, current_user=current_user)

            # Get shared setup (reused for both runs)
            setup = await service.get_shared_setup(req.question)

            # ============ RUN BASELINE ONLY ============
            yield f"data: {json.dumps({'type': 'without_rim_start', 'content': 'Processing WITHOUT RIM...'})}\n\n"

            baseline_side = await service.run_baseline_only(req.question, setup)
            baseline_side.source_context_block = redact_secrets(baseline_side.source_context_block)
            baseline_side.tool_call_transcript = sanitize_dict_or_list(baseline_side.tool_call_transcript)

            # Send WITHOUT RIM result
            without_rim_response = ComparisonSideResponse(
                answer=baseline_side.answer,
                retrieval_metrics=RetrievalMetricsResponse(
                    tool_call_count=baseline_side.retrieval_metrics.tool_call_count,
                    files_retrieved=baseline_side.retrieval_metrics.files_retrieved,
                    symbols_retrieved=baseline_side.retrieval_metrics.symbols_retrieved,
                    rim_entities_accessed_count=baseline_side.retrieval_metrics.rim_entities_accessed_count,
                    rim_relationship_types_used=baseline_side.retrieval_metrics.rim_relationship_types_used,
                    retrieval_latency_ms=baseline_side.retrieval_metrics.retrieval_latency_ms
                ),
                llm_efficiency_metrics=LLMEfficiencyMetricsResponse(
                    provider=baseline_side.llm_efficiency_metrics.provider,
                    model=baseline_side.llm_efficiency_metrics.model,
                    actual_prompt_tokens=baseline_side.llm_efficiency_metrics.actual_prompt_tokens,
                    actual_completion_tokens=baseline_side.llm_efficiency_metrics.actual_completion_tokens,
                    actual_total_tokens=baseline_side.llm_efficiency_metrics.actual_total_tokens,
                    estimated_system_tokens=baseline_side.llm_efficiency_metrics.estimated_system_tokens,
                    estimated_rim_tokens=baseline_side.llm_efficiency_metrics.estimated_rim_tokens,
                    estimated_source_tokens=baseline_side.llm_efficiency_metrics.estimated_source_tokens,
                    estimated_other_tokens=baseline_side.llm_efficiency_metrics.estimated_other_tokens,
                    token_estimation_method=baseline_side.llm_efficiency_metrics.token_estimation_method,
                    token_estimation_is_approximate=baseline_side.llm_efficiency_metrics.token_estimation_is_approximate,
                    token_reconciliation_diff=baseline_side.llm_efficiency_metrics.token_reconciliation_diff,
                    llm_latency_ms=baseline_side.llm_efficiency_metrics.llm_latency_ms,
                    retrieval_latency_ms=baseline_side.llm_efficiency_metrics.retrieval_latency_ms,
                    token_counting_latency_ms=baseline_side.llm_efficiency_metrics.token_counting_latency_ms,
                    total_latency_ms=baseline_side.llm_efficiency_metrics.total_latency_ms
                ),
                answer_metrics=AnswerMetricsResponse(
                    correctness=baseline_side.answer_metrics.correctness,
                    grounding=baseline_side.answer_metrics.grounding,
                    notes=baseline_side.answer_metrics.notes
                ),
                rim_metadata_block=baseline_side.rim_metadata_block,
                source_context_block=baseline_side.source_context_block,
                tool_call_transcript=baseline_side.tool_call_transcript,
                stop_reason=baseline_side.stop_reason
            )

            yield f"data: {json.dumps({'type': 'without_rim_complete', 'without_rim': without_rim_response.model_dump()})}\n\n"

            # ============ RUN RIM (SEPARATE TIMEOUT) ============
            yield f"data: {json.dumps({'type': 'with_rim_start', 'content': 'Processing WITH RIM...'})}\n\n"

            rim_side, rim_metadata = await service.run_rim_only(req.question, setup, setup['repository_context_block'])
            rim_side.source_context_block = redact_secrets(rim_side.source_context_block)
            rim_side.rim_metadata_block = redact_secrets(rim_side.rim_metadata_block or "")
            rim_side.tool_call_transcript = sanitize_dict_or_list(rim_side.tool_call_transcript)

            with_rim_response = ComparisonSideResponse(
                answer=rim_side.answer,
                retrieval_metrics=RetrievalMetricsResponse(
                    tool_call_count=rim_side.retrieval_metrics.tool_call_count,
                    files_retrieved=rim_side.retrieval_metrics.files_retrieved,
                    symbols_retrieved=rim_side.retrieval_metrics.symbols_retrieved,
                    rim_entities_accessed_count=rim_side.retrieval_metrics.rim_entities_accessed_count,
                    rim_relationship_types_used=rim_side.retrieval_metrics.rim_relationship_types_used,
                    retrieval_latency_ms=rim_side.retrieval_metrics.retrieval_latency_ms
                ),
                llm_efficiency_metrics=LLMEfficiencyMetricsResponse(
                    provider=rim_side.llm_efficiency_metrics.provider,
                    model=rim_side.llm_efficiency_metrics.model,
                    actual_prompt_tokens=rim_side.llm_efficiency_metrics.actual_prompt_tokens,
                    actual_completion_tokens=rim_side.llm_efficiency_metrics.actual_completion_tokens,
                    actual_total_tokens=rim_side.llm_efficiency_metrics.actual_total_tokens,
                    estimated_system_tokens=rim_side.llm_efficiency_metrics.estimated_system_tokens,
                    estimated_rim_tokens=rim_side.llm_efficiency_metrics.estimated_rim_tokens,
                    estimated_source_tokens=rim_side.llm_efficiency_metrics.estimated_source_tokens,
                    estimated_other_tokens=rim_side.llm_efficiency_metrics.estimated_other_tokens,
                    token_estimation_method=rim_side.llm_efficiency_metrics.token_estimation_method,
                    token_estimation_is_approximate=rim_side.llm_efficiency_metrics.token_estimation_is_approximate,
                    token_reconciliation_diff=rim_side.llm_efficiency_metrics.token_reconciliation_diff,
                    llm_latency_ms=rim_side.llm_efficiency_metrics.llm_latency_ms,
                    retrieval_latency_ms=rim_side.llm_efficiency_metrics.retrieval_latency_ms,
                    token_counting_latency_ms=rim_side.llm_efficiency_metrics.token_counting_latency_ms,
                    total_latency_ms=rim_side.llm_efficiency_metrics.total_latency_ms
                ),
                answer_metrics=AnswerMetricsResponse(
                    correctness=rim_side.answer_metrics.correctness,
                    grounding=rim_side.answer_metrics.grounding,
                    notes=rim_side.answer_metrics.notes
                ),
                rim_metadata_block=rim_side.rim_metadata_block,
                source_context_block=rim_side.source_context_block,
                tool_call_transcript=rim_side.tool_call_transcript,
                stop_reason=rim_side.stop_reason
            )

            # Calculate metrics differences
            metrics_diff = {
                "tool_calls_diff": rim_side.retrieval_metrics.tool_call_count - baseline_side.retrieval_metrics.tool_call_count,
                "files_diff": rim_side.retrieval_metrics.files_retrieved - baseline_side.retrieval_metrics.files_retrieved,
                "tokens_diff": rim_side.llm_efficiency_metrics.actual_total_tokens - baseline_side.llm_efficiency_metrics.actual_total_tokens,
                "latency_diff_ms": rim_side.llm_efficiency_metrics.total_latency_ms - baseline_side.llm_efficiency_metrics.total_latency_ms,
                "tool_calls_pct": round(((rim_side.retrieval_metrics.tool_call_count - baseline_side.retrieval_metrics.tool_call_count) / max(1, baseline_side.retrieval_metrics.tool_call_count)) * 100, 1) if baseline_side.retrieval_metrics.tool_call_count > 0 else 0,
                "tokens_pct": round(((rim_side.llm_efficiency_metrics.actual_total_tokens - baseline_side.llm_efficiency_metrics.actual_total_tokens) / max(1, baseline_side.llm_efficiency_metrics.actual_total_tokens)) * 100, 1) if baseline_side.llm_efficiency_metrics.actual_total_tokens > 0 else 0,
            }

            yield f"data: {json.dumps({'type': 'with_rim_complete', 'with_rim': with_rim_response.model_dump(), 'metrics_diff': metrics_diff})}\n\n"

        except Exception as exc:
            logger.error(f"Error in compare_rim_stream: {exc}", exc_info=True)
            crash_logger = get_crash_logger()
            crash_logger.log_exception(
                exception=exc,
                endpoint=f"POST /api/repos/{repo_name}/rim-comparison/compare-stream",
                user_id=current_user.id if current_user else None,
                repository_id=repo_name,
                request_body={"question": req.question},
            )
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
