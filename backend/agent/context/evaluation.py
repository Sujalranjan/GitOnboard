"""Evaluation and contract verification helpers for ContextAssembler."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.agent.context.contracts import (
    CompletenessStatus,
    ContextAssemblyRequest,
    ContextBudget,
    ContextEvidence,
    RepositoryContext,
    RepositoryUnderstandingContract,
)
from backend.models.fact_store import FactFile


def evaluate_understanding_contract(
    request: ContextAssemblyRequest,
    capabilities: List[Dict[str, Any]],
    unknowns: List[str],
    dedup_routes: List[Dict[str, Any]],
    dedup_files: List[str],
    dedup_symbols: List[Dict[str, Any]],
    dedup_deps: List[Dict[str, Any]],
    dedup_db: List[Dict[str, Any]],
    db: Optional[Session] = None,
) -> RepositoryUnderstandingContract:
    """Evaluates the repository understanding contract based on collected categories."""
    satisfied_cats: List[str] = []
    missing_cats: List[str] = []

    is_frontend = False
    is_backend = False
    repo_files = db.query(FactFile).filter(FactFile.analysis_id == request.analysis_id).all() if db and request.analysis_id else []
    file_paths = [f.path.lower() for f in repo_files]
    if any("package.json" in p or "next.config" in p or p.endswith(".tsx") or p.endswith(".jsx") or p.endswith(".ts") for p in file_paths):
        is_frontend = True
    if any("requirements.txt" in p or "pyproject.toml" in p or p.endswith(".py") for p in file_paths):
        is_backend = True

    if capabilities or unknowns:
        satisfied_cats.append("capabilities")
    else:
        missing_cats.append("capabilities")

    if dedup_routes or dedup_files:
        satisfied_cats.append("entrypoints_or_routes")
    else:
        missing_cats.append("entrypoints_or_routes")

    if dedup_symbols or dedup_files:
        satisfied_cats.append("symbols_or_files")
    else:
        missing_cats.append("symbols_or_files")

    if dedup_deps or dedup_db or (request.worktree_path and Path(request.worktree_path).exists()) or (is_frontend and any("package.json" in p for p in file_paths)):
        satisfied_cats.append("dependencies_or_models")
    elif is_frontend and not is_backend:
        satisfied_cats.append("dependencies_or_models")
    else:
        missing_cats.append("dependencies_or_models")

    # Evaluate completeness for the defined contract
    if len(satisfied_cats) == 4:
        completeness = CompletenessStatus.COMPLETE
        explanation = "Sufficient evidence collected to satisfy all defined contract categories."
    elif len(satisfied_cats) >= 2:
        completeness = CompletenessStatus.PARTIAL
        explanation = f"Partial evidence gathered; missing: {', '.join(missing_cats)}."
    else:
        completeness = CompletenessStatus.INSUFFICIENT
        explanation = f"Insufficient evidence found for requirement; missing: {', '.join(missing_cats)}."

    return RepositoryUnderstandingContract(
        required_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
        satisfied_categories=satisfied_cats,
        missing_categories=missing_cats,
        unknowns=unknowns,
        completeness=completeness,
        explanation=explanation,
    )


def build_repository_context(
    request: ContextAssemblyRequest,
    budget: ContextBudget,
    capabilities: List[Dict[str, Any]],
    dedup_files: List[str],
    dedup_symbols: List[Dict[str, Any]],
    dedup_routes: List[Dict[str, Any]],
    dedup_db: List[Dict[str, Any]],
    dedup_deps: List[Dict[str, Any]],
    relevant_call_paths: List[Dict[str, Any]],
    relevant_features: List[Dict[str, Any]],
    architecture_constraints: List[str],
    impact_context: Optional[Dict[str, Any]],
    evidence_items: List[ContextEvidence],
    unknowns: List[str],
    contract: RepositoryUnderstandingContract,
    start_time: float,
) -> RepositoryContext:
    """Builds and packages the final RepositoryContext object."""
    import time
    duration_ms = (time.time() - start_time) * 1000

    return RepositoryContext(
        version="v1",
        repository_id=request.repository_id,
        requirement=request.requirement,
        analysis_id=request.analysis_id,
        capabilities=capabilities,
        relevant_files=dedup_files,
        relevant_symbols=dedup_symbols,
        relevant_routes=dedup_routes,
        relevant_db_objects=dedup_db,
        relevant_dependencies=dedup_deps,
        relevant_call_paths=relevant_call_paths,
        relevant_features=relevant_features,
        architecture_constraints=architecture_constraints,
        impact_context=impact_context,
        evidence=evidence_items,
        unknowns=unknowns,
        contract=contract,
        metadata={
            "analysis_id": request.analysis_id,
            "duration_ms": round(duration_ms, 2),
            "evidence_count": len(evidence_items),
            "budget_applied": budget.model_dump(),
        },
    )
