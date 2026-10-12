"""
Data models and schemas for the GitOnboard Deterministic Benchmark Evaluation Runner.
Defines questions, trajectories, retrieval/answer metrics, trajectory validity, and aggregate summaries.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """
    Top-level execution status of an evaluation run.
    Distinguishes runtime crashes from benchmark test performance.
    """
    SUCCESS = "SUCCESS"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    TIMEOUT = "TIMEOUT"
    MODEL_ERROR = "MODEL_ERROR"
    TOOL_ERROR = "TOOL_ERROR"


class TrajectoryValidity(str, Enum):
    """
    Exhaustive partition of trajectory validity at correctness >= 0.75 & recall >= 0.75,
    plus EXECUTION_FAILURE for infrastructure/runtime errors.
    """
    VALID = "VALID"                              # correctness >= 0.75 AND recall >= 0.75
    LUCKY_CORRECT = "LUCKY_CORRECT"              # correctness >= 0.75 AND recall < 0.75
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # correctness < 0.75 AND recall < 0.75
    INCORRECT = "INCORRECT"                      # correctness < 0.75 AND recall >= 0.75
    EXECUTION_FAILURE = "EXECUTION_FAILURE"      # Crash or runtime infrastructure failure


class FailureCategory(str, Enum):
    """
    Granular failure attribution taxonomy.
    Distinguishes tool usage:
    - UNNECESSARY_TOOL_USE: unnecessary but harmless tool calls
    - INVALID_TOOL_USE: tool inappropriate/unsupported or errored for the task
    - FAILED_TOOL_SELECTION: wrong tool choice materially prevented successful retrieval
    """
    NONE = "NONE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    UNNECESSARY_TOOL_USE = "UNNECESSARY_TOOL_USE"
    INVALID_TOOL_USE = "INVALID_TOOL_USE"
    FAILED_TOOL_SELECTION = "FAILED_TOOL_SELECTION"
    INSUFFICIENT_SEARCH = "INSUFFICIENT_SEARCH"
    GRAPH_FAILURE = "GRAPH_FAILURE"
    SOURCE_READ_FAILURE = "SOURCE_READ_FAILURE"
    CONTEXT_ASSEMBLY_FAILURE = "CONTEXT_ASSEMBLY_FAILURE"
    REASONING_FAILURE = "REASONING_FAILURE"
    HALLUCINATION = "HALLUCINATION"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    ANSWER_INCOMPLETE = "ANSWER_INCOMPLETE"
    CROSS_REPO_LEAKAGE = "CROSS_REPO_LEAKAGE"


class ExperimentalArm(str, Enum):
    """
    The 4 controlled experimental arms.
    """
    MODEL_PRIOR = "model_prior"              # Arm 0: Zero retrieval, zero tools
    CONVENTIONAL_RAG = "conventional_rag"    # Arm 1: Single-turn top-K chunks -> LLM
    GITONBOARD_RAG = "gitonboard_rag"        # Arm 2: GitOnboard hybrid retrieval top-K -> LLM
    GITONBOARD_AGENT = "gitonboard_agent"    # Arm 3: Full QALoop agentic loop with tools & graph


class QuestionBenchmarkSpec(BaseModel):
    """Complete specification of a benchmark question from benchmark/*.json."""
    id: str
    repository: str
    repository_commit: str
    question: str
    category: str
    answer_type: str
    difficulty: str
    required_evidence: List[str] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    decoy_files: List[str] = Field(default_factory=list)
    expected_symbols: List[str] = Field(default_factory=list)
    expected_concepts: List[str] = Field(default_factory=list)
    expected_tool_capabilities: List[str] = Field(default_factory=list)
    expected_answer_points: List[str] = Field(default_factory=list)
    expected_answer_structure: List[str] = Field(default_factory=list)
    requires_multi_hop: bool = False
    requires_graph_reasoning: bool = False
    requires_verification: bool = False
    difficulty_factors: Dict[str, Any] = Field(default_factory=dict)
    known_traps: List[str] = Field(default_factory=list)


class TrajectoryTurn(BaseModel):
    """Single turn recorded in an agent execution trajectory."""
    turn_index: int
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    observation_preview: str = ""
    is_success: bool = True
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: float = 0.0


class ToolEfficiencyMetrics(BaseModel):
    """Detailed tool efficiency and redundancy telemetry."""
    tool_calls: int = 0
    successful_tool_calls: int = 0
    failed_tool_calls: int = 0
    redundant_tool_calls: int = 0
    unique_files_read: int = 0
    search_iterations: int = 0
    tool_success_rate: float = 1.0           # execution_success: whether tool call completed without exception
    useful_evidence_returned: int = 0        # retrieval_success: calls that actually yielded evidence
    retrieval_success_rate: float = 0.0      # useful_evidence_returned / tool_calls
    tool_redundancy_rate: float = 0.0
    time_to_first_useful_evidence_ms: Optional[float] = None
    unnecessary_tool_calls: int = 0
    invalid_tool_calls: int = 0
    failed_tool_selections: int = 0


class RetrievalMetrics(BaseModel):
    """Deterministic retrieval quality metrics."""
    retrieved_files: List[str] = Field(default_factory=list)
    required_evidence_found: List[str] = Field(default_factory=list)
    required_evidence_missed: List[str] = Field(default_factory=list)
    supporting_evidence_found: List[str] = Field(default_factory=list)
    decoy_evidence_used: List[str] = Field(default_factory=list)
    
    # 3-Tier precision and recall
    evidence_recall: float = 0.0          # |retrieved ∩ required| / |required|
    relevant_evidence_precision: float = 0.0  # |retrieved ∩ (required ∪ supporting)| / |retrieved|
    
    # Recall@K
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    
    # Decoy testing
    decoy_hit: int = 0                    # 1 if any decoy used, else 0
    decoy_file_rate: float = 0.0          # |retrieved ∩ decoys| / |decoys|
    
    # Hard Isolation Metric
    cross_repo_files: List[str] = Field(default_factory=list)
    cross_repo_leakage_rate: float = 0.0  # Must be 0.0%


class CitationMetrics(BaseModel):
    """Citation metrics extracted from the final answer text."""
    citation_presence: bool = False
    cited_files: List[str] = Field(default_factory=list)
    valid_citations: List[str] = Field(default_factory=list)
    invalid_citations: List[str] = Field(default_factory=list)
    citation_correctness: float = 0.0     # |valid| / |cited|
    citation_completeness: float = 0.0    # |valid ∩ required| / |required|


class ClaimEntailmentResult(BaseModel):
    """Result of claim-level entailment evaluation."""
    claim_text: str
    referenced_file: Optional[str] = None
    is_entailed: bool = True
    entailment_reason: str = ""


class AnswerMetrics(BaseModel):
    """Answer quality and semantic evaluation metrics."""
    answer_points_hit: List[str] = Field(default_factory=list)
    answer_points_missed: List[str] = Field(default_factory=list)
    correctness: float = 0.0             # |points hit| / |expected points|
    completeness: float = 0.0            # completeness score 0.0 - 1.0
    claims_evaluated: List[ClaimEntailmentResult] = Field(default_factory=list)
    groundedness: float = 1.0            # |entailed claims| / |total claims|
    hallucination_rate: float = 0.0      # 1.0 - groundedness
    judge_score: float = 0.0
    judge_confidence: float = 1.0
    judge_reason: str = ""
    judge_model: str = ""
    judge_prompt_version: str = "v1"
    judge_status: str = "SUCCESS"          # SUCCESS, PARSE_ERROR, MODEL_ERROR, TIMEOUT, EMPTY_ANSWER
    judge_fallback_used: bool = False
    judge_failure_reason: Optional[str] = None



class ExecutionRecord(BaseModel):
    """Complete evaluation record for a single run on a single question."""
    run_id: str
    question_id: str
    repository: str
    repository_commit: str
    arm: ExperimentalArm
    model: str
    temperature: float = 0.0
    iteration: int = 1
    timestamp: str
    
    final_answer: str = ""
    trajectory: List[TrajectoryTurn] = Field(default_factory=list)
    
    # Metrics
    retrieval_metrics: RetrievalMetrics = Field(default_factory=RetrievalMetrics)
    tool_efficiency: ToolEfficiencyMetrics = Field(default_factory=ToolEfficiencyMetrics)
    citation_metrics: CitationMetrics = Field(default_factory=CitationMetrics)
    answer_metrics: AnswerMetrics = Field(default_factory=AnswerMetrics)
    
    # Execution Status
    execution_status: ExecutionStatus = ExecutionStatus.SUCCESS
    
    # Classification
    trajectory_validity: TrajectoryValidity = TrajectoryValidity.INCORRECT
    primary_failure: FailureCategory = FailureCategory.NONE
    
    # Performance
    total_duration_ms: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    error: Optional[str] = None
