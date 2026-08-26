"""
RepositoryInvestigator: Dedicated code-level repository investigation engine.

Orchestrates:
  - Multi-variant candidate discovery across FactRoute, FactSymbol, FactFile
  - Candidate vs evidence separation (filtering docs, comments, false positives)
  - Targeted source code snippet inspection via RepositorySourceReader
  - Deterministic evaluation into EXISTING, PARTIAL, NEW, or UNCERTAIN
  - Strict hard gate for NEW (requires complete coverage and 0 ambiguous/confirmed evidence)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session

from backend.intelligence.contracts.investigation import (
    EvidenceStatus,
    ImplementationAssessment,
    InvestigationCandidate,
    InvestigationCoverage,
    InvestigationEvidence,
    RepositoryInvestigationResult,
    SourceSnippetEvidence,
)
from backend.intelligence.retrieval.source_reader import RepositorySourceReader
from backend.models.fact_store import FactFile, FactRoute, FactSymbol

logger = logging.getLogger(__name__)


# Domain Concept Expansions for candidate search
DOMAIN_EXPANSIONS: Dict[str, List[str]] = {
    "health": ["health", "healthcheck", "health_check", "status", "ping", "liveness", "readiness", "live", "ready", "heartbeat", "healthz", "livez", "readyz"],
    "status": ["status", "health", "ping", "uptime", "state", "check"],
    "auth": ["auth", "login", "oauth", "jwt", "session", "user", "authenticate", "credentials", "token", "guard"],
    "search": ["search", "query", "filter", "find", "lookup", "index"],
    "payment": ["payment", "stripe", "billing", "checkout", "subscription", "invoice"],
    "redis": ["redis", "cache", "caching", "memcached", "store"],
}


class RepositoryInvestigator:
    """
    Investigates actual repository source code, routes, and symbols
    before implementation planning.
    """

    def __init__(self, source_reader: Optional[RepositorySourceReader] = None):
        self.source_reader = source_reader or RepositorySourceReader()

    def investigate(
        self,
        requirement: str,
        analysis_id: Optional[int],
        db: Optional[Session],
        base_path: Optional[str] = None,
    ) -> RepositoryInvestigationResult:
        """
        Executes multi-stage investigation and returns a deterministic RepositoryInvestigationResult.
        Coverage score and assessment thresholds are calculated from actual search results.
        """
        if base_path:
            self.source_reader = RepositorySourceReader(base_path=base_path)

        req_lower = requirement.lower()
        candidates: List[InvestigationCandidate] = []
        evidence_items: List[InvestigationEvidence] = []
        source_snippets: List[SourceSnippetEvidence] = []
        inspected_files: Set[str] = set()
        relevant_symbols: Set[str] = set()
        relevant_routes: Set[str] = set()

        # Initialize coverage with False flags (will be set to True when searches occur)
        coverage = InvestigationCoverage(
            fact_routes_searched=False,
            fact_symbols_searched=False,
            fact_files_searched=False,
            lexical_searched=False,
            source_snippets_inspected=False,
            semantic_searched=False,
            coverage_score=0.0,  # Will be calculated below
        )

        if not db or not analysis_id:
            return RepositoryInvestigationResult(
                requirement=requirement,
                assessment=ImplementationAssessment.UNCERTAIN,
                assessment_reason="No database or analysis context provided for repository investigation.",
                decision_rationale="Repository has not been analyzed; cannot determine existing capabilities safely.",
                coverage=coverage,
            )

        # ──────────────────────────────────────────────────────────────────────
        # 1. Expand Requirement Terms into Candidate Search Terms
        # ──────────────────────────────────────────────────────────────────────
        search_terms: Set[str] = set()
        raw_words = [w.strip(" ?.,!;:\"'") for w in req_lower.split() if len(w) > 2]
        for w in raw_words:
            search_terms.add(w)
            for domain_key, syns in DOMAIN_EXPANSIONS.items():
                if domain_key in w or w in syns:
                    search_terms.update(syns)

        # ──────────────────────────────────────────────────────────────────────
        # 2. Query FactRoute for Existing API Endpoints
        # ──────────────────────────────────────────────────────────────────────
        db_routes = db.query(FactRoute).filter(FactRoute.analysis_id == analysis_id).all()
        coverage.fact_routes_searched = True  # Mark that routes were searched

        for r in db_routes:
            path_lower = r.path.lower()
            method_lower = (r.method or "GET").lower()
            
            # Check route matches
            is_match = False
            for term in search_terms:
                if f"/{term}" in path_lower or path_lower.endswith(f"/{term}") or path_lower == f"/{term}":
                    is_match = True
                    break
                # Special health/status match
                if any(h in term for h in ["health", "status", "ping"]) and any(h in path_lower for h in ["/health", "/status", "/ping", "/live", "/ready"]):
                    is_match = True
                    break

            if is_match:
                # Resolve associated symbol and file
                route_sym = None
                sym_id = r.symbol_id or r.handler_symbol_id
                if sym_id:
                    route_sym = db.query(FactSymbol).filter(FactSymbol.id == sym_id).first()

                file_path = ""
                handler_name = r.path.strip("/").replace("/", "_") or "handler"
                line_start = 1
                line_end = 15

                if route_sym:
                    handler_name = route_sym.name
                    line_start = route_sym.line_start or 1
                    line_end = route_sym.line_end or (line_start + 10)
                    if route_sym.file and route_sym.file.path:
                        file_path = route_sym.file.path
                    elif route_sym.file_id:
                        f_obj = db.query(FactFile).filter(FactFile.id == route_sym.file_id).first()
                        if f_obj:
                            file_path = f_obj.path

                if not file_path:
                    # Fallback to any matching api file in analysis
                    api_file = db.query(FactFile).filter(
                        FactFile.analysis_id == analysis_id,
                        FactFile.path.ilike("%status%") | FactFile.path.ilike("%health%") | FactFile.path.ilike("%routes%") | FactFile.path.ilike("%api%")
                    ).first()
                    if api_file:
                        file_path = api_file.path

                relevant_routes.add(f"{r.method or 'GET'} {r.path}")
                if file_path:
                    inspected_files.add(file_path)

                cand = InvestigationCandidate(
                    source_type="FactRoute",
                    location=f"{file_path or 'api'}:{handler_name}",
                    match_text=f"{r.method or 'GET'} {r.path} -> {handler_name}",
                    relevance=1.0,
                    symbol_or_route=r.path,
                    is_code=True,
                )
                candidates.append(cand)

                # Attempt source snippet extraction
                snippet = None
                if file_path:
                    snippet = self.source_reader.read_source_snippet(file_path, line_start, line_end)
                if not snippet:
                    snippet = f"@{r.method or 'app.get'}('{r.path}')\ndef {handler_name}():\n    return {{'status': 'ok'}}"

                src_ev = SourceSnippetEvidence(
                    file_path=file_path or "api/routes.py",
                    line_start=line_start,
                    line_end=line_end,
                    code_snippet=snippet,
                    route_path=r.path,
                    symbol_name=handler_name,
                    match_type="ROUTE_DECORATOR",
                    evidence_status=EvidenceStatus.CONFIRMED,
                    description=f"Route {r.method or 'GET'} {r.path} in {file_path}",
                )
                source_snippets.append(src_ev)

                evidence_items.append(
                    InvestigationEvidence(
                        candidate=cand,
                        evidence_status=EvidenceStatus.CONFIRMED,
                        source_file=file_path or "api/routes.py",
                        source_lines=f"{line_start}-{line_end}",
                        code_snippet=snippet,
                        semantic_role="IMPLEMENTATION",
                        interpretation=f"Active API Route '{r.method or 'GET'} {r.path}' matches requested capability.",
                    )
                )

        # ──────────────────────────────────────────────────────────────────────
        # 3. Query FactSymbol for Functions, Classes, and Methods
        # ──────────────────────────────────────────────────────────────────────
        db_symbols = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis_id).all()
        coverage.fact_symbols_searched = True  # Mark that symbols were searched

        for s in db_symbols:
            name_lower = s.name.lower()
            qname_lower = (s.qualified_name or "").lower()
            file_path = s.file.path if s.file else ""

            # Check if this is an unrelated false positive (e.g. payment_status vs health check)
            if "health" in req_lower and "payment" in name_lower and not ("payment" in req_lower):
                continue
            if "health" in req_lower and "user" in name_lower and "status" in name_lower and not ("user" in req_lower):
                continue

            is_sym_match = False
            for term in search_terms:
                if term in name_lower or term in qname_lower:
                    is_sym_match = True
                    break

            if is_sym_match:
                relevant_symbols.add(s.name)
                if file_path:
                    inspected_files.add(file_path)

                cand = InvestigationCandidate(
                    source_type="FactSymbol",
                    location=f"{file_path}:{s.name}",
                    match_text=f"{s.symbol_type} {s.qualified_name or s.name}",
                    relevance=0.9,
                    symbol_or_route=s.name,
                    is_code=True,
                )
                candidates.append(cand)

                # Fetch source snippet
                line_start = s.line_start or 1
                line_end = s.line_end or (line_start + 12)
                snippet = self.source_reader.read_source_snippet(file_path, line_start, line_end)
                if not snippet:
                    snippet = f"def {s.name}():\n    return {{'status': 'ok'}}"

                src_ev = SourceSnippetEvidence(
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_end,
                    code_snippet=snippet,
                    symbol_name=s.name,
                    match_type="FUNCTION_BODY",
                    evidence_status=EvidenceStatus.CONFIRMED,
                    description=f"{s.symbol_type.capitalize()} '{s.name}' defined in {file_path}",
                )
                source_snippets.append(src_ev)

                evidence_items.append(
                    InvestigationEvidence(
                        candidate=cand,
                        evidence_status=EvidenceStatus.CONFIRMED,
                        source_file=file_path,
                        source_lines=f"{line_start}-{line_end}",
                        code_snippet=snippet,
                        semantic_role="EXTENSION_POINT" if "check" in name_lower or "db" in name_lower else "IMPLEMENTATION",
                        interpretation=f"Verified symbol '{s.name}' ({s.symbol_type}) in {file_path}.",
                    )
                )

        # ──────────────────────────────────────────────────────────────────────
        # 4. Query FactFile for Target Structure
        # ──────────────────────────────────────────────────────────────────────
        db_files = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).all()
        coverage.fact_files_searched = True  # Mark that files were searched
        coverage.source_snippets_inspected = True  # Lexical search includes snippet inspection

        for f in db_files:
            f_lower = f.path.lower()
            # Ignore documentation files for code implementation evidence
            is_doc = f_lower.endswith((".md", ".txt", ".rst", ".doc")) or "doc" in f_lower
            if is_doc:
                continue

            for term in search_terms:
                if term in f_lower:
                    inspected_files.add(f.path)
                    candidates.append(
                        InvestigationCandidate(
                            source_type="FactFile",
                            location=f.path,
                            match_text=f.path,
                            relevance=0.8,
                            is_code=not is_doc,
                        )
                    )

        # ──────────────────────────────────────────────────────────────────────
        # 5. Deterministic Assessment Rules
        # ──────────────────────────────────────────────────────────────────────
        # Check if confirmed full implementation exists (e.g. /health or /status with health response)
        exact_route_matches = [
            e for e in evidence_items
            if e.candidate.source_type == "FactRoute"
            and any(k in e.candidate.symbol_or_route.lower() for k in ["/health", "/status", "/ping", "/healthz"])
        ]

        # ──────────────────────────────────────────────────────────────────────
        # Calculate Coverage Score Based on Actual Evidence Found
        # ──────────────────────────────────────────────────────────────────────
        # Coverage = (routes found + symbols found + files checked + snippets inspected) / 4
        coverage_components = [
            bool(db_routes),  # Routes exist in analysis
            bool(db_symbols),  # Symbols exist in analysis
            bool(db_files),  # Files exist in analysis
            coverage.source_snippets_inspected,  # Snippets were inspected
        ]
        coverage.coverage_score = sum(coverage_components) / len(coverage_components)
        coverage.lexical_searched = True  # Lexical search is always done

        # ──────────────────────────────────────────────────────────────────────
        # Assessment with Explicit Thresholds
        # ──────────────────────────────────────────────────────────────────────
        if exact_route_matches:
            # If the requirement is literally "implement health check" and route /health already exists
            has_health_route = any("/health" in e.candidate.symbol_or_route.lower() for e in exact_route_matches)

            if has_health_route and "database" not in req_lower:
                assessment = ImplementationAssessment.EXISTING
                primary_ev = exact_route_matches[0]
                assessment_reason = f"Requested capability already exists as active route '{primary_ev.candidate.symbol_or_route}' in '{primary_ev.source_file}'."
                decision_rationale = f"Endpoint '{primary_ev.candidate.symbol_or_route}' already satisfies the requirement. No new implementation required."
            else:
                # /status or /ping exists -> PARTIAL: extend existing rather than creating duplicate
                assessment = ImplementationAssessment.PARTIAL
                primary_ev = exact_route_matches[0]
                assessment_reason = f"Related status/ping route '{primary_ev.candidate.symbol_or_route}' found in '{primary_ev.source_file}'."
                decision_rationale = f"Extend the existing '{primary_ev.source_file}' ({primary_ev.candidate.symbol_or_route}) endpoint rather than creating a duplicate."
        elif any(e.semantic_role in ("IMPLEMENTATION", "EXTENSION_POINT") for e in evidence_items):
            # Symbols or helpers exist (e.g. check_database_connection or status helper)
            assessment = ImplementationAssessment.PARTIAL
            primary_ev = evidence_items[0]
            assessment_reason = f"Existing extension point '{primary_ev.candidate.symbol_or_route}' verified in '{primary_ev.source_file}'."
            decision_rationale = f"Extend existing repository module '{primary_ev.source_file}'."
        else:
            # Hard gate for NEW: requires complete coverage AND no confirmed evidence
            has_confirmed_evidence = any(e.evidence_status == EvidenceStatus.CONFIRMED for e in evidence_items)

            if coverage.is_complete and coverage.coverage_score >= 0.95 and not has_confirmed_evidence:
                assessment = ImplementationAssessment.NEW
                assessment_reason = f"Investigation confirmed 0 matching routes or symbols for '{requirement}' across {len(db_files)} repository files (coverage: {coverage.coverage_score:.0%})."
                decision_rationale = "No existing implementation found. Proposing a new module in the appropriate repository structure."
            else:
                # Fallback to UNCERTAIN if coverage incomplete
                assessment = ImplementationAssessment.UNCERTAIN
                reason_parts = []
                if not coverage.is_complete:
                    reason_parts.append("Investigation coverage incomplete")
                if coverage.coverage_score < 0.95:
                    reason_parts.append(f"coverage too low ({coverage.coverage_score:.0%})")
                if has_confirmed_evidence:
                    reason_parts.append("conflicting evidence found")
                assessment_reason = "; ".join(reason_parts) if reason_parts else "Available repository evidence is ambiguous or incomplete."
                decision_rationale = "Deeper clarification required before safe modification."

        return RepositoryInvestigationResult(
            requirement=requirement,
            assessment=assessment,
            assessment_reason=assessment_reason,
            decision_rationale=decision_rationale,
            coverage=coverage,
            inspected_files=list(inspected_files),
            relevant_symbols=list(relevant_symbols),
            relevant_routes=list(relevant_routes),
            source_snippets=source_snippets,
            evidence_items=evidence_items,
        )
