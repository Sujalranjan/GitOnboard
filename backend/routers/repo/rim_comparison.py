"""RIM Comparison research endpoint."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.services.rim_comparison_service import (
    RIMComparisonService,
    RIMComparisonResult,
    ComparisonSide,
    RetrievalMetrics,
    LLMEfficiencyMetrics,
    AnswerMetrics,
    ContextDiff,
    RIMExecutionTrace
)
from backend.summary.audit import redact_secrets, sanitize_dict_or_list

rim_comparison_router = APIRouter(tags=["rim-comparison"])


# ──────────────────────────────────────────────────────────────────────────
# Pydantic request/response models
# ──────────────────────────────────────────────────────────────────────────

class RIMComparisonRequest(BaseModel):
    question: str


class RetrievalMetricsResponse(BaseModel):
    files_retrieved: int
    symbols_retrieved: int
    rim_relationships_count: int = 0
    rim_discovered_files: int = 0
    rim_discovered_symbols: int = 0
    retrieval_latency_ms: float = 0.0


class LLMEfficiencyMetricsResponse(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    context_size_chars: int = 0
    context_assembly_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
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
    retrieved_files: List[str]
    retrieved_symbols: List[str]
    context_block: str


class ContextDiffResponse(BaseModel):
    files_only_without_rim: List[str]
    shared_files: List[str]
    files_only_with_rim: List[str]


class RIMExecutionTraceResponse(BaseModel):
    """Execution trace with redacted secrets."""
    query: str
    baseline_candidates: List[Dict[str, Any]] = []
    rim_seed_entities: List[Dict[str, Any]] = []
    rim_relationships_traversed: List[Dict[str, Any]] = []
    rim_discovered_entities: List[Dict[str, Any]] = []
    files_added_by_rim: List[str] = []

    context_without_rim: str = ""
    context_with_rim: str = ""

    llm_input_without_rim: List[Dict[str, str]] = []
    llm_input_with_rim: List[Dict[str, str]] = []

    llm_output_without_rim: str = ""
    llm_output_with_rim: str = ""

    token_usage_without_rim: Optional[Dict[str, int]] = None
    token_usage_with_rim: Optional[Dict[str, int]] = None

    latency_without_rim_ms: Dict[str, float] = {}
    latency_with_rim_ms: Dict[str, float] = {}


class RIMComparisonResponse(BaseModel):
    """Complete comparison result."""
    without_rim: ComparisonSideResponse
    with_rim: ComparisonSideResponse

    repository: str
    branch: Optional[str] = None
    commit: Optional[str] = None
    analysis_id: Optional[int] = None

    context_diff: ContextDiffResponse
    trace: RIMExecutionTraceResponse


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
    Compare repository Q&A with and without RIM structural expansion.

    Runs the same question through two identical retrieval + LLM pipelines,
    differing only in expand_with_fact_store (RIM on/off).
    Returns full execution trace showing RIM's contribution.
    """
    service = RIMComparisonService(db=db, repo_name=repo_name, current_user=current_user)
    result = await service.run_comparison(req.question)

    # Redact secrets from contexts and trace before sending to frontend
    result.without_rim.context_block = redact_secrets(result.without_rim.context_block)
    result.with_rim.context_block = redact_secrets(result.with_rim.context_block)
    result.trace.context_without_rim = redact_secrets(result.trace.context_without_rim)
    result.trace.context_with_rim = redact_secrets(result.trace.context_with_rim)

    # Sanitize trace objects
    result.trace.baseline_candidates = sanitize_dict_or_list(result.trace.baseline_candidates)
    result.trace.rim_seed_entities = sanitize_dict_or_list(result.trace.rim_seed_entities)
    result.trace.rim_discovered_entities = sanitize_dict_or_list(result.trace.rim_discovered_entities)
    result.trace.rim_relationships_traversed = sanitize_dict_or_list(result.trace.rim_relationships_traversed)

    # Convert to response model
    return RIMComparisonResponse(
        without_rim=ComparisonSideResponse(
            answer=result.without_rim.answer,
            retrieval_metrics=RetrievalMetricsResponse(**vars(result.without_rim.retrieval_metrics)),
            llm_efficiency_metrics=LLMEfficiencyMetricsResponse(**vars(result.without_rim.llm_efficiency_metrics)),
            answer_metrics=AnswerMetricsResponse(**vars(result.without_rim.answer_metrics)),
            retrieved_files=result.without_rim.retrieved_files,
            retrieved_symbols=result.without_rim.retrieved_symbols,
            context_block=result.without_rim.context_block
        ),
        with_rim=ComparisonSideResponse(
            answer=result.with_rim.answer,
            retrieval_metrics=RetrievalMetricsResponse(**vars(result.with_rim.retrieval_metrics)),
            llm_efficiency_metrics=LLMEfficiencyMetricsResponse(**vars(result.with_rim.llm_efficiency_metrics)),
            answer_metrics=AnswerMetricsResponse(**vars(result.with_rim.answer_metrics)),
            retrieved_files=result.with_rim.retrieved_files,
            retrieved_symbols=result.with_rim.retrieved_symbols,
            context_block=result.with_rim.context_block
        ),
        repository=result.repository,
        branch=result.branch,
        commit=result.commit,
        analysis_id=result.analysis_id,
        context_diff=ContextDiffResponse(**vars(result.context_diff)),
        trace=RIMExecutionTraceResponse(**vars(result.trace))
    )
