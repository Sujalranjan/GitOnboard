"""
Canonical Intelligence Domain Contracts: Repository Investigation and Evidence Verification.

Defines the ground-truth models for:
  - EvidenceStatus (CONFIRMED, INFERRED, UNRESOLVED)
  - ImplementationAssessment (EXISTING, PARTIAL, NEW, UNCERTAIN)
  - InvestigationCandidate (raw potential matches)
  - InvestigationEvidence (verified code-level evidence with source snippets)
  - InvestigationCoverage (coverage completeness indicators)
  - RepositoryInvestigationResult (complete structured investigation report)
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    UNRESOLVED = "UNRESOLVED"


class ImplementationAssessment(str, Enum):
    EXISTING = "EXISTING"
    PARTIAL = "PARTIAL"
    NEW = "NEW"
    UNCERTAIN = "UNCERTAIN"


class SourceSnippetEvidence(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    symbol_name: Optional[str] = None
    route_path: Optional[str] = None
    match_type: str = "EXACT_SYMBOL"  # EXACT_SYMBOL, ROUTE_DECORATOR, FUNCTION_BODY, CALL_SITE
    evidence_status: EvidenceStatus = EvidenceStatus.CONFIRMED
    description: str = ""


class InvestigationCandidate(BaseModel):
    source_type: str  # FactRoute, FactSymbol, FactFile, LexicalSearch, SemanticSearch
    location: str
    match_text: str
    relevance: float = 1.0
    symbol_or_route: Optional[str] = None
    is_code: bool = True  # False for README, markdown docs, comments


class InvestigationEvidence(BaseModel):
    candidate: InvestigationCandidate
    evidence_status: EvidenceStatus = EvidenceStatus.CONFIRMED
    source_file: str
    source_lines: Optional[str] = None  # e.g. "12-24"
    code_snippet: Optional[str] = None
    semantic_role: str = "IMPLEMENTATION"  # IMPLEMENTATION, EXTENSION_POINT, TEST, UTILITY, UNRELATED
    interpretation: str = ""


class InvestigationCoverage(BaseModel):
    fact_routes_searched: bool = True
    fact_symbols_searched: bool = True
    fact_files_searched: bool = True
    lexical_searched: bool = True
    source_snippets_inspected: bool = True
    semantic_searched: bool = True
    coverage_score: float = 1.0  # 0.0 - 1.0

    @property
    def is_complete(self) -> bool:
        return (
            self.fact_routes_searched
            and self.fact_symbols_searched
            and self.fact_files_searched
            and self.lexical_searched
            and self.source_snippets_inspected
        )


class RepositoryInvestigationResult(BaseModel):
    requirement: str
    assessment: ImplementationAssessment
    assessment_reason: str
    decision_rationale: str
    coverage: InvestigationCoverage = Field(default_factory=InvestigationCoverage)
    inspected_files: List[str] = Field(default_factory=list)
    relevant_symbols: List[str] = Field(default_factory=list)
    relevant_routes: List[str] = Field(default_factory=list)
    source_snippets: List[SourceSnippetEvidence] = Field(default_factory=list)
    evidence_items: List[InvestigationEvidence] = Field(default_factory=list)

    @property
    def has_confirmed_relevant_evidence(self) -> bool:
        return any(
            e.evidence_status == EvidenceStatus.CONFIRMED
            and e.semantic_role in ("IMPLEMENTATION", "EXTENSION_POINT")
            for e in self.evidence_items
        )

    @property
    def has_ambiguous_relevant_evidence(self) -> bool:
        return any(
            e.evidence_status == EvidenceStatus.UNRESOLVED
            or (e.evidence_status == EvidenceStatus.INFERRED and e.semantic_role == "IMPLEMENTATION")
            for e in self.evidence_items
        )
