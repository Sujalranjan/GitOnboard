"""Data models and evaluation structures for RIM comparison service."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RetrievalMetrics:
    """Retrieval-phase metrics."""
    tool_call_count: int = 0
    files_retrieved: int = 0
    symbols_retrieved: int = 0
    rim_entities_accessed_count: int = 0
    rim_relationship_types_used: List[str] = field(default_factory=list)
    retrieval_latency_ms: float = 0.0
    semantic_degradation: Optional[str] = None  # Reason semantic search unavailable, if any


@dataclass
class LLMEfficiencyMetrics:
    """LLM execution and token metrics (actual + estimated breakdown)."""
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


@dataclass
class AnswerMetrics:
    """Holder for manual quality evaluation (auto-filled with None for UI scaffolding)."""
    correctness: Optional[str] = None
    grounding: Optional[str] = None
    notes: str = ""


@dataclass
class ComparisonSide:
    """Result of one pipeline (with or without RIM)."""
    answer: str
    retrieval_metrics: RetrievalMetrics
    llm_efficiency_metrics: LLMEfficiencyMetrics
    answer_metrics: AnswerMetrics
    rim_metadata_block: Optional[str] = None  # None for baseline, facts text for RIM
    source_context_block: str = ""
    tool_call_transcript: List[Dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""


@dataclass
class RIMTrace:
    """Comprehensive RIM execution trace showing navigation flow."""
    enabled: bool = False
    query: str = ""

    # Initial retrieval anchors
    anchors: List[Dict[str, Any]] = field(default_factory=list)
    anchor_count: int = 0

    # Graph expansion
    expanded_entities: List[Dict[str, Any]] = field(default_factory=list)
    expansion_count: int = 0
    graph_depth: int = 0
    total_nodes_expanded: int = 0

    # Relationships discovered during expansion
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    relationship_types: List[str] = field(default_factory=list)

    # Selected context
    selected_files: List[str] = field(default_factory=list)
    selected_symbols: List[Dict[str, Any]] = field(default_factory=list)

    # Source locations resolved
    source_locations: List[Dict[str, Any]] = field(default_factory=list)

    # Legacy fields (preserved for backward compatibility)
    rim_metadata_seed_entities: List[Dict[str, Any]] = field(default_factory=list)
    rim_metadata_relationships: List[Dict[str, Any]] = field(default_factory=list)
    query_rim_call_log: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ContextDiff:
    """Files retrieved, grouped by side."""
    files_only_without_rim: List[str] = field(default_factory=list)
    shared_files: List[str] = field(default_factory=list)
    files_only_with_rim: List[str] = field(default_factory=list)


@dataclass
class RIMComparisonResult:
    """Complete comparison result for frontend consumption."""
    without_rim: ComparisonSide
    with_rim: ComparisonSide
    repository: str
    branch: Optional[str] = None
    commit: Optional[str] = None
    analysis_id: Optional[int] = None
    context_diff: ContextDiff = field(default_factory=ContextDiff)
    trace: RIMTrace = field(default_factory=RIMTrace)
