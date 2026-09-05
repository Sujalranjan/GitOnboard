"""RIM Comparison research endpoint (v2 - agentic loop-based)."""
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse
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
