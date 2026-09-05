"""
Safe Non-Mutating Mode Handlers for CHAT, EXPLORE, and EXPLAIN (Phase 3).

Guarantees:
  - CHAT: Conversational LLM interaction with zero repository/database access.
  - EXPLORE: Deterministic repository symbol/file/tree query using QueryLayer and FactStore.
  - EXPLAIN: Grounded architectural explanation using ContextAssembler and bounded evidence.
  - SAFETY INVARIANT: Strictly read-only. Structurally incapable of mutating repository or files.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import ContextAssemblyRequest, ContextBudget
from backend.ai.schemas import LLMRequest, Message, MessageRole
from backend.ai.service import LLMService, build_default_service
from backend.config import settings
from backend.database import SessionLocal
from backend.models.repository import Analysis
from backend.models.fact_store import FactFile, FactSymbol

logger = logging.getLogger(__name__)


def resolve_target_repository_and_analysis(
    db: Session,
    repository_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> tuple[Optional[Any], Optional[int], str]:
    """
    Strictly resolves target Repository and latest Analysis with zero cross-user leakage
    and zero implicit fallback.
    """
    if not repository_id or not str(repository_id).strip() or str(repository_id).strip().lower() == "default":
        return None, None, "default"

    clean_repo_id = str(repository_id).strip()

    try:
        from backend.models.repository import Repository, Analysis

        # 1. Direct Integer repository.id match
        if clean_repo_id.isdigit():
            repo_int_id = int(clean_repo_id)
            query = db.query(Repository).filter(Repository.id == repo_int_id)
            if user_id is not None:
                query = query.filter(Repository.user_id == user_id)
            repo = query.first()
            if repo:
                repo_name = repo.url.split("/")[-1].replace(".git", "") if repo.url else clean_repo_id
                latest_analysis = db.query(Analysis).filter(
                    Analysis.repository_id == repo.id,
                    Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                ).order_by(Analysis.id.desc()).first()
                return repo, latest_analysis.id if latest_analysis else None, repo_name

        # 2. Exact URL / slug match
        query = db.query(Repository)
        if user_id is not None:
            query = query.filter(Repository.user_id == user_id)

        exact_matches = query.filter(
            (Repository.url == clean_repo_id) |
            (Repository.url == f"https://github.com/{clean_repo_id}") |
            (Repository.url == f"https://github.com/{clean_repo_id}.git")
        ).all()
        if len(exact_matches) == 1:
            repo = exact_matches[0]
            repo_name = repo.url.split("/")[-1].replace(".git", "") if repo.url else clean_repo_id
            latest_analysis = db.query(Analysis).filter(
                Analysis.repository_id == repo.id,
                Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
            ).order_by(Analysis.id.desc()).first()
            return repo, latest_analysis.id if latest_analysis else None, repo_name

        # 3. Slug match
        slug_matches = query.filter(
            (Repository.url.endswith(f"/{clean_repo_id}")) |
            (Repository.url.endswith(f"/{clean_repo_id}.git"))
        ).all()
        if len(slug_matches) == 1:
            repo = slug_matches[0]
            repo_name = repo.url.split("/")[-1].replace(".git", "") if repo.url else clean_repo_id
            latest_analysis = db.query(Analysis).filter(
                Analysis.repository_id == repo.id,
                Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
            ).order_by(Analysis.id.desc()).first()
            return repo, latest_analysis.id if latest_analysis else None, repo_name

    except Exception as err:
        logger.debug(f"Database lookup in resolve_target_repository_and_analysis bypassed: {err}")

    return None, None, clean_repo_id

def resolve_worktree_path(repo_name: str, repo: Optional[Any] = None) -> Optional[str]:
    from pathlib import Path
    from backend.config import settings
    
    if repo and hasattr(repo, "local_path") and repo.local_path and Path(repo.local_path).exists():
        return str(Path(repo.local_path).resolve())
    
    if repo_name and repo_name != "default":
        candidates = [
            Path(settings.worktrees_dir) / repo_name,
            Path("data/worktrees") / repo_name,
            Path("data/repos") / repo_name,
            Path(settings.storage_path) / "worktrees" / repo_name,
            Path(settings.storage_path) / "repos" / repo_name,
            Path("/app/data/worktrees") / repo_name,
            Path("/app/data/repos") / repo_name,
            Path("/home/dheeraj/repository_intelligence_platform/data/worktrees") / repo_name,
            Path("/home/dheeraj/repository_intelligence_platform/data/repos") / repo_name,
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                return str(c.resolve())
    return None

def execute_chat(
    user_requirement: str,
    repository_id: Optional[str] = None,
    user_id: Optional[int] = None,
    llm_service: Optional[LLMService] = None,
) -> Dict[str, Any]:
    """
    Executes conversational interaction without repository or database retrieval.
    """
    service = llm_service or build_default_service()
    system_prompt = (
        "You are the Repository Intelligence Assistant. "
        "Provide friendly, helpful, and concise responses about your capabilities: exploring codebases, "
        "finding symbols, explaining architecture, and safely understanding software repositories. "
        "Do not invent facts or assume specific repository contents unless evidence is provided."
    )
    req = LLMRequest(
        model=settings.model_terminal_chat,
        messages=[
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=user_requirement),
        ],
        temperature=0.7,
        max_tokens=256,
    )
    try:
        resp = asyncio.run(service.generate(req))
        response_text = resp.content.strip()
    except Exception as err:
        logger.warning(f"LLM chat generation failed ({err}); using default capability message.")
        response_text = (
            "Hello! I am your Repository Intelligence Assistant. "
            "You can ask me to explore files, explain architectures, plan features, or understand code."
        )

    return {
        "response": response_text,
        "intent": "chat",
        "model": settings.model_terminal_chat,
        "evidence": [],
    }


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

        import re
        from sqlalchemy import or_
        from backend.agent.intent.semantic_query import classify_semantic_query, SemanticQueryClass, TraversalDirection
        from backend.intelligence.retrieval.target_resolver import TargetEntityResolver
        from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser

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
                    # Target does NOT exist in repository index -> Return clean grounded not found without lexical fallback
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
                    # Format by relationship class
                    if traversal_res.query_class == SemanticQueryClass.CONTAINMENT:
                        if isinstance(target_entity, FactFile):
                            lines.append(f"#### Files and Contained Symbols:")
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
                    # Honest missing relationship notification
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

        # 3. Fallback: Generic Symbol & File Keyword Search (Only for unformatted generic search)
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

        # Check for authentication synonyms
        if any("auth" in t.lower() or "login" in t.lower() for t in search_tokens):
            if "auth" not in search_tokens:
                search_tokens.append("auth")
            if "jwt" not in search_tokens:
                search_tokens.append("jwt")

        matching_symbols = []
        matching_files = []
        file_symbols_map = {}

        if analysis_id:
            # A. Match files directly mentioned in requirement (or by token)
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

            # B. Fetch all symbols declared inside the matched files
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

            # C. Search symbols by identifier tokens (only if specific non-stopword tokens exist)
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
            
            # If files have contained symbols, display grouped by file
            if matching_files:
                lines.append("#### Files and Contained Symbols:")
                for f in matching_files:
                    contained = file_symbols_map.get(f.id, [])
                    lines.append(f"- **[`{f.path}`](file:///{f.path})** ({f.size or 0} bytes, {len(contained)} symbols cataloged)")
                    for s in contained:
                        lines.append(f"  - **`{s.name}`** (`{s.symbol_type}`) at line {s.line_start or 1}")

            # If there are standalone matching symbols not covered in files above
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


def execute_explain(
    user_requirement: str,
    repository_id: Optional[str] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
    llm_service: Optional[LLMService] = None,
    on_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes repository-grounded natural-language explanation.
    Reads actual source files from the active worktree and prompts the LLM with real code.
    Strictly isolated to the authenticated user's target repository.
    """
    from backend.intelligence.retrieval.source_reader import RepositorySourceReader
    import re
    import time

    service = llm_service or build_default_service()
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        if on_event:
            on_event({
                "type": "activity",
                "item": {
                    "id": f"search-{time.time()}",
                    "type": "search",
                    "title": f"Search repository context for '{user_requirement}'",
                    "status": "completed",
                }
            })

        repo_obj, analysis_id, repo_name_resolved = resolve_target_repository_and_analysis(db, repository_id, user_id)
        worktree_path = resolve_worktree_path(repo_name_resolved, repo_obj)
        source_reader = RepositorySourceReader(base_path=worktree_path, db=db, analysis_id=analysis_id)

        # 1. Identify target file(s) mentioned in prompt or from index
        target_files: List[str] = []
        file_matches = re.findall(r'[a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+', user_requirement)
        for fm in file_matches:
            resolved_p = source_reader.resolve_file_path(fm)
            if resolved_p and source_reader.base_path:
                try:
                    rel_path = str(resolved_p.relative_to(source_reader.base_path)).replace(chr(92), "/")
                except ValueError:
                    rel_path = fm
                if rel_path not in target_files:
                    target_files.append(rel_path)
            elif analysis_id:
                clean_fm = fm.strip("/\\")
                base_fm = Path(clean_fm).name.lower()
                db_file = db.query(FactFile).filter(
                    FactFile.analysis_id == analysis_id,
                    or_(
                        FactFile.path == clean_fm,
                        FactFile.path == f".{clean_fm}",
                        FactFile.path.ilike(f"%{clean_fm}"),
                        FactFile.path.ilike(f"%/{base_fm}"),
                        FactFile.path.ilike(base_fm),
                    )
                ).first()
                if db_file and db_file.path not in target_files:
                    target_files.append(db_file.path)

        # Explicit GitHub Actions / CI Workflow discovery
        req_lower = user_requirement.lower()
        is_workflow_query = any(w in req_lower for w in ["github action", "github actions", "workflow", "workflows", "ci/cd", "ci pipeline", "action"])
        if is_workflow_query:
            workflow_files = []
            if source_reader.base_path:
                for wf_dir_name in [".github/workflows", "github/workflows"]:
                    wf_dir = source_reader.base_path / wf_dir_name
                    if wf_dir.exists() and wf_dir.is_dir():
                        for p in sorted(wf_dir.glob("*.y*ml")):
                            try:
                                rel = str(p.relative_to(source_reader.base_path)).replace(chr(92), "/")
                                if rel not in workflow_files:
                                    workflow_files.append(rel)
                            except Exception:
                                pass

            if not workflow_files and analysis_id:
                db_wf_files = db.query(FactFile).filter(
                    FactFile.analysis_id == analysis_id,
                    or_(
                        FactFile.path.ilike("%workflows/%.yml"),
                        FactFile.path.ilike("%workflows/%.yaml"),
                        FactFile.path.ilike("%.github/workflows/%"),
                    )
                ).all()
                for wf in db_wf_files:
                    if wf.path not in workflow_files:
                        workflow_files.append(wf.path)

            if workflow_files:
                target_files = workflow_files[:5]

        # Check if prompt mentions a directory/module (e.g., 'pls_cli', 'tests', 'utils', 'docs')
        if not target_files and analysis_id:
            words = [w.strip("'\":,./\\") for w in user_requirement.split() if len(w) > 2]
            for w in words:
                if w.lower() in {"explain", "folder", "directory", "package", "module", "code", "repo", "repository", "this", "that", "what", "does", "the"}:
                    continue
                dir_files = db.query(FactFile).filter(
                    FactFile.analysis_id == analysis_id,
                    or_(
                        FactFile.path.ilike(f"{w}/%"),
                        FactFile.path.ilike(f"%/{w}/%"),
                        FactFile.path.ilike(f"{w.replace('-', '_')}/%"),
                        FactFile.path.ilike(f"%/{w.replace('-', '_')}/%"),
                    )
                ).limit(5).all()
                for df in dir_files:
                    if df.path not in target_files:
                        target_files.append(df.path)
                if target_files:
                    break

        # If no explicit file mentioned or found, query ContextAssembler to locate candidate files
        if not target_files:
            assembler = ContextAssembler(llm_service=None, worktree_path=worktree_path)
            req = ContextAssemblyRequest(
                repository_id=repo_name_resolved,
                analysis_id=analysis_id,
                requirement=user_requirement,
                worktree_path=worktree_path,
                context_budget=ContextBudget(max_files=5, max_symbols=8, max_call_paths=2),
            )
            ctx = assembler.assemble(req, db=db)
            sorted_files = sorted(
                ctx.relevant_files,
                key=lambda p: 0 if p.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java")) else (1 if p.endswith((".yml", ".yaml")) else (3 if any(p.lower().endswith(m) for m in ["code_of_conduct.md", "license", "funding.yml", "dependabot.yml"]) else 2))
            )
            for f in sorted_files:
                if not f.endswith(".json") and not any(f.lower().endswith(m) for m in ["code_of_conduct.md", "license", "funding.yml", "dependabot.yml"]) and f not in target_files and len(target_files) < 3:
                    target_files.append(f)

        # 2. Read actual source code for target files (focused lines for local inference)
        source_code_blocks = []
        actual_read_evidence = []
        for tf in target_files:
            if on_event:
                on_event({
                    "type": "activity",
                    "item": {
                        "id": f"read-{tf}",
                        "type": "read",
                        "title": f"Read {tf}",
                        "file": tf,
                        "startLine": 1,
                        "status": "running",
                    }
                })
            code = source_reader.read_file_content(tf, max_lines=400)
            if code:
                line_count = max(1, len(code.splitlines()))
                source_code_blocks.append(f"File: `{tf}` (lines 1–{line_count})\n```yaml\n{code}\n```" if tf.endswith((".yml", ".yaml")) else f"File: `{tf}` (lines 1–{line_count})\n```python\n{code}\n```")
                actual_read_evidence.append({
                    "source_type": "source_code",
                    "source_id": tf,
                    "summary": f"Read source of {tf} (lines 1–{line_count})",
                    "path": tf,
                    "start_line": 1,
                    "end_line": line_count,
                })
                if on_event:
                    on_event({
                        "type": "activity",
                        "item": {
                            "id": f"read-{tf}",
                            "type": "read",
                            "title": f"Read {tf}",
                            "file": tf,
                            "startLine": 1,
                            "endLine": line_count,
                            "start_line": 1,
                            "end_line": line_count,
                            "status": "completed",
                        }
                    })
            else:
                if on_event:
                    on_event({
                        "type": "activity",
                        "item": {
                            "id": f"read-{tf}",
                            "type": "read",
                            "title": f"Read {tf}",
                            "file": tf,
                            "status": "failed",
                            "error": "File not found on disk",
                        }
                    })

        if not source_code_blocks and not analysis_id:
            return {
                "response": f"Target repository '{repository_id}' has not been analyzed or is unavailable on disk.",
                "intent": "explain",
                "model": settings.model_terminal_explain,
                "evidence": [],
                "completeness": "INCOMPLETE",
            }

        # 3. Extract RIM metadata from retriever with graph expansion
        rim_metadata_block = None
        rim_trace = {
            "anchors": [],
            "expanded_entities": [],
            "relationships": [],
            "graph_depth": 0,
        }

        if analysis_id:
            try:
                from backend.services.rim_metadata import build_rim_metadata_block
                from backend.intelligence.retrieval.retriever import HybridRetriever

                retriever = HybridRetriever(
                    db=db,
                    analysis_id=analysis_id,
                    enable_graph_expansion=True,
                    graph_expansion_depth=2,
                    graph_expansion_nodes_per_hop=3,
                    graph_expansion_max_total=30,
                )

                rim_metadata_block = build_rim_metadata_block(
                    db=db,
                    analysis_id=analysis_id,
                    question=user_requirement,
                    retriever=retriever,
                    max_seed_entities=3,
                    max_related_per_seed=8,
                    max_block_chars=2000,
                )

                if rim_metadata_block:
                    rim_trace = {
                        "anchors": rim_metadata_block.anchor_entities,
                        "expanded_entities": rim_metadata_block.expanded_entities,
                        "relationships": rim_metadata_block.relationships,
                        "relationship_types": rim_metadata_block.relationship_types_used,
                        "graph_depth": rim_metadata_block.expansion_depth,
                        "total_nodes_expanded": rim_metadata_block.total_nodes_expanded,
                    }

                    logger.info(
                        f"[EXPLAIN_RIM] RIM metadata built: "
                        f"anchors={len(rim_metadata_block.anchor_entities)}, "
                        f"expanded={len(rim_metadata_block.expanded_entities)}, "
                        f"relationships={len(rim_metadata_block.relationships)}"
                    )
            except Exception as err:
                logger.warning(f"[EXPLAIN_RIM] Failed to build RIM metadata: {err}", exc_info=True)

        # 4. Build grounded prompt for LLM with real code
        code_context = "\n\n".join(source_code_blocks) if source_code_blocks else "No source code content available."
        total_code_chars = sum(len(b) for b in source_code_blocks)

        # Build RIM metadata block text for injection
        rim_context = ""
        if rim_metadata_block and rim_metadata_block.text:
            rim_context = f"\n--- REPOSITORY INTELLIGENCE MAPPING (RIM) ---\n{rim_metadata_block.text}\n"

        logger.info(
            f"\n==================== EXPLAIN CONTEXT DEBUG ====================\n"
            f"Requirement: {user_requirement}\n"
            f"Target Repository: {repo_name_resolved}\n"
            f"Selected Files ({len(target_files)}): {target_files}\n"
            f"Loaded Source Blocks: {len(source_code_blocks)}\n"
            f"Total Source Characters: {total_code_chars}\n"
            f"Estimated Context Tokens: {total_code_chars // 4}\n"
            f"RIM Metadata Present: {bool(rim_metadata_block and rim_metadata_block.text)}\n"
            f"RIM Anchors: {len(rim_trace.get('anchors', []))}\n"
            f"RIM Expanded: {len(rim_trace.get('expanded_entities', []))}\n"
            f"LLM Provider: ollama (model: {settings.model_terminal_explain})\n"
            f"Source Context Present: {bool(source_code_blocks)}\n"
            f"==============================================================="
        )

        from backend.agent.context.rim_guidance import get_rim_guidance_for_system_prompt

        rim_guidance = get_rim_guidance_for_system_prompt(
            include_sections=['anchor', 'positive', 'negative', 'priority', 'direction'],
            max_chars=2000
        )

        system_prompt = (
            f"You are the GitOnboard Repository Architecture Explainer for target repository '{repo_name_resolved}'.\n"
            "Explain the user's question clearly, accurately, and thoroughly based on the actual source code and architectural relationships provided below.\n\n"
            "GROUNDING RULES:\n"
            "1. Base your explanation directly on the provided source code, workflows, classes, and functions.\n"
            "2. If Repository Intelligence Mapping (RIM) relationships are provided, cite them to explain how components interact.\n"
            "3. Use relationship verbs like CALLS, IMPORTS, CONTAINS, etc. when referencing architectural flow.\n"
            "4. Provide a clear overview of the purpose, core components, and logic flow.\n"
            "5. Keep the explanation structured, clean, and educational.\n"
            "6. For questions about absence or non-existence, be careful: express uncertainty when evidence is incomplete.\n\n"
            "REPOSITORY RELATIONSHIP INTERPRETATION GUIDE:\n"
            f"{rim_guidance}"
        )

        user_content = (
            f"Target Repository: {repo_name_resolved}\n"
            f"User Question: {user_requirement}\n\n"
            f"--- REPOSITORY SOURCE CODE & WORKFLOWS ---\n"
            f"{code_context}"
            f"{rim_context}\n"
            f"-----------------------------------------"
        )

        llm_req = LLMRequest(
            model=settings.model_terminal_explain,
            messages=[
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=user_content),
            ],
            temperature=0.2,
            max_tokens=650,
        )

        if on_event:
            on_event({
                "type": "activity",
                "item": {
                    "id": "llm-synth",
                    "type": "info",
                    "title": f"Analyze with {settings.model_terminal_explain}",
                    "status": "completed",
                }
            })

        # Log final LLM request for verification (RIM metadata injection)
        logger.info(
            f"[EXPLAIN_LLM_REQUEST] Final user_content length: {len(user_content)} chars\n"
            f"[EXPLAIN_LLM_REQUEST] Contains RIM block: {'--- REPOSITORY INTELLIGENCE MAPPING' in user_content}\n"
            f"[EXPLAIN_LLM_REQUEST] Relationships in metadata: {rim_trace.get('relationship_types', [])}"
        )

        try:
            resp = asyncio.run(service.generate(llm_req))
            response_text = resp.content.strip()
        except Exception as err:
            logger.error(f"[EXPLAIN_FAILURE] LLM explanation generation failed: {err}", exc_info=True)
            response_text = f"Unable to generate the explanation because the coding model ({settings.model_terminal_explain}) did not respond: {err}."

        return {
            "response": response_text,
            "intent": "explain",
            "model": settings.model_terminal_explain,
            "evidence": actual_read_evidence,
            "completeness": "COMPLETE" if source_code_blocks else "PARTIAL",
            "rim_trace": rim_trace,
        }
    finally:
        if close_db:
            db.close()

def execute_plan(
    user_requirement: str,
    repository_id: Optional[str] = None,
    user_id: Optional[int] = None,
    agent_run_id: Optional[str] = None,
    analysis_id: Optional[int] = None,
    db: Optional[Session] = None,
    llm_service: Optional[LLMService] = None,
    on_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes repository-aware implementation planning (Phase 4).
    
    Guarantees:
      - Strictly read-only planning. 0 file writes, 0 worktree checkouts, 0 shell mutations.
      - Bounded context acquisition loop (<= 2 iterations).
      - Grounds tasks in FactStore facts vs explicit NEW components vs unknowns.
      - Validates DAG acyclicity, acceptance criteria, and verification strategies.
    """
    from backend.agent.planning.orchestrator import PlanningOrchestrator
    from backend.models.fact_store import FactRelationship
    import time

    service = llm_service or build_default_service()
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        if on_event:
            on_event({
                "type": "activity",
                "item": {
                    "id": f"plan-start-{time.time()}",
                    "type": "search",
                    "title": f"Analyzing repository for '{user_requirement}'",
                    "status": "running",
                }
            })

        # 1. Resolve repository and analysis_id strictly scoped to user and target
        if not analysis_id:
            _, analysis_id, repo_name_resolved = resolve_target_repository_and_analysis(db, repository_id, user_id)
        else:
            repo_name_resolved = repository_id or "default"

        # 2. Bounded Context Acquisition Loop (Max 2 Iterations)
        # Iteration 1: Initial Context Assembly (deterministic FactStore/AST retrieval)
        assembler = ContextAssembler(llm_service=None)
        req = ContextAssemblyRequest(
            repository_id=repo_name_resolved,
            analysis_id=analysis_id,
            requirement=user_requirement,
            context_budget=ContextBudget(max_files=8, max_symbols=15, max_call_paths=5),
        )
        ctx = assembler.assemble(req, db=db)

        # Iteration 2: Refine context with graph-derived dependencies if gaps exist
        if len(ctx.relevant_files) < 2 and analysis_id:
            related_symbols = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis_id
            ).limit(10).all()
            for rel in related_symbols:
                if rel.target_file_id and rel.target_file_id not in ctx.relevant_files:
                    ctx.relevant_files.append(rel.target_file_id)

        # 3. Determine Repository Revision
        repo_revision = "main"
        if repo_name_resolved:
            from backend.models.repository import Repository
            repo_record = db.query(Repository).filter(
                (Repository.url.ilike(f"%/{repo_name_resolved}%")) | 
                (Repository.url == repo_name_resolved) |
                (Repository.id == (int(repo_name_resolved) if repo_name_resolved.isdigit() else -1))
            ).first()
            if repo_record and getattr(repo_record, "default_branch", None):
                repo_revision = repo_record.default_branch

        # 4. Invoke LLM-backed Planning Orchestrator
        if on_event:
            on_event({
                "type": "activity",
                "item": {
                    "id": f"plan-synth-{time.time()}",
                    "type": "info",
                    "title": "Synthesizing implementation plan...",
                    "status": "running",
                }
            })

        orchestrator = PlanningOrchestrator(llm_service=service)
        if analysis_id:
            ctx.analysis_id = analysis_id
            if ctx.metadata is None:
                ctx.metadata = {}
            ctx.metadata["analysis_id"] = analysis_id

        plan = orchestrator.create_plan(
            context=ctx,
            agent_run_id=agent_run_id or f"run_plan_{repo_name_resolved}",
            repository_id=repo_name_resolved,
            requirement=user_requirement,
            db=db,
            version=1,
            repository_revision=repo_revision,
        )

        # 5. Format Concise Executive Summary Response
        task_count = len(plan.tasks)
        file_count = len(ctx.relevant_files)
        analysis_tag = f"Analysis #{analysis_id}" if analysis_id else "Analysis #N/A"
        response_text = (
            f"Repository-aware implementation plan synthesized for: *{user_requirement}* "
            f"({repo_name_resolved}, {analysis_tag}, {task_count} {'task' if task_count == 1 else 'tasks'} · {file_count} {'file' if file_count == 1 else 'files'})."
        )

        return {
            "response": response_text,
            "intent": "plan",
            "model": settings.model_terminal_plan,
            "plan": plan.model_dump(mode="json"),
            "evidence": [
                {"source_type": e.source_type, "source_id": e.source_id, "summary": e.summary}
                for e in ctx.evidence[:10]
            ],
            "unknowns": plan.unknowns,
            "risks": plan.risks,
            "is_valid": plan.validation.valid if plan.validation else False,
        }

    finally:
        if close_db:
            db.close()


def execute_implement(
    user_requirement: str,
    repository_id: Optional[str] = None,
    agent_run_id: Optional[str] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
    on_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Safe Intent.IMPLEMENT handler (Phase 5).
    Synthesizes a repository-aware plan and establishes the server approval gate.
    Guarantees:
      - Repository-aware planning using Phase 4 pipeline.
      - Plan status is READY_FOR_APPROVAL.
      - AgentRun state is AWAITING_APPROVAL.
      - ZERO file mutations, ZERO shell executions, ZERO task executions.
    """
    res = execute_plan(
        user_requirement=user_requirement,
        repository_id=repository_id,
        user_id=user_id,
        agent_run_id=agent_run_id,
        db=db,
        on_event=on_event,
    )
    task_count = len(res.get("plan", {}).get("tasks", []))
    res["intent"] = "implement"
    res["model"] = settings.model_terminal_implement
    res["status"] = "READY_FOR_APPROVAL"
    res["response"] = (
        f"Implementation plan synthesized for: *{user_requirement}* "
        f"({task_count} {'task' if task_count == 1 else 'tasks'}). Ready for review."
    )
    return res


