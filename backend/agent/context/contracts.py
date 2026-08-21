"""
Repository Context Contracts: Typed models for assembled repository evidence and understanding contracts.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CompletenessStatus(str, Enum):
    """
    Evaluation of evidence sufficiency for the defined contract.
    Note: COMPLETE indicates sufficient evidence satisfies the contract criteria,
    not that the entire repository is completely understood.
    """
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class ContextEvidence(BaseModel):
    """
    A single deterministic evidence item gathered from a specific GitOnBoard subsystem.
    Preserves provenance, relevance, and structured data.
    """
    source_type: str = Field(..., description="Source subsystem (e.g. 'retrieval', 'rim_symbol', 'rim_route', 'capability', 'feature_trace', 'impact', 'source_excerpt')")
    source_id: str = Field(..., description="Identifier of source entity (file path, symbol name, route ID)")
    relevance: float = Field(default=1.0, description="Relevance score in range [0.0, 1.0]")
    confidence: float = Field(default=1.0, description="Subsystem confidence score in range [0.0, 1.0]")
    summary: str = Field(..., description="Human/LLM-readable summary of the evidence item")
    data: Dict[str, Any] = Field(default_factory=dict, description="Structured raw data from subsystem")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional provenance metadata")


class ContextBudget(BaseModel):
    """
    Configurable limits for assembled repository evidence to ensure token economy.
    """
    max_files: int = Field(default=15, description="Maximum relevant files to include")
    max_symbols: int = Field(default=30, description="Maximum relevant symbols to include")
    max_routes: int = Field(default=15, description="Maximum relevant routes to include")
    max_db_objects: int = Field(default=15, description="Maximum relevant database objects")
    max_dependencies: int = Field(default=20, description="Maximum dependency manifests/packages")
    max_call_paths: int = Field(default=10, description="Maximum call paths/edges")
    max_source_excerpts: int = Field(default=10, description="Maximum bounded source excerpts")
    max_total_evidence_size_kb: int = Field(default=256, description="Max total evidence payload size in KB")


class ContextAssemblyRequest(BaseModel):
    """
    Request parameters for assembling repository context for a requirement.
    """
    repository_id: str
    requirement: str
    context_budget: Optional[ContextBudget] = None
    analysis_id: Optional[int] = None
    worktree_path: Optional[str] = None
    task_context: Optional[Dict[str, Any]] = None
    previous_context: Optional[Dict[str, Any]] = None


class RepositoryUnderstandingContract(BaseModel):
    """
    Contract defining minimum evidence required for understanding before planning.
    """
    required_categories: List[str] = Field(
        default_factory=lambda: ["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
        description="Required evidence dimensions",
    )
    satisfied_categories: List[str] = Field(default_factory=list, description="Categories with sufficient evidence")
    missing_categories: List[str] = Field(default_factory=list, description="Categories lacking sufficient evidence")
    unknowns: List[str] = Field(default_factory=list, description="Explicitly registered missing repository facts")
    completeness: CompletenessStatus = Field(default=CompletenessStatus.INSUFFICIENT, description="Computed sufficiency")
    explanation: str = Field(default="", description="Detailed rationale for contract verdict")


class RepositoryContext(BaseModel):
    """
    Complete assembled repository evidence package for a given requirement.
    Structured, typed, deduplicated, and budgeted.
    """
    version: str = Field(default="v1", description="Context schema version")
    repository_id: str
    requirement: str
    capabilities: List[Dict[str, Any]] = Field(default_factory=list, description="Existing matching capabilities")
    relevant_files: List[str] = Field(default_factory=list, description="Selected file paths")
    relevant_symbols: List[Dict[str, Any]] = Field(default_factory=list, description="Selected symbol definitions")
    relevant_routes: List[Dict[str, Any]] = Field(default_factory=list, description="Selected HTTP routes")
    relevant_db_objects: List[Dict[str, Any]] = Field(default_factory=list, description="Selected DB entities/tables")
    relevant_dependencies: List[Dict[str, Any]] = Field(default_factory=list, description="Relevant external dependencies")
    relevant_call_paths: List[Dict[str, Any]] = Field(default_factory=list, description="Call path sequences")
    relevant_features: List[Dict[str, Any]] = Field(default_factory=list, description="Features/traces matched")
    architecture_constraints: List[str] = Field(default_factory=list, description="Identified architectural patterns/rules")
    impact_context: Optional[Dict[str, Any]] = Field(default=None, description="ImpactAnalyzer blast radius report")
    evidence: List[ContextEvidence] = Field(default_factory=list, description="Chronological evidence items")
    unknowns: List[str] = Field(default_factory=list, description="Explicit unknowns where evidence was absent")
    contract: RepositoryUnderstandingContract = Field(default_factory=RepositoryUnderstandingContract)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Assembly metadata (duration, query counts)")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def to_bounded_summary(self) -> Dict[str, Any]:
        """
        Returns a bounded, versioned summary for safe persistence in AgentRun.metadata_json
        without bloating database storage.
        """
        return {
            "version": self.version,
            "repository_id": self.repository_id,
            "requirement_length": len(self.requirement),
            "completeness": self.contract.completeness.value,
            "counts": {
                "capabilities": len(self.capabilities),
                "relevant_files": len(self.relevant_files),
                "relevant_symbols": len(self.relevant_symbols),
                "relevant_routes": len(self.relevant_routes),
                "relevant_db_objects": len(self.relevant_db_objects),
                "relevant_dependencies": len(self.relevant_dependencies),
                "evidence_items": len(self.evidence),
                "unknowns": len(self.unknowns),
            },
            "unknowns": self.unknowns[:10],
            "satisfied_categories": self.contract.satisfied_categories,
            "missing_categories": self.contract.missing_categories,
            "duration_ms": self.metadata.get("duration_ms", 0.0),
        }
