"""
ContextAssembler: Orchestrates repository evidence selection over existing deterministic GitOnBoard subsystems.

Subsystems Orchestrated (Zero Rebuilding):
  - RequirementAnalyzer (backend/planning/requirements.py)
  - HybridRetriever (backend/intelligence/retrieval/retriever.py)
  - FactStore / RIM (backend/intelligence/store/fact_store.py, backend/models/fact_store.py)
  - RepositoryToolLayer (backend/repository_tools/tools.py)
  - Capability Detection (FactCapability / backend/intelligence/capabilities/)
  - Feature Tracing (backend/intelligence/feature_tracing.py)
  - ImpactAnalyzer (backend/planning/impact_analysis.py)
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session

from backend.agent.context.contracts import (
    CompletenessStatus,
    ContextAssemblyRequest,
    ContextBudget,
    ContextEvidence,
    RepositoryContext,
    RepositoryUnderstandingContract,
)
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.models.fact_store import (
    FactCapability,
    FactDatabaseObject,
    FactFile,
    FactRelationship,
    FactRoute,
    FactSymbol,
)
from backend.planning.requirements import AnalyzedRequirement, RequirementAnalyzer
from backend.repository_tools.tools import RepositoryToolLayer

logger = logging.getLogger(__name__)


def extract_domain_concepts(requirement: str) -> List[str]:
    """
    Extracts high-signal domain concepts and removes generic planning language noise.
    E.g. 'what would it take to add Google OAuth' -> ['google oauth', 'google', 'oauth', 'auth', 'login']
         'what would it take to add pagination to the users API' -> ['pagination users api', 'pagination', 'users', 'api']
         'what would it take to add dark mode' -> ['dark mode', 'dark', 'mode', 'theme', 'tailwind', 'color', 'style']
    """
    import re
    planning_noise = {
        "what", "would", "it", "take", "to", "add", "implement", "feature", "system",
        "please", "could", "should", "want", "need", "like", "about", "into", "make",
        "help", "this", "that", "with", "from", "have", "tell", "show", "give", "step",
        "steps", "plan", "estimate", "changes", "files", "file", "for", "and", "the", "a", "an",
        "require", "require?", "take?", "add?", "create", "setup", "new", "do", "we", "of", "in"
    }
    cleaned = re.sub(r"[^\w\s-]", " ", requirement)
    words = cleaned.split()
    meaningful_words = [w.lower() for w in words if w.lower() not in planning_noise and len(w) > 1]
    
    concepts: List[str] = []
    if meaningful_words:
        concepts.append(" ".join(meaningful_words))
    for w in meaningful_words:
        if w not in concepts:
            concepts.append(w)
            
    req_lower = requirement.lower()
    if "oauth" in req_lower or "google" in req_lower or "auth" in req_lower:
        for syn in ["auth", "login", "oauth", "session", "user"]:
            if syn not in concepts:
                concepts.append(syn)
    if "dark" in req_lower or "mode" in req_lower or "theme" in req_lower:
        for syn in ["theme", "dark", "tailwind", "color", "style", "provider"]:
            if syn not in concepts:
                concepts.append(syn)
    if "pagination" in req_lower or "page" in req_lower:
        for syn in ["pagination", "page", "limit", "offset", "cursor", "api"]:
            if syn not in concepts:
                concepts.append(syn)
    if "payment" in req_lower or "stripe" in req_lower or "billing" in req_lower:
        for syn in ["payment", "stripe", "billing", "checkout", "subscription"]:
            if syn not in concepts:
                concepts.append(syn)
    if "redis" in req_lower or "cache" in req_lower or "caching" in req_lower:
        for syn in ["redis", "cache", "caching", "store"]:
            if syn not in concepts:
                concepts.append(syn)
    if "user" in req_lower or "users" in req_lower:
        for syn in ["user", "users", "account", "profile"]:
            if syn not in concepts:
                concepts.append(syn)

    return concepts or [requirement]


def _extract_symbol_file_path(sym: FactSymbol) -> str:
    if sym.file and sym.file.path:
        return sym.file.path
    if sym.id:
        import re
        match = re.search(r":urn:[^:]+:(.+?)#", sym.id)
        if match:
            return match.group(1)
    if sym.file_id:
        return sym.file_id.split(":")[-1]
    return ""


class ContextAssembler:
    """
    Assembles bounded, structured, and deduplicated repository evidence for an agent requirement.
    """

    def __init__(self, llm_service: Optional[Any] = None, worktree_path: Optional[str] = None):
        self.llm_service = llm_service
        self.worktree_path = worktree_path

    def assemble(
        self,
        request: ContextAssemblyRequest,
        db: Optional[Session] = None,
    ) -> RepositoryContext:
        """
        Executes the multi-stage evidence assembly pipeline.
        """
        start_time = time.time()
        budget = request.context_budget or ContextBudget()

        evidence_items: List[ContextEvidence] = []
        unknowns: List[str] = []
        capabilities: List[Dict[str, Any]] = []
        relevant_files: List[str] = []
        relevant_symbols: List[Dict[str, Any]] = []
        relevant_routes: List[Dict[str, Any]] = []
        relevant_db_objects: List[Dict[str, Any]] = []
        relevant_dependencies: List[Dict[str, Any]] = []
        relevant_call_paths: List[Dict[str, Any]] = []
        relevant_features: List[Dict[str, Any]] = []
        architecture_constraints: List[str] = []
        impact_context: Optional[Dict[str, Any]] = None

        # ──────────────────────────────────────────────────────────────────────
        # 1. Requirement Analysis (Intent & Keyword Extraction)
        # ──────────────────────────────────────────────────────────────────────
        keywords = extract_domain_concepts(request.requirement)
        from backend.planning.requirements import AcceptanceCriterion
        analyzed_req = AnalyzedRequirement(
            title=request.requirement[:60],
            goals=[request.requirement],
            acceptance_criteria=[
                AcceptanceCriterion(id="AC-01", description=f"Implement: {request.requirement}")
            ],
            security_considerations=[],
            tests_required=[f"Test {request.requirement}"],
        )

        evidence_items.append(
            ContextEvidence(
                source_type="requirement_analysis",
                source_id="req_analysis",
                relevance=1.0,
                confidence=1.0,
                summary=f"Requirement Title: {analyzed_req.title}, extracted domain concepts: {keywords}",
                data={
                    "title": analyzed_req.title,
                    "goals": analyzed_req.goals,
                    "criteria": [
                        {"id": c.id, "text": c.description}
                        for c in analyzed_req.acceptance_criteria
                    ],
                    "keywords": keywords,
                },
            )
        )

        # ──────────────────────────────────────────────────────────────────────
        # 2. Candidate Discovery (HybridRetriever & Direct Fact Store)
        # ──────────────────────────────────────────────────────────────────────
        seen_files: Set[str] = set()
        seen_symbols: Set[str] = set()

        if db and request.analysis_id:
            try:
                retriever = HybridRetriever(db=db, analysis_id=request.analysis_id)
                for kw in keywords[:8]:
                    # Exact file match in FactFile
                    exact_files = db.query(FactFile).filter(
                        FactFile.analysis_id == request.analysis_id,
                        FactFile.path.ilike(f"%{kw}%")
                    ).limit(5).all()
                    for f in exact_files:
                        if f.path not in seen_files:
                            seen_files.add(f.path)
                            relevant_files.append(f.path)

                    # Exact symbol match in FactSymbol
                    exact_symbols = db.query(FactSymbol).filter(
                        FactSymbol.analysis_id == request.analysis_id,
                        FactSymbol.name.ilike(f"%{kw}%")
                    ).limit(5).all()
                    for s in exact_symbols:
                        f_path = _extract_symbol_file_path(s)
                        if f_path and f_path not in seen_files:
                            seen_files.add(f_path)
                            relevant_files.append(f_path)
                        if s.name not in seen_symbols:
                            seen_symbols.add(s.name)
                            relevant_symbols.append({
                                "name": s.name,
                                "file_path": f_path,
                                "kind": s.symbol_type,
                            })

                    # Hybrid lexical BM25 / vector retrieval
                    retrieved = retriever.retrieve(query=kw, top_k=5, expand_with_fact_store=True)
                    for item in retrieved:
                        f_path = item.get("file_path", "")
                        sym_name = item.get("name", "")
                        if f_path and f_path not in seen_files:
                            seen_files.add(f_path)
                            relevant_files.append(f_path)

                        if sym_name and sym_name not in seen_symbols:
                            seen_symbols.add(sym_name)
                            relevant_symbols.append(
                                {
                                    "name": sym_name,
                                    "file_path": f_path,
                                    "kind": item.get("type", "symbol"),
                                }
                            )

                        evidence_items.append(
                            ContextEvidence(
                                source_type="retrieval",
                                source_id=f"{f_path or 'match'}:{sym_name or 'match'}",
                                relevance=float(item.get("score", 0.9) or 0.9),
                                confidence=0.85,
                                summary=f"Discovered candidate '{f_path or sym_name}' (relevance: {float(item.get('score', 0.9) or 0.9):.2f})",
                                data=item,
                            )
                        )
            except Exception as err:
                logger.debug(f"HybridRetriever query error: {err}")

        # Direct repository snapshot tool discovery (only if active worktree on disk is present)
        if request.worktree_path and Path(request.worktree_path).exists():
            try:
                tool_layer = RepositoryToolLayer(
                    repo_name=request.repository_id,
                    db=db,
                    repo_root=request.worktree_path,
                )
                for kw in keywords[:5]:
                    matches = tool_layer.search_repository(query=kw, limit=5)
                    for m in matches:
                        f_path = m.get("file", m.get("path", ""))
                        if f_path and f_path not in seen_files:
                            seen_files.add(f_path)
                            relevant_files.append(f_path)
                            evidence_items.append(
                                ContextEvidence(
                                    source_type="snapshot_search",
                                    source_id=f_path,
                                    relevance=0.85,
                                    confidence=1.0,
                                    summary=f"Found match in {f_path}: {m.get('line_content', '')[:60]}",
                                    data=m,
                                )
                            )
            except Exception as err:
                logger.debug(f"RepositoryToolLayer search failed: {err}")


        # ──────────────────────────────────────────────────────────────────────
        # 3. RIM / Fact Store Relational Expansion
        # ──────────────────────────────────────────────────────────────────────
        if db:
            # Expand Symbols
            for kw in keywords[:5]:
                syms = db.query(FactSymbol).filter(FactSymbol.name.ilike(f"%{kw}%")).limit(10).all()
                for s in syms:
                    if s.name not in seen_symbols:
                        seen_symbols.add(s.name)
                        relevant_symbols.append(
                            {
                                "name": s.name,
                                "kind": s.symbol_type,
                                "file_path": s.file_id.split(":")[-1] if s.file_id else "",
                                "signature": (s.metadata_json or {}).get("signature", "") if s.metadata_json else "",
                            }
                        )

                        if s.file_id:
                            f_path = s.file_id.split(":")[-1]
                            if f_path and f_path not in seen_files:
                                seen_files.add(f_path)
                                relevant_files.append(f_path)

            # Expand Routes
            for kw in keywords[:5]:
                routes = db.query(FactRoute).filter(FactRoute.path.ilike(f"%{kw}%")).limit(5).all()
                for r in routes:
                    relevant_routes.append(
                        {
                            "id": r.id,
                            "method": r.method,
                            "path": r.path,
                            "handler_symbol_id": r.handler_symbol_id,
                        }
                    )
                    evidence_items.append(
                        ContextEvidence(
                            source_type="rim_route",
                            source_id=r.id,
                            relevance=0.9,
                            confidence=1.0,
                            summary=f"Route {r.method} {r.path} mapped to handler {r.handler_symbol_id}",
                            data={"method": r.method, "path": r.path},
                        )
                    )

            # Expand Database Objects
            for kw in keywords[:5]:
                db_objs = db.query(FactDatabaseObject).filter(FactDatabaseObject.name.ilike(f"%{kw}%")).limit(5).all()
                for d in db_objs:
                    relevant_db_objects.append(
                        {
                            "id": d.id,
                            "name": d.name,
                            "object_type": d.object_type,
                            "symbol_id": d.symbol_id,
                        }
                    )

        # ──────────────────────────────────────────────────────────────────────
        # 4. Capability Detection & First-Class Unknowns
        # ──────────────────────────────────────────────────────────────────────
        if db:
            matched_caps = []
            for kw in keywords:
                caps = db.query(FactCapability).filter(FactCapability.name.ilike(f"%{kw}%")).limit(5).all()
                for c in caps:
                    matched_caps.append(c)
                    capabilities.append(
                        {
                            "id": c.id,
                            "name": c.name,
                            "type": c.capability_type,
                            "status": c.status,
                            "evidence_summary": c.evidence_summary,
                        }
                    )
                    evidence_items.append(
                        ContextEvidence(
                            source_type="capability",
                            source_id=c.id,
                            relevance=0.95,
                            confidence=1.0,
                            summary=f"Matched capability '{c.name}' (type: {c.capability_type})",
                            data={"name": c.name, "status": c.status},
                        )
                    )

            # Check if domain requirement had no matching capability
            if not matched_caps:
                unknowns.append(
                    f"No existing capability found for requirement keywords: {', '.join(keywords[:3])}. "
                    "This appears to require a new capability rather than extending an existing one."
                )

        # ──────────────────────────────────────────────────────────────────────
        # 5. Dependency Inspection & Repository Tools
        # ──────────────────────────────────────────────────────────────────────
        try:
            tool_layer = RepositoryToolLayer(
                repo_name=request.repository_id,
                db=db,
                repo_root=request.worktree_path,
            )
            deps = tool_layer.get_dependencies()
            if deps:
                for d in deps.get("dependencies", [])[:budget.max_dependencies]:
                    relevant_dependencies.append(d)

            # Bounded source excerpts for top relevant files (max 2 files, 30 lines)
            for f_path in relevant_files[:2]:
                try:
                    f_read = tool_layer.read_file(path=f_path, start_line=1, end_line=30)
                    if f_read and "content" in f_read:
                        evidence_items.append(
                            ContextEvidence(
                                source_type="source_excerpt",
                                source_id=f_path,
                                relevance=0.8,
                                confidence=1.0,
                                summary=f"Source excerpt from {f_path} (lines 1-30)",
                                data={"file_path": f_path, "content": f_read["content"]},
                            )
                        )
                except Exception as err:
                    logger.debug(f"Source excerpt reading failed for {f_path}: {err}")
        except Exception as err:
            logger.debug(f"RepositoryToolLayer inspection encountered error: {err}")

        # ──────────────────────────────────────────────────────────────────────
        # 6. Feature Tracing (DeterministicTracer)
        # ──────────────────────────────────────────────────────────────────────
        if db and request.analysis_id and (relevant_routes or relevant_symbols):
            try:
                from backend.intelligence.feature_tracing import DeterministicTracer
                from backend.intelligence.store.fact_store import load_rim_from_fact_store

                seed = relevant_routes[0]["id"] if relevant_routes else relevant_symbols[0]["name"]
                model = load_rim_from_fact_store(db, analysis_id=request.analysis_id)
                tracer = DeterministicTracer(model)
                trace_res = tracer.trace_feature(seed)
                if trace_res and trace_res.nodes:
                    relevant_features.append(trace_res.to_dict())
                    evidence_items.append(
                        ContextEvidence(
                            source_type="feature_trace",
                            source_id=str(seed),
                            relevance=0.9,
                            confidence=1.0,
                            summary=f"Deterministic execution trace visited {len(trace_res.nodes)} nodes",
                            data=trace_res.to_dict(),
                        )
                    )
            except Exception as err:
                logger.debug(f"Feature tracing skipped or encountered error: {err}")

        # ──────────────────────────────────────────────────────────────────────
        # 7. Impact Analysis (ImpactAnalyzer)
        # ──────────────────────────────────────────────────────────────────────
        if db and request.analysis_id:
            try:
                import asyncio
                import concurrent.futures
                from backend.planning.impact_analysis import ImpactAnalyzer
                analyzer = ImpactAnalyzer(db=db, analysis_id=request.analysis_id)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        impact_res = pool.submit(asyncio.run, analyzer.analyze(keywords=keywords)).result()
                else:
                    impact_res = asyncio.run(analyzer.analyze(keywords=keywords))

                if impact_res:
                    impact_context = {
                        "affected_files": impact_res.affected_files,
                        "affected_symbols": impact_res.affected_symbols,
                        "status": impact_res.planning_status.value if hasattr(impact_res.planning_status, "value") else str(impact_res.planning_status),
                    }
                    evidence_items.append(
                        ContextEvidence(
                            source_type="impact",
                            source_id="impact_analysis",
                            relevance=0.85,
                            confidence=0.9,
                            summary=f"Impact analysis: {len(impact_res.affected_files)} affected files",
                            data=impact_context,
                        )
                    )
            except Exception as err:
                logger.debug(f"ImpactAnalyzer skipped or encountered error: {err}")

        # ──────────────────────────────────────────────────────────────────────
        # 8. Deduplication & Budget Enforcement
        # ──────────────────────────────────────────────────────────────────────
        # Deduplicate files & symbols while preserving order
        dedup_files = list(dict.fromkeys(relevant_files))[:budget.max_files]
        dedup_symbols = list({s["name"]: s for s in relevant_symbols}.values())[:budget.max_symbols]
        dedup_routes = list({r.get("id", r.get("path")): r for r in relevant_routes}.values())[:budget.max_routes]
        dedup_db = list({d.get("id", d.get("name")): d for d in relevant_db_objects}.values())[:budget.max_db_objects]
        dedup_deps = relevant_dependencies[:budget.max_dependencies]

        # ──────────────────────────────────────────────────────────────────────
        # 9. Understanding Contract Evaluation (Tech-Stack Aware)
        # ──────────────────────────────────────────────────────────────────────
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

        contract = RepositoryUnderstandingContract(
            required_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
            satisfied_categories=satisfied_cats,
            missing_categories=missing_cats,
            unknowns=unknowns,
            completeness=completeness,
            explanation=explanation,
        )

        duration_ms = (time.time() - start_time) * 1000

        return RepositoryContext(
            version="v1",
            repository_id=request.repository_id,
            requirement=request.requirement,
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
                "duration_ms": round(duration_ms, 2),
                "evidence_count": len(evidence_items),
                "budget_applied": budget.model_dump(),
            },
        )
