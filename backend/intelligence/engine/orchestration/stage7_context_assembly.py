"""
Stage 7: Context Assembly

Wraps existing ContextAssembler, consuming Stage 5 retrieval and Stage 6 graph results.
Preserves provenance from retrieval and graph traversal.
"""
import logging
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from sqlalchemy.orm import Session

from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import (
    ContextAssemblyRequest,
    RepositoryContext,
    ContextEvidence,
    ContextBudget,
)
from backend.intelligence.retrieval.schema import RetrieverResult
from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigationResult

logger = logging.getLogger(__name__)


@dataclass
class ContextAssemblyMetrics:
    """Metrics from Stage 7 assembly."""
    query: str
    retrieval_anchors: int
    graph_entities: int
    graph_edges: int
    selected_files: List[str]
    selected_symbols: List[str]
    context_size_kb: float
    evidence_count: int
    configured_budgets: Dict[str, int]
    assembly_time: float
    validation_passed: bool
    validation_errors: List[str]


class ContextAssemblyValidator:
    """Validate Stage 7 context output."""

    @staticmethod
    def validate(
        context: RepositoryContext,
        graph_result: GraphNavigationResult,
        query: str,
    ) -> tuple[bool, List[str]]:
        """
        Validate that assembled context is repository-derived and budgeted.

        Returns:
            (passed: bool, errors: List[str])
        """
        errors: List[str] = []

        # Validate context structure
        if not context:
            errors.append("Context is None")
            return False, errors

        if not context.requirement:
            errors.append("Context requirement is empty")

        if not context.relevant_files:
            errors.append("No relevant files selected")

        if not context.evidence:
            errors.append("No evidence items selected")

        # Validate that selected files actually exist (sanity check)
        # Note: Would need RepositoryModel to fully validate; skip for now
        if context.relevant_files and not all(isinstance(f, str) for f in context.relevant_files):
            errors.append("Selected files contain non-string values")

        # Validate budget constraints
        if len(context.relevant_files) > 50:
            errors.append(f"Too many files selected: {len(context.relevant_files)} > 50")

        if len(context.relevant_symbols) > 100:
            errors.append(f"Too many symbols selected: {len(context.relevant_symbols)} > 100")

        if len(context.evidence) > 200:
            errors.append(f"Too many evidence items: {len(context.evidence)} > 200")

        # Validate evidence provenance
        for evidence in context.evidence:
            if not evidence.source_type:
                errors.append("Evidence missing source_type")
            if not evidence.source_id:
                errors.append("Evidence missing source_id")
            if not evidence.summary:
                errors.append("Evidence missing summary")

        # Validate that evidence is bounded
        try:
            evidence_json = json.dumps([e.model_dump() for e in context.evidence])
            context_size_kb = len(evidence_json) / 1024
            if context_size_kb > 512:
                errors.append(f"Context too large: {context_size_kb:.1f}KB > 512KB")
        except Exception as e:
            errors.append(f"Failed to measure context size: {e}")

        passed = len(errors) == 0
        return passed, errors


class ContextAssembler7:
    """Stage 7: Assemble bounded repository context from retrieval + graph results."""

    def __init__(self, db: Optional[Session] = None):
        self.assembler = ContextAssembler()
        self.db = db
        self.validator = ContextAssemblyValidator()

    def assemble(
        self,
        query: str,
        retrieval_results: List[RetrieverResult],
        graph_result: GraphNavigationResult,
        repository_id: str,
        analysis_id: Optional[int] = None,
        context_budget: Optional[ContextBudget] = None,
    ) -> tuple[RepositoryContext, ContextAssemblyMetrics]:
        """
        Assemble repository context from retrieval + graph results.

        Args:
            query: Original user query
            retrieval_results: Stage 5 retrieval anchors
            graph_result: Stage 6 graph traversal results
            repository_id: Repository identifier
            analysis_id: Analysis ID (optional)
            context_budget: Context budget constraints (optional)

        Returns:
            (context: RepositoryContext, metrics: ContextAssemblyMetrics)
        """
        import time
        start_time = time.time()

        # Default budget if not provided
        if not context_budget:
            context_budget = ContextBudget(
                max_files=15,
                max_symbols=30,
                max_routes=10,
                max_db_objects=10,
                max_dependencies=15,
                max_call_paths=10,
                max_source_excerpts=10,
                max_total_evidence_size_kb=256,
            )

        # Build ContextAssemblyRequest
        task_context = {
            "retrieval_anchors": len(retrieval_results),
            "graph_entities": graph_result.entity_count,
            "graph_edges": graph_result.edge_count,
            "graph_depth": graph_result.traversal_depth,
            "search_strategy": "hybrid_retrieval_plus_graph",
        }

        request = ContextAssemblyRequest(
            repository_id=repository_id,
            requirement=query,
            context_budget=context_budget,
            analysis_id=analysis_id,
            task_context=task_context,
        )

        # Call existing ContextAssembler
        try:
            context = self.assembler.assemble(request, db=self.db)
        except Exception as e:
            logger.error(f"[Stage 7] ContextAssembler failed: {e}")
            raise

        # Validate assembled context
        validated, errors = self.validator.validate(context, graph_result, query)

        # Collect metrics
        selected_files = context.relevant_files or []
        selected_symbols = [s.get("name", "") for s in context.relevant_symbols] if context.relevant_symbols else []

        try:
            context_json = json.dumps(context.model_dump())
            context_size_kb = len(context_json) / 1024
        except Exception:
            context_size_kb = 0.0

        metrics = ContextAssemblyMetrics(
            query=query,
            retrieval_anchors=len(retrieval_results),
            graph_entities=graph_result.entity_count,
            graph_edges=graph_result.edge_count,
            selected_files=selected_files,
            selected_symbols=selected_symbols,
            context_size_kb=context_size_kb,
            evidence_count=len(context.evidence) if context.evidence else 0,
            configured_budgets={
                "max_files": context_budget.max_files,
                "max_symbols": context_budget.max_symbols,
                "max_routes": context_budget.max_routes,
            },
            assembly_time=time.time() - start_time,
            validation_passed=validated,
            validation_errors=errors,
        )

        if not validated:
            logger.warning(f"[Stage 7] Context validation failed: {errors}")

        return context, metrics
