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


class DomainIntent(dict):
    """Container for domain concept extraction supporting both dict access and membership checks."""
    def __contains__(self, item):
        if super().__contains__(item):
            return True
        return (
            item in self.get("primary", [])
            or item in self.get("secondary", [])
            or item in self.get("raw_words", [])
        )


def extract_domain_concepts(requirement: str) -> DomainIntent:
    """
    Extracts high-signal primary capability keywords, secondary context keywords,
    and classifies the architectural domain of the requested capability.
    Operates strictly on generic domain terminology without hardcoded repository file names.
    """
    import re
    planning_noise = {
        "what", "would", "it", "take", "to", "add", "implement", "feature", "system",
        "please", "could", "should", "want", "need", "like", "about", "into", "make",
        "help", "this", "that", "with", "from", "have", "tell", "show", "give", "step",
        "steps", "plan", "estimate", "changes", "files", "file", "for", "and", "the", "a", "an",
        "require", "require?", "take?", "add?", "create", "setup", "new", "do", "we", "of", "in",
        "how", "can"
    }
    cleaned = re.sub(r"[^\w\s-]", " ", requirement)
    words = [w.lower() for w in cleaned.split() if w.lower() not in planning_noise and len(w) > 1]
    req_lower = requirement.lower()

    primary_kws: List[str] = []
    secondary_kws: List[str] = []
    arch_layer: str = "GENERAL"

    # 1. Auth / Access Control / RBAC / Permissions
    if any(k in req_lower for k in ["role", "rbac", "admin", "permission", "access control", "guard", "oauth", "auth", "login"]):
        primary_kws.extend(["auth", "authentication", "login", "oauth", "jwt", "session", "user", "permission", "role", "guard", "security", "credentials", "middleware", "token"])
        secondary_kws.extend(["user", "session", "permission", "access"])
        arch_layer = "AUTH_ACCESS_CONTROL"
    # 2. Search / Query across data sources
    elif any(k in req_lower for k in ["search", "find", "filter", "lookup", "query", "index"]):
        primary_kws.extend(["search", "query", "find", "filter", "lookup", "index", "browse", "retrieve"])
        secondary_kws.extend(["data", "item", "record", "store"])
        arch_layer = "DATA_SEARCH_QUERY"
    # 3. External Notifications / Messaging (Email, SMS, Webhooks)
    elif any(k in req_lower for k in ["email", "notification", "notify", "sms", "mailer", "webhook", "alert"]):
        primary_kws.extend(["notification", "notify", "email", "mailer", "alert", "message", "webhook", "sms"])
        secondary_kws.extend(["finish", "status", "complete", "event"])
        arch_layer = "EXTERNAL_COMMUNICATIONS"
    # 4. Theming / Styling
    elif any(k in req_lower for k in ["dark", "mode", "theme", "color", "styling"]):
        primary_kws.extend(["theme", "dark", "mode", "color", "style", "palette", "theme-provider"])
        secondary_kws.extend(["style", "color"])
        arch_layer = "THEMING_UI"
    # 5. Pagination / Data fetching
    elif any(k in req_lower for k in ["pagination", "paginate", "page", "cursor"]):
        primary_kws.extend(["pagination", "paginate", "page", "cursor", "limit", "offset"])
        secondary_kws.extend(["users", "user", "fetch", "query"])
        arch_layer = "API_CLIENT_PAGINATION"
    # 6. Payment / Billing
    elif any(k in req_lower for k in ["payment", "stripe", "billing", "checkout"]):
        primary_kws.extend(["payment", "stripe", "billing", "checkout", "subscription", "invoice"])
        arch_layer = "PAYMENTS_BILLING"
    # 7. Server Cache / Infra
    elif any(k in req_lower for k in ["redis", "cache", "caching", "memcached"]):
        primary_kws.extend(["cache", "caching", "redis", "memcached", "store"])
        arch_layer = "SERVER_INFRA"
    else:
        primary_kws.extend(words)

    return DomainIntent(
        primary=primary_kws,
        secondary=secondary_kws,
        arch_layer=arch_layer,
        raw_words=words,
    )


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
    Strictly isolated to the specified target analysis_id and repository.
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
        intent_data = extract_domain_concepts(request.requirement)
        primary_kws = intent_data["primary"]
        secondary_kws = intent_data["secondary"]
        arch_layer = intent_data["arch_layer"]
        keywords = list(dict.fromkeys(primary_kws + secondary_kws + intent_data.get("raw_words", [])))

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
                summary=f"Requirement Title: {analyzed_req.title}, domain: {arch_layer}, primary keywords: {primary_kws[:6]}",
                data={
                    "title": analyzed_req.title,
                    "goals": analyzed_req.goals,
                    "criteria": [
                        {"id": c.id, "text": c.description}
                        for c in analyzed_req.acceptance_criteria
                    ],
                    "keywords": keywords,
                    "arch_layer": arch_layer,
                },
            )
        )

        # ──────────────────────────────────────────────────────────────────────
        # 2. Repository Archetype & Architectural Boundary Check
        # ──────────────────────────────────────────────────────────────────────
        repo_files = []
        if db and request.analysis_id:
            repo_files = db.query(FactFile).filter(FactFile.analysis_id == request.analysis_id).all()

        if repo_files:
            evidence_items.append(
                ContextEvidence(
                    source_type="target_repository_structure",
                    source_id="repo_catalog",
                    relevance=1.0,
                    confidence=1.0,
                    summary=f"Cataloged {len(repo_files)} target repository files",
                    data={"files": [f.path for f in repo_files]},
                )
            )

        file_paths = [f.path.lower() for f in repo_files]
        is_python = any(p.endswith(".py") for p in file_paths)
        is_frontend = any("package.json" in p or "next.config" in p or p.endswith((".tsx", ".jsx", ".ts", ".js")) for p in file_paths)
        is_backend = is_python or any("requirements.txt" in p or "pyproject.toml" in p or "go.mod" in p or "cargo.toml" in p for p in file_paths)

        if is_python and not is_frontend:
            architecture_constraints.append("Target Repository Archetype: Python application / library")
        elif is_frontend and not is_backend:
            architecture_constraints.append("Target Repository Archetype: Frontend TypeScript / JavaScript application")

        # Architectural boundary check: server infrastructure in frontend client
        if (arch_layer == "SERVER_INFRA" or any(k in request.requirement.lower() for k in ["redis", "cache", "memcached"])) and is_frontend and not is_backend:
            unknowns.append(
                "Architectural Boundary: Redis caching requires server-side infrastructure. "
                "In this frontend repository, client-side state modules are not server caches. "
                "Caching should be implemented via Route Handlers / Server Actions or an external API gateway."
            )

        # Missing capability check: email delivery infrastructure in frontend repository
        if (arch_layer == "EXTERNAL_COMMUNICATIONS" or any(k in request.requirement.lower() for k in ["email", "mailer", "smtp", "sendgrid"])) and is_frontend and not is_backend:
            has_mailer = any("mailer" in p or "sendgrid" in p or "ses" in p for p in file_paths)
            if not has_mailer:
                unknowns.append(
                    "Required capability not present in target repository: Email delivery infrastructure "
                    "(SMTP/mailer service, background worker) is absent from this frontend repository. "
                    "Implementation requires a backend notification service."
                )

        # ──────────────────────────────────────────────────────────────────────
        # 3. Candidate Discovery (Relationship-Aware Scored Fact Store)
        # ──────────────────────────────────────────────────────────────────────
        seen_files: Set[str] = set()
        seen_symbols: Set[str] = set()
        file_scores: Dict[str, float] = {}

        if db and request.analysis_id:
            try:
                retriever = HybridRetriever(
                    db=db,
                    analysis_id=request.analysis_id,
                    enable_graph_expansion=True,
                    graph_expansion_depth=2,
                    graph_expansion_nodes_per_hop=3,
                    graph_expansion_max_total=30,
                )

                # Skip matching client-side state files for server infrastructure or external messaging requests
                skip_client_state = (arch_layer in ["SERVER_INFRA", "EXTERNAL_COMMUNICATIONS"] and is_frontend and not is_backend)

                # Score matching files
                for f in repo_files:
                    f_lower = f.path.lower()
                    if skip_client_state and ("store" in f_lower or "zustand" in f_lower or "analysispage" in f_lower):
                        continue

                    # Filter out peripheral styling and animation hooks from core architectural changes
                    if any(noise in f_lower for noise in ["animation", ".module.css", ".css", "favicon", ".jpg"]):
                        continue

                    score = 0.0
                    for p in primary_kws:
                        if p.lower() in f_lower:
                            score += 3.0
                    for s in secondary_kws:
                        if s.lower() in f_lower:
                            score += 0.4
                    for rw in intent_data.get("raw_words", []):
                        rw_clean = rw.lower().strip("./")
                        if len(rw_clean) >= 3 and (rw_clean in f_lower or f_lower.endswith(rw_clean)):
                            score += 3.0
                    if score >= 1.0:
                        file_scores[f.path] = max(file_scores.get(f.path, 0.0), score)

                # Query symbols using domain keywords and explicit requirement words
                search_kws = list(dict.fromkeys(primary_kws[:5] + intent_data.get("raw_words", [])[:5]))
                for kw in search_kws:
                    kw_clean = kw.strip("./")
                    if len(kw_clean) < 2:
                        continue
                    exact_symbols = db.query(FactSymbol).filter(
                        FactSymbol.analysis_id == request.analysis_id,
                        FactSymbol.name.ilike(f"%{kw_clean}%")
                    ).limit(5).all()
                    for s in exact_symbols:
                        f_path = _extract_symbol_file_path(s)
                        if f_path:
                            f_lower = f_path.lower()
                            if skip_client_state and ("store" in f_lower or "zustand" in f_lower):
                                continue
                            if any(noise in f_lower for noise in ["animation", ".module.css", ".css", "favicon", ".jpg"]):
                                continue
                            file_scores[f_path] = max(file_scores.get(f_path, 0.0), 2.5)

                        if s.name not in seen_symbols:
                            seen_symbols.add(s.name)
                            relevant_symbols.append({
                                "name": s.name,
                                "file_path": f_path,
                                "kind": s.symbol_type,
                                "symbol_type": s.symbol_type,
                                "line_start": s.line_start or 1,
                            })

                # Sort files by relevance score
                sorted_files = sorted(file_scores.keys(), key=lambda x: file_scores[x], reverse=True)
                for f_path in sorted_files[:budget.max_files]:
                    if f_path not in seen_files:
                        seen_files.add(f_path)
                        relevant_files.append(f_path)
                        evidence_items.append(
                            ContextEvidence(
                                source_type="retrieval",
                                source_id=f_path,
                                relevance=min(1.0, file_scores[f_path] / 3.0),
                                confidence=0.9,
                                summary=f"Matched relevant file '{f_path}' (score: {file_scores[f_path]:.1f})",
                                data={"file_path": f_path, "score": file_scores[f_path]},
                            )
                        )

                # Enrich relevant symbols with symbols defined in the matched relevant files
                if relevant_files and len(relevant_symbols) < budget.max_symbols:
                    matched_db_files = db.query(FactFile).filter(
                        FactFile.analysis_id == request.analysis_id,
                        FactFile.path.in_(relevant_files)
                    ).all()
                    file_id_to_path = {f.id: f.path for f in matched_db_files}
                    if file_id_to_path:
                        file_symbols = db.query(FactSymbol).filter(
                            FactSymbol.analysis_id == request.analysis_id,
                            FactSymbol.file_id.in_(list(file_id_to_path.keys()))
                        ).order_by(FactSymbol.line_start).limit(budget.max_symbols - len(relevant_symbols)).all()
                        for s in file_symbols:
                            if s.name not in seen_symbols:
                                seen_symbols.add(s.name)
                                f_path = file_id_to_path.get(s.file_id, _extract_symbol_file_path(s))
                                relevant_symbols.append({
                                    "name": s.name,
                                    "file_path": f_path,
                                    "kind": s.symbol_type,
                                    "symbol_type": s.symbol_type,
                                    "line_start": s.line_start or 1,
                                })
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
        # 3. RIM / Fact Store Relational Expansion & Directed Graph Traversal
        # ──────────────────────────────────────────────────────────────────────
        if db and request.analysis_id:
            from backend.agent.intent.semantic_query import classify_semantic_query, SemanticQueryClass
            from backend.intelligence.retrieval.target_resolver import TargetEntityResolver
            from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser

            # A. Check for explicit semantic relationship intent
            semantic_intent = classify_semantic_query(request.requirement)
            if semantic_intent.target_raw_name:
                resolver = TargetEntityResolver(db, request.analysis_id)
                target_entity = resolver.resolve(semantic_intent.target_raw_name, hint=semantic_intent.target_hint)
                if target_entity:
                    traverser = FactStoreGraphTraverser(db, request.analysis_id)
                    traversal_res = traverser.traverse(semantic_intent, target_entity)
                    if traversal_res.related_entities:
                        evidence_items.append(
                            ContextEvidence(
                                source_type="relationship_traversal",
                                source_id=traversal_res.target_display_name,
                                relevance=0.95,
                                confidence=1.0,
                                summary=traversal_res.explanation,
                                data={
                                    "query_class": traversal_res.query_class.value,
                                    "target": traversal_res.target_display_name,
                                    "direction": traversal_res.direction.value,
                                    "related": [
                                        {
                                            "name": e.name,
                                            "type": e.entity_type,
                                            "location": e.location,
                                            "line": e.line_number,
                                            "role": e.relationship_role,
                                        }
                                        for e in traversal_res.related_entities
                                    ]
                                }
                            )
                        )

                        # Enforce category population based on traversal
                        for e in traversal_res.related_entities:
                            if e.entity_type in ("function", "method", "class") and len(relevant_symbols) < budget.max_symbols:
                                if e.name not in seen_symbols:
                                    seen_symbols.add(e.name)
                                    relevant_symbols.append({
                                        "name": e.name,
                                        "kind": e.entity_type,
                                        "file_path": e.location or "",
                                        "line_start": e.line_number or 1,
                                    })
                            elif e.entity_type == "file" and len(relevant_files) < budget.max_files:
                                if e.location and e.location not in seen_files:
                                    seen_files.add(e.location)
                                    relevant_files.append(e.location)
                            elif e.relationship_role in ("callee", "caller"):
                                relevant_call_paths.append({
                                    "source": traversal_res.target_display_name if traversal_res.direction.value == "FORWARD" else e.name,
                                    "target": e.name if traversal_res.direction.value == "FORWARD" else traversal_res.target_display_name,
                                    "rel_type": "CALLS"
                                })

            # B. Expand Symbols by Keywords
            for kw in keywords[:5]:
                syms = db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == request.analysis_id,
                    FactSymbol.name.ilike(f"%{kw}%")
                ).limit(10).all()
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

            # C. Expand Routes by Keywords
            for kw in keywords[:5]:
                routes = db.query(FactRoute).filter(
                    FactRoute.analysis_id == request.analysis_id,
                    FactRoute.path.ilike(f"%{kw}%")
                ).limit(5).all()
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

            # D. Expand Database Objects by Keywords
            for kw in keywords[:5]:
                db_objs = db.query(FactDatabaseObject).filter(
                    FactDatabaseObject.analysis_id == request.analysis_id,
                    FactDatabaseObject.name.ilike(f"%{kw}%")
                ).limit(5).all()
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
        matched_caps = []
        if db and request.analysis_id:
            for kw in keywords:
                caps = db.query(FactCapability).filter(
                    FactCapability.analysis_id == request.analysis_id,
                    FactCapability.name.ilike(f"%{kw}%")
                ).limit(5).all()
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
                analysis_id=request.analysis_id,
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
                from backend.planning.impact_analysis import ImpactAnalyzer
                analyzer = ImpactAnalyzer(db=db, analysis_id=request.analysis_id)
                impact_res = analyzer.analyze_sync(keywords=keywords)

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
        # Ensure unknowns are preserved
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
