# Phase 3 Schemas
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    TECHNOLOGY = "TECHNOLOGY"
    DEPENDENCY = "DEPENDENCY"
    FILE = "FILE"
    PATH = "PATH"
    SYMBOL = "SYMBOL"
    API = "API"
    DATABASE = "DATABASE"
    DEPLOYMENT = "DEPLOYMENT"
    ENTRYPOINT = "ENTRYPOINT"
    WORKER = "WORKER"
    CONFIGURATION = "CONFIGURATION"
    ARCHITECTURE = "ARCHITECTURE"
    BEHAVIOR = "BEHAVIOR"
    CONTRADICTION = "CONTRADICTION"
    OTHER = "OTHER"


class SupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class HallucinationCategory(str, Enum):
    FABRICATED_PATH = "FABRICATED_PATH"
    FABRICATED_FILE = "FABRICATED_FILE"
    FABRICATED_SYMBOL = "FABRICATED_SYMBOL"
    FALSE_CONTRADICTION = "FALSE_CONTRADICTION"
    INCORRECT_TECHNOLOGY = "INCORRECT_TECHNOLOGY"


class CitationStatus(str, Enum):
    VALID = "VALID"
    INVALID_ID = "INVALID_ID"
    WRONG_FILE = "WRONG_FILE"
    WRONG_LINE_RANGE = "WRONG_LINE_RANGE"
    SNIPPET_MISMATCH = "SNIPPET_MISMATCH"
    NOT_ENTAILED = "NOT_ENTAILED"


class CitationEvaluation(BaseModel):
    evidence_id: str
    status: CitationStatus
    detail: Optional[str] = None


class ValidatorDecision(BaseModel):
    decision: Optional[str] = None  # "ACCEPT" or "REJECT"
    reason: Optional[str] = None


class FinalSummaryStatus(BaseModel):
    present: Optional[bool] = None


class AtomicClaim(BaseModel):
    claim_id: str
    repository: str
    text: str
    claim_type: ClaimType
    citations: List[str] = Field(default_factory=list)
    citation_evaluations: List[CitationEvaluation] = Field(default_factory=list)
    support_status: SupportStatus
    hallucination_categories: List[HallucinationCategory] = Field(default_factory=list)
    validator: ValidatorDecision = Field(default_factory=ValidatorDecision)
    final_summary: FinalSummaryStatus = Field(default_factory=FinalSummaryStatus)
    evidence_detail: Optional[str] = None


class CitationQualityMetrics(BaseModel):
    total_citations: int = 0
    valid_citations: int = 0
    invalid_id_citations: int = 0
    unentailed_citations: int = 0
    validity_rate: float = 0.0
    entailment_rate: float = 0.0


class RepositoryPhase3Result(BaseModel):
    repository: str
    total_claims: int = 0
    evaluable_claims: int = 0
    supported: int = 0
    unsupported: int = 0
    contradicted: int = 0
    unresolved: int = 0
    
    # Rates
    hallucination_rate: float = 0.0               # (unsupported + contradicted) / total_claims
    conditional_hallucination_rate: float = 0.0   # (unsupported + contradicted) / evaluable_claims
    unsupported_rate: float = 0.0
    contradiction_rate: float = 0.0
    
    # Content Hallucination Taxonomy (Citation issues separated)
    fabricated_paths: int = 0
    fabricated_files: int = 0
    fabricated_symbols: int = 0
    false_contradictions: int = 0
    incorrect_technologies: int = 0
    
    # Citation Quality Metrics (Reported separately)
    citation_quality: CitationQualityMetrics = Field(default_factory=CitationQualityMetrics)
    
    # Validator Leakage Metrics
    invalid_claims_before_validator: int = 0
    invalid_claims_rejected: int = 0
    invalid_claims_leaked: int = 0
    leakage_rate: float = 0.0
    
    # Validator False Rejection (Supported + Correctly Evidenced claims rejected)
    supported_claims: int = 0
    supported_correctly_evidenced_claims: int = 0
    supported_correctly_evidenced_rejected: int = 0
    false_rejection_rate: float = 0.0
    
    claims: List[AtomicClaim] = Field(default_factory=list)


class Phase3AggregateReport(BaseModel):
    phase: str = "phase3_hallucination_baseline"
    writer: Dict[str, str] = Field(default_factory=lambda: {
        "provider": "ollama",
        "model": "qwen2.5-coder:7b"
    })
    benchmark: Dict[str, int] = Field(default_factory=lambda: {"repositories": 15})
    claims: Dict[str, int] = Field(default_factory=dict)
    writer_metrics: Dict[str, float] = Field(default_factory=dict)
    hallucination_categories: Dict[str, int] = Field(default_factory=dict)
    citation_quality: Dict[str, Any] = Field(default_factory=dict)
    validator: Dict[str, Any] = Field(default_factory=dict)
    per_repository: List[RepositoryPhase3Result] = Field(default_factory=list)
