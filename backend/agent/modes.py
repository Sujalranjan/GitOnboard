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
from typing import Any, Dict, List, Optional
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
    
    ISOLATION INVARIANTS:
      1. When repository_id is None, empty, or 'default', return (None, None, 'default') with analysis_id=None.
         NEVER select a latest or default repository implicitly.
      2. When user_id is provided, lookups are strictly scoped to Repository.user_id == user_id.
         NEVER fall back to global repositories or other users' repositories.
      3. Identity resolution order:
         a. Integer repository.id match (Repository.id == int(repository_id))
         b. Direct integer analysis.id match (Analysis.id == int(repository_id)), checking Analysis.repository.user_id == user_id
         c. Exact repository URL match (Repository.url == repository_id or Repository.url == f"https://github.com/{repository_id}")
         d. Repository slug match (Repository.url.endswith(f"/{repository_id}") or Repository.url.endswith(f"/{repository_id}.git"))
      4. Ambiguity Guard:
         If matching by slug yields multiple repositories for the user (e.g. org-a/common-name and org-b/common-name),
         DO NOT arbitrarily pick one. Return (None, None, repository_id) to reject ambiguous resolution.
    """
    from backend.models.repository import Repository, Analysis

    if not repository_id or not str(repository_id).strip() or str(repository_id).strip().lower() == "default":
        return None, None, "default"

    clean_repo_id = str(repository_id).strip()

    # 1. Direct Integer repository.id match (Authoritative)
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

        # 2. Direct Integer analysis.id match
        query_analysis = db.query(Analysis).filter(Analysis.id == repo_int_id)
        analysis_match = query_analysis.first()
        if analysis_match and analysis_match.repository:
            if user_id is None or analysis_match.repository.user_id == user_id:
                r_name = analysis_match.repository.url.split("/")[-1].replace(".git", "") if analysis_match.repository.url else clean_repo_id
                return analysis_match.repository, analysis_match.id, r_name

    # 3. User-scoped repository query
    query = db.query(Repository)
    if user_id is not None:
        query = query.filter(Repository.user_id == user_id)

    # 3a. Primary numeric repository ID match
    if clean_repo_id.isdigit():
        repo_by_id = query.filter(Repository.id == int(clean_repo_id)).first()
        if repo_by_id:
            repo_name = repo_by_id.url.split("/")[-1].replace(".git", "") if repo_by_id.url else clean_repo_id
            latest_analysis = db.query(Analysis).filter(
                Analysis.repository_id == repo_by_id.id,
                Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
            ).order_by(Analysis.id.desc()).first()
            return repo_by_id, latest_analysis.id if latest_analysis else None, repo_name

    # 3b. Exact URL match
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
    elif len(exact_matches) > 1:
        logger.warning(f"Ambiguous exact matches for repository identifier '{clean_repo_id}' for user_id={user_id}")
        return None, None, clean_repo_id

    # 3b. Slug suffix match (/slug or /slug.git)
    slug_matches = query.filter(
        Repository.url.ilike(f"%/{clean_repo_id}") |
        Repository.url.ilike(f"%/{clean_repo_id}.git")
    ).all()
    if len(slug_matches) == 1:
        repo = slug_matches[0]
        repo_name = repo.url.split("/")[-1].replace(".git", "") if repo.url else clean_repo_id
        latest_analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
        ).order_by(Analysis.id.desc()).first()
        return repo, latest_analysis.id if latest_analysis else None, repo_name
    elif len(slug_matches) > 1:
        logger.warning(f"Ambiguous slug matches for repository identifier '{clean_repo_id}' for user_id={user_id}. Found {len(slug_matches)} repositories.")
        return None, None, clean_repo_id

    # If no match found under user_id, DO NOT fall back to global lookup or another user's repo.
    return None, None, clean_repo_id


def execute_chat(
    user_requirement: str,
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
) -> Dict[str, Any]:
    """
    Executes repository-grounded natural-language explanation.
    Assembles evidence using ContextAssembler and prompts the LLM with evidence-only bounds.
    Strictly isolated to the authenticated user's target repository.
    """
    service = llm_service or build_default_service()
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Find matching repository analysis strictly scoped to target repository
        _, analysis_id, repo_name_resolved = resolve_target_repository_and_analysis(db, repository_id, user_id)

        if repository_id and not analysis_id:
            return {
                "response": f"Target repository '{repository_id}' has not been analyzed yet. Please run an analysis to inspect its architecture.",
                "intent": "explain",
                "model": settings.model_terminal_explain,
                "evidence": [],
                "completeness": "INCOMPLETE",
            }

        # Assemble bounded repository context (deterministic FactStore/AST retrieval)
        assembler = ContextAssembler(llm_service=None)
        req = ContextAssemblyRequest(
            repository_id=repo_name_resolved,
            analysis_id=analysis_id,
            requirement=user_requirement,
            context_budget=ContextBudget(max_files=8, max_symbols=15, max_call_paths=5),
        )
        ctx = assembler.assemble(req, db=db)

        # Build evidence text
        evidence_snippets = []
        if ctx.relevant_files:
            evidence_snippets.append("Relevant Files:\n" + "\n".join(f"- {f}" for f in ctx.relevant_files[:8]))
        if ctx.relevant_symbols:
            evidence_snippets.append("Relevant Symbols:\n" + "\n".join(
                f"- {s.get('name')} ({s.get('symbol_type') or s.get('kind') or 'symbol'}) at {s.get('file_path', '')}:{s.get('line_start', '')}"
                for s in ctx.relevant_symbols[:12]
            ))
        if ctx.relevant_routes:
            evidence_snippets.append("Relevant Routes:\n" + "\n".join(
                f"- {r.get('method')} {r.get('path')} -> {r.get('handler_name', '')}"
                for r in ctx.relevant_routes[:6]
            ))
        if ctx.relevant_call_paths:
            evidence_snippets.append("Call Graphs / Dependencies:\n" + "\n".join(
                f"- {c.get('source_symbol', '')} -> {c.get('target_symbol', '')}"
                for c in ctx.relevant_call_paths[:6]
            ))

        evidence_text = "\n\n".join(evidence_snippets) if evidence_snippets else "No specific symbols found in index."

        system_prompt = (
            f"You are the GitOnboard Repository Architecture Explainer for target repository '{repo_name_resolved}'.\n"
            "Explain the user's question using ONLY the provided repository evidence below.\n\n"
            "GROUNDING RULES:\n"
            "1. Base your explanation directly on the listed files, symbols, routes, and call graphs of this target repository.\n"
            "2. Cite exact file paths and symbols in markdown format: `[Symbol](file_path)`.\n"
            "3. If evidence is missing or insufficient in this repository, explicitly state that repository evidence is absent rather than inventing facts.\n"
            "4. Do NOT discuss GitOnboard application internals or other unrelated repositories.\n"
            "5. Keep the explanation structured, clear, and educational."
        )

        user_content = (
            f"Target Repository: {repo_name_resolved}\n"
            f"User Question: {user_requirement}\n\n"
            f"--- REPOSITORY EVIDENCE ---\n"
            f"{evidence_text}\n"
            f"----------------------------"
        )

        llm_req = LLMRequest(
            model=settings.model_terminal_explain,
            messages=[
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=user_content),
            ],
            temperature=0.2,
            max_tokens=512,
        )

        try:
            resp = asyncio.run(service.generate(llm_req))
            response_text = resp.content.strip()
        except Exception as err:
            logger.warning(f"LLM explanation failed ({err}); using assembled evidence summary.")
            response_text = (
                f"Explanation for '{user_requirement}' in `{repo_name_resolved}`:\n\n"
                f"Based on repository index:\n{evidence_text}"
            )

        evidence_items = [
            {"source_type": e.source_type, "source_id": e.source_id, "summary": e.summary}
            for e in ctx.evidence[:10]
        ]

        return {
            "response": response_text,
            "intent": "explain",
            "model": settings.model_terminal_explain,
            "evidence": evidence_items,
            "completeness": ctx.contract.completeness.value,
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

    service = llm_service or build_default_service()
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
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
        if ctx.metadata is None:
            ctx.metadata = {}
        if analysis_id:
            ctx.metadata["analysis_id"] = analysis_id

        # Iteration 2: 1-Hop Graph Expansion if anchor symbols exist
        expanded_symbols = list(ctx.relevant_symbols)
        seen_sym_names = {s.get("name") for s in expanded_symbols if s.get("name")}
        if analysis_id and expanded_symbols and len(expanded_symbols) < 15:
            top_sym_names = [s.get("name") for s in expanded_symbols[:5] if s.get("name")]
            rel_query = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.rel_type.in_(["CALLS", "IMPORTS", "DEFINED_IN"])
            )
            # Find related symbols
            related_edges = rel_query.limit(20).all()
            for edge in related_edges:
                target_name = edge.to_symbol_id.split(":")[-1] if edge.to_symbol_id else ""
                if target_name and target_name not in seen_sym_names and len(expanded_symbols) < 15:
                    seen_sym_names.add(target_name)
                    expanded_symbols.append({
                        "name": target_name,
                        "kind": "related_symbol",
                        "relation": edge.rel_type,
                        "file_path": "",
                    })

        ctx.relevant_symbols = expanded_symbols

        # 3. Assemble Evidence Text
        evidence_snippets = []
        if ctx.relevant_files:
            evidence_snippets.append("Relevant Files:\n" + "\n".join(f"- `{f}`" for f in ctx.relevant_files[:8]))
        if ctx.relevant_symbols:
            evidence_snippets.append("Relevant Symbols:\n" + "\n".join(
                f"- `{s.get('name')}` ({s.get('kind', 'symbol')}) at `{s.get('file_path', '')}`"
                for s in ctx.relevant_symbols[:12]
            ))
        if ctx.relevant_routes:
            evidence_snippets.append("Relevant Routes:\n" + "\n".join(
                f"- `{r.get('method')} {r.get('path')}` -> `{r.get('handler_name', '')}`"
                for r in ctx.relevant_routes[:6]
            ))

        evidence_text = "\n\n".join(evidence_snippets) if evidence_snippets else "No matching files or symbols found in repository index."

        # 4. Synthesize DAG Plan via PlanningOrchestrator (<10ms)
        import subprocess
        repo_revision = f"rev:{repo_name_resolved}"
        if req.worktree_path and Path(req.worktree_path).exists():
            try:
                res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=req.worktree_path, capture_output=True, text=True, timeout=5)
                if res.returncode == 0 and res.stdout.strip():
                    repo_revision = res.stdout.strip()
            except Exception:
                pass

        orchestrator = PlanningOrchestrator(llm_service=None)
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


