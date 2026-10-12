"""
Safe Non-Mutating Exploration Mode Handler (Phase 3).
Executes deterministic repository inspection and navigation using QueryLayer and FactStore.
Extracted from backend.agent.modes to maintain modularity.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.agent.intent.semantic_query import classify_semantic_query, SemanticQueryClass, TraversalDirection
from backend.ai.service import LLMService
from backend.config import settings
from backend.database import SessionLocal
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from backend.intelligence.retrieval.target_resolver import TargetEntityResolver
from backend.models.fact_store import FactFile, FactSymbol

logger = logging.getLogger(__name__)


def execute_explore(
    user_requirement: str,
    repository_id: Optional[str] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
    on_event: Optional[Any] = None,
    llm_service: Optional[LLMService] = None,
) -> Dict[str, Any]:
    """
    Executes deterministic repository inspection and navigation.
    Queries QueryLayer and FactStore for symbols, files, classes, functions, and repo tree.
    Strictly isolated to the authenticated user's target repository.
    """
    from backend.agent.modes import resolve_target_repository_and_analysis

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Find matching repository analysis strictly scoped to target repository
        _, analysis_id, repo_name_resolved = resolve_target_repository_and_analysis(db, repository_id, user_id)

        if repository_id and not analysis_id:
            return {
                "response": f"Target repository '{repository_id}' has not been analyzed yet or has no active index.",
                "intent": "explore",
                "model": settings.model_terminal_explore,
                "entities": [],
            }

        query_lower = user_requirement.lower()

        # 1. Repository tree / file listing (when tree is explicitly requested without a specific file or symbol target)
        is_tree_query = any(term in query_lower for term in ["repo tree", "file tree", "show tree", "list files", "directory structure", "show directory"])
        file_path_matches = re.findall(r'[a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+', user_requirement)
        
        if is_tree_query and not file_path_matches:
            query_files = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).limit(30).all() if analysis_id else []
            if query_files:
                file_lines = [f"- `{f.path}` ({f.size or 0} bytes, {f.language or 'code'})" for f in query_files]
                response_text = f"### Repository File Tree for `{repo_name_resolved}` ({len(query_files)} files cataloged):\n\n" + "\n".join(file_lines)
                return {
                    "response": response_text,
                    "intent": "explore",
                    "model": settings.model_terminal_explore,
                    "entities": [{"type": "file", "path": f.path} for f in query_files],
                    "evidence": [{"source_type": "file", "source_id": f.path, "summary": f"Cataloged {f.path}", "path": f.path} for f in query_files],
                }

        # 2. Semantic Query Interpretation & Graph Traversal
        semantic_intent = classify_semantic_query(user_requirement)
        resolver = TargetEntityResolver(db, analysis_id) if analysis_id else None
        traverser = FactStoreGraphTraverser(db, analysis_id) if analysis_id else None

        if resolver and traverser and semantic_intent.target_raw_name:
            target_entity = resolver.resolve(semantic_intent.target_raw_name, hint=semantic_intent.target_hint)
            
            # If a specific relationship intent is recognized
            if semantic_intent.query_class != SemanticQueryClass.GENERIC_LOOKUP:
                if not target_entity:
                    response_text = (
                        f"### Exploration Results for '{semantic_intent.target_raw_name}' in `{repo_name_resolved}`:\n\n"
                        f"Target entity '{semantic_intent.target_raw_name}' was not found in this repository index."
                    )
                    return {
                        "response": response_text,
                        "intent": "explore",
                        "model": settings.model_terminal_explore,
                        "entities": [],
                    }

                traversal_res = traverser.traverse(semantic_intent, target_entity)

                if traversal_res.related_entities:
                    lines = []
                    if traversal_res.query_class == SemanticQueryClass.CONTAINMENT:
                        if isinstance(target_entity, FactFile):
                            lines.append("#### Files and Contained Symbols:")
                            lines.append(f"- **[`{target_entity.path}`](file:///{target_entity.path})** ({target_entity.size or 0} bytes, {len(traversal_res.related_entities)} symbols cataloged)")
                            for e in traversal_res.related_entities:
                                lines.append(f"  - **`{e.name}`** (`{e.entity_type}`) at line {e.line_number or 1}")
                        else:
                            lines.append(f"#### Declared Members in `{traversal_res.target_display_name}`:")
                            for e in traversal_res.related_entities:
                                lines.append(f"- **`{e.name}`** (`{e.entity_type}`) at line {e.line_number or 1}")
                    elif traversal_res.query_class == SemanticQueryClass.IMPORTS_FORWARD:
                        lines.append(f"#### Imported Modules for `{traversal_res.target_display_name}`:")
                        for e in traversal_res.related_entities:
                            lines.append(f"- **`{e.name}`** (`{e.entity_type}`)")
                    elif traversal_res.query_class == SemanticQueryClass.IMPORTS_REVERSE:
                        lines.append(f"#### Dependent Files Importing `{traversal_res.target_display_name}`:")
                        for e in traversal_res.related_entities:
                            lines.append(f"- **[`{e.name}`](file:///{e.name})**")
                    elif traversal_res.query_class == SemanticQueryClass.CALLS_FORWARD:
                        lines.append(f"#### Functions/Methods Called by `{traversal_res.target_display_name}`:")
                        for e in traversal_res.related_entities:
                            loc_str = f" in [`{e.location}:{e.line_number}`](file:///{e.location}#L{e.line_number})" if e.location else ""
                            lines.append(f"- **`{e.name}`** (`{e.entity_type}`){loc_str}")
                    elif traversal_res.query_class == SemanticQueryClass.CALLS_REVERSE:
                        lines.append(f"#### Callers Invoking `{traversal_res.target_display_name}`:")
                        for e in traversal_res.related_entities:
                            loc_str = f" in [`{e.location}:{e.line_number}`](file:///{e.location}#L{e.line_number})" if e.location else ""
                            lines.append(f"- **`{e.name}`** (`{e.entity_type}`){loc_str}")
                    elif traversal_res.query_class == SemanticQueryClass.INHERITS_FORWARD:
                        lines.append(f"#### Base Classes Inherited by `{traversal_res.target_display_name}`:")
                        for e in traversal_res.related_entities:
                            lines.append(f"- **`{e.name}`** (`{e.entity_type}`)")
                    elif traversal_res.query_class == SemanticQueryClass.INHERITS_REVERSE:
                        lines.append(f"#### Subclasses Extending `{traversal_res.target_display_name}`:")
                        for e in traversal_res.related_entities:
                            loc_str = f" in [`{e.location}:{e.line_number}`](file:///{e.location}#L{e.line_number})" if e.location else ""
                            lines.append(f"- **`{e.name}`** (`{e.entity_type}`){loc_str}")
                    elif traversal_res.query_class == SemanticQueryClass.ROUTE_HANDLER:
                        lines.append(f"#### Route Handler for `{traversal_res.target_display_name}`:")
                        for e in traversal_res.related_entities:
                            loc_str = f" in [`{e.location}:{e.line_number}`](file:///{e.location}#L{e.line_number})" if e.location else ""
                            lines.append(f"- **`{e.name}`** (`{e.entity_type}`){loc_str}")
                    elif traversal_res.query_class == SemanticQueryClass.DATABASE_ACCESS:
                        lines.append(f"#### Code Accessing Database Model/Table `{traversal_res.target_display_name}`:")
                        for e in traversal_res.related_entities:
                            loc_str = f" in [`{e.location}:{e.line_number}`](file:///{e.location}#L{e.line_number})" if e.location else ""
                            lines.append(f"- **`{e.name}`** (`{e.entity_type}`){loc_str}")

                    response_text = f"### Exploration Results for '{semantic_intent.target_raw_name}' in `{repo_name_resolved}`:\n\n" + "\n".join(lines)
                    evidence_items = []
                    for e in traversal_res.related_entities:
                        evidence_items.append({
                            "source_type": "symbol" if e.entity_type != "file" else "file",
                            "source_id": e.location or e.name,
                            "summary": f"Inspected {e.name} ({e.entity_type})" if e.name else f"Inspected {e.location}",
                            "path": e.location or "",
                            "line": e.line_number or 1,
                            "symbol": e.name,
                        })

                    return {
                        "response": response_text,
                        "intent": "explore",
                        "model": settings.model_terminal_explore,
                        "entities": [
                            {
                                "name": e.name,
                                "type": e.entity_type,
                                "file": e.location or "",
                                "line": e.line_number or 1,
                                "role": e.relationship_role,
                            }
                            for e in traversal_res.related_entities
                        ] + ([
                            {
                                "name": target_entity.path if isinstance(target_entity, FactFile) else target_entity.name,
                                "type": "file" if isinstance(target_entity, FactFile) else getattr(target_entity, "symbol_type", "entity"),
                                "file": target_entity.path if isinstance(target_entity, FactFile) else (target_entity.file.path if getattr(target_entity, "file", None) else ""),
                                "line": getattr(target_entity, "line_start", 1) or 1,
                                "role": "target_entity",
                            }
                        ] if semantic_intent.query_class == SemanticQueryClass.CONTAINMENT else []),
                        "evidence": evidence_items,
                    }
                else:
                    response_text = (
                        f"### Exploration Results for '{semantic_intent.target_raw_name}' in `{repo_name_resolved}`:\n\n"
                        f"{traversal_res.explanation}"
                    )
                    return {
                        "response": response_text,
                        "intent": "explore",
                        "model": settings.model_terminal_explore,
                        "entities": [],
                        "evidence": [],
                    }

        # 3. Fallback: Generic Symbol & File Keyword Search
        stop_words = {
            "what", "which", "where", "how", "why", "who", "when", "show", "find", "list",
            "give", "tell", "explain", "defined", "implemented", "functions", "function",
            "classes", "class", "methods", "method", "symbols", "symbol", "files", "file",
            "exact", "names", "name", "based", "only", "indexed", "evidence", "repository",
            "repo", "each", "does", "do", "did", "done", "with", "from", "that", "this",
            "these", "those", "their", "have", "has", "had", "been", "here", "there",
            "work", "code", "about", "are", "the", "and", "for", "all", "in", "on", "at",
            "to", "of", "by", "me", "my", "a", "an", "is", "it", "its", "as", "or", "so",
            "if", "up", "out", "no", "not", "be", "we", "he", "she", "us", "you", "they",
            "them", "would", "could", "should", "shall", "will", "can", "may", "might",
            "must", "trace", "detail", "describe", "see", "get", "look", "inspect"
        }

        raw_tokens = re.findall(r'[a-zA-Z0-9_\-\.\/]+', user_requirement)
        search_tokens = [t.strip("./") for t in raw_tokens if len(t.strip("./")) >= 3 and t.lower() not in stop_words]

        if any("auth" in t.lower() or "login" in t.lower() for t in search_tokens):
            if "auth" not in search_tokens:
                search_tokens.append("auth")
            if "jwt" not in search_tokens:
                search_tokens.append("jwt")

        matching_symbols = []
        matching_files = []
        file_symbols_map = {}

        if analysis_id:
            file_conditions = []
            for path_cand in file_path_matches:
                clean_p = path_cand.replace("\\", "/").strip("./")
                file_conditions.append(FactFile.path.ilike(f"%{clean_p}%"))
            for tok in search_tokens:
                if len(tok) >= 3:
                    file_conditions.append(FactFile.path.ilike(f"%{tok}%"))

            if file_conditions:
                matching_files = db.query(FactFile).filter(
                    FactFile.analysis_id == analysis_id,
                    or_(*file_conditions)
                ).limit(10).all()

            if matching_files:
                file_ids = [f.id for f in matching_files]
                file_scoped_symbols = db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == analysis_id,
                    FactSymbol.file_id.in_(file_ids)
                ).order_by(FactSymbol.line_start).all()
                for s in file_scoped_symbols:
                    file_symbols_map.setdefault(s.file_id, []).append(s)
                    if s not in matching_symbols:
                        matching_symbols.append(s)

            symbol_conditions = []
            for tok in search_tokens:
                if len(tok) >= 3:
                    symbol_conditions.append(FactSymbol.name.ilike(f"%{tok}%"))
                    symbol_conditions.append(FactSymbol.qualified_name.ilike(f"%{tok}%"))

            if symbol_conditions:
                token_symbols = db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == analysis_id,
                    or_(*symbol_conditions)
                ).limit(15).all()
                for s in token_symbols:
                    if s not in matching_symbols:
                        matching_symbols.append(s)

        if matching_symbols or matching_files:
            lines = []
            if matching_files:
                lines.append("#### Files and Contained Symbols:")
                for f in matching_files:
                    contained = file_symbols_map.get(f.id, [])
                    lines.append(f"- **[`{f.path}`](file:///{f.path})** ({f.size or 0} bytes, {len(contained)} symbols cataloged)")
                    for s in contained:
                        lines.append(f"  - **`{s.name}`** (`{s.symbol_type}`) at line {s.line_start or 1}")

            standalone_symbols = [s for s in matching_symbols if not (s.file_id and s.file_id in file_symbols_map)]
            if standalone_symbols:
                lines.append("\n#### Other Matching Symbols:")
                for s in standalone_symbols:
                    file_path = s.file.path if s.file else "unknown"
                    lines.append(f"- **`{s.name}`** (`{s.symbol_type}`) in [`{file_path}:{s.line_start}`](file:///{file_path}#L{s.line_start})")

            query_summary = ", ".join(search_tokens[:4]) if search_tokens else user_requirement
            response_text = f"### Exploration Results for '{query_summary}' in `{repo_name_resolved}`:\n\n" + "\n".join(lines)
            return {
                "response": response_text,
                "intent": "explore",
                "model": settings.model_terminal_explore,
                "entities": [
                    {
                        "name": s.name,
                        "type": s.symbol_type,
                        "file": s.file.path if s.file else "",
                        "line": s.line_start or 1,
                    }
                    for s in matching_symbols
                ] + [
                    {
                        "name": f.path,
                        "type": "file",
                        "file": f.path,
                        "line": 1,
                    }
                    for f in matching_files
                ],
                "evidence": [
                    {
                        "source_type": "file",
                        "source_id": f.path,
                        "summary": f"Inspected file {f.path}",
                        "path": f.path,
                    }
                    for f in matching_files
                ] + [
                    {
                        "source_type": "symbol",
                        "source_id": s.name,
                        "summary": f"Found symbol {s.name} in {s.file.path if s.file else ''}",
                        "path": s.file.path if s.file else "",
                        "line": s.line_start or 1,
                        "symbol": s.name,
                    }
                    for s in matching_symbols
                ],
            }

        response_text = (
            f"Exploration query recognized for: '{user_requirement}' in `{repo_name_resolved}`. "
            "No matching symbols or files found in this repository index."
        )
        return {
            "response": response_text,
            "intent": "explore",
            "model": settings.model_terminal_explore,
            "entities": [],
            "evidence": [],
        }

    finally:
        if close_db:
            db.close()
