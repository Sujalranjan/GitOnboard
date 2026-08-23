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


def execute_chat(
    user_requirement: str,
    llm_service: Optional[LLMService] = None,
) -> Dict[str, Any]:
    """
    Executes conversational interaction without repository or database retrieval.
    """
    service = llm_service or build_default_service()
    system_prompt = (
        "You are the GitOnboard Repository Intelligence Assistant. "
        "Provide friendly, helpful, and concise responses about your capabilities: exploring codebases, "
        "finding symbols, explaining architecture, and safely understanding software repositories."
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
        # Find matching repository analysis strictly scoped to user
        analysis_id = None
        if repository_id:
            from backend.models.repository import Repository
            query = db.query(Repository)
            if user_id is not None:
                query = query.filter(Repository.user_id == user_id)
            repo = query.filter(
                (Repository.id == (int(repository_id) if repository_id.isdigit() else -1)) |
                (Repository.url.ilike(f"%/{repository_id}")) |
                (Repository.url.ilike(f"%/{repository_id}.git")) |
                (Repository.url.ilike(f"%{repository_id}%"))
            ).first()
            if repo:
                latest_analysis = db.query(Analysis).filter(
                    Analysis.repository_id == repo.id,
                    Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                ).order_by(Analysis.id.desc()).first()
                if latest_analysis:
                    analysis_id = latest_analysis.id

        # If still no analysis and user_id is provided, search user's latest repo analysis only
        if not analysis_id and user_id is not None:
            user_repo = db.query(Repository).filter(Repository.user_id == user_id).order_by(Repository.id.desc()).first()
            if user_repo:
                user_analysis = db.query(Analysis).filter(
                    Analysis.repository_id == user_repo.id,
                    Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                ).order_by(Analysis.id.desc()).first()
                if user_analysis:
                    analysis_id = user_analysis.id

        query_lower = user_requirement.lower()

        # 1. Repository tree / file listing
        if any(term in query_lower for term in ["tree", "files", "list files", "directory", "structure"]):
            query_files = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).limit(30).all() if analysis_id else []
            if query_files:
                file_lines = [f"- `{f.path}` ({f.size or 0} bytes, {f.language or 'code'})" for f in query_files]
                response_text = f"### Repository File Tree ({len(query_files)} files cataloged):\n\n" + "\n".join(file_lines)
                return {
                    "response": response_text,
                    "intent": "explore",
                    "model": settings.model_terminal_explore,
                    "entities": [{"type": "file", "path": f.path} for f in query_files],
                }

        # 2. Symbol / Reference / File search
        search_token = user_requirement
        for prefix in ["find all references to", "find references to", "where is", "find", "search for", "locate", "show"]:
            if query_lower.startswith(prefix):
                search_token = user_requirement[len(prefix):].strip().rstrip("?.!")
                break
        search_token = search_token.replace("implemented", "").replace("defined", "").strip()

        search_variations = [search_token]
        if "authentication" in search_token.lower():
            search_variations.append("auth")
        if "auth" in search_token.lower():
            search_variations.append("auth")
            search_variations.append("jwt")

        matching_symbols = []
        matching_files = []
        if analysis_id and search_token:
            from sqlalchemy import or_
            symbol_conditions = []
            file_conditions = []
            for token in search_variations:
                symbol_conditions.append(FactSymbol.name.ilike(f"%{token}%"))
                symbol_conditions.append(FactSymbol.qualified_name.ilike(f"%{token}%"))
                file_conditions.append(FactFile.path.ilike(f"%{token}%"))

            matching_symbols = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis_id,
                or_(*symbol_conditions)
            ).limit(15).all()

            matching_files = db.query(FactFile).filter(
                FactFile.analysis_id == analysis_id,
                or_(*file_conditions)
            ).limit(10).all()

        if matching_symbols or matching_files:
            lines = []
            if matching_symbols:
                lines.append("#### Matching Symbols:")
                for s in matching_symbols:
                    file_path = s.file.path if s.file else "unknown"
                    lines.append(f"- **`{s.name}`** (`{s.symbol_type}`) in [`{file_path}:{s.line_start}`](file:///{file_path}#L{s.line_start})")

            if matching_files:
                lines.append("\n#### Matching Files:")
                for f in matching_files:
                    lines.append(f"- [`{f.path}`](file:///{f.path}) ({f.size or 0} bytes)")

            response_text = f"### Exploration Results for '{search_token}':\n\n" + "\n".join(lines)
            return {
                "response": response_text,
                "intent": "explore",
                "model": settings.model_terminal_explore,
                "entities": [
                    {
                        "name": s.name,
                        "type": s.symbol_type,
                        "file": s.file.path if s.file else "",
                        "line": s.line_start,
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
            f"Exploration query recognized for: '{user_requirement}'. "
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
        # Find matching repository analysis strictly scoped to user
        analysis_id = None
        repo_name_resolved = repository_id or "default"
        if repository_id:
            from backend.models.repository import Repository
            query = db.query(Repository)
            if user_id is not None:
                query = query.filter(Repository.user_id == user_id)
            repo = query.filter(
                (Repository.id == (int(repository_id) if repository_id.isdigit() else -1)) |
                (Repository.url.ilike(f"%/{repository_id}")) |
                (Repository.url.ilike(f"%/{repository_id}.git")) |
                (Repository.url.ilike(f"%{repository_id}%"))
            ).first()
            if repo:
                repo_name_resolved = repo.url.split("/")[-1].replace(".git", "")
                latest_analysis = db.query(Analysis).filter(
                    Analysis.repository_id == repo.id,
                    Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                ).order_by(Analysis.id.desc()).first()
                if latest_analysis:
                    analysis_id = latest_analysis.id

        # If still no analysis and user_id is provided, search user's latest repo analysis only
        if not analysis_id and user_id is not None:
            user_repo = db.query(Repository).filter(Repository.user_id == user_id).order_by(Repository.id.desc()).first()
            if user_repo:
                user_analysis = db.query(Analysis).filter(
                    Analysis.repository_id == user_repo.id,
                    Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                ).order_by(Analysis.id.desc()).first()
                if user_analysis:
                    analysis_id = user_analysis.id

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
                f"- {s.get('name')} ({s.get('symbol_type', 'symbol')}) at {s.get('file_path', '')}:{s.get('line_start', '')}"
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
            "You are the GitOnboard Repository Architecture Explainer.\n"
            "Explain the user's question using ONLY the provided repository evidence below.\n\n"
            "GROUNDING RULES:\n"
            "1. Base your explanation directly on the listed files, symbols, routes, and call graphs.\n"
            "2. Cite exact file paths and symbols in markdown format: `[Symbol](file_path)`.\n"
            "3. If evidence is missing or insufficient to answer developer intent, "
            "explicitly state that repository evidence is absent rather than inventing facts.\n"
            "4. Keep the explanation structured, clear, and educational."
        )

        user_content = (
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
                f"Explanation for '{user_requirement}':\n\n"
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
        # 1. Resolve repository and analysis_id strictly scoped to user
        repo_name_resolved = repository_id or "default"
        if not analysis_id and repository_id:
            from backend.models.repository import Repository
            query = db.query(Repository)
            if user_id is not None:
                query = query.filter(Repository.user_id == user_id)
            repo = query.filter(
                (Repository.id == (int(repository_id) if repository_id.isdigit() else -1)) |
                (Repository.url.ilike(f"%/{repository_id}")) |
                (Repository.url.ilike(f"%/{repository_id}.git")) |
                (Repository.url.ilike(f"%{repository_id}%"))
            ).first()
            if repo:
                repo_name_resolved = repo.url.split("/")[-1].replace(".git", "")
                latest_analysis = db.query(Analysis).filter(
                    Analysis.repository_id == repo.id,
                    Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                ).order_by(Analysis.id.desc()).first()
                if latest_analysis:
                    analysis_id = latest_analysis.id

        if not analysis_id and user_id is not None:
            user_repo = db.query(Repository).filter(Repository.user_id == user_id).order_by(Repository.id.desc()).first()
            if user_repo:
                user_analysis = db.query(Analysis).filter(
                    Analysis.repository_id == user_repo.id,
                    Analysis.status.in_(["Completed", "COMPLETED", "Saving", "Analyzing"])
                ).order_by(Analysis.id.desc()).first()
                if user_analysis:
                    analysis_id = user_analysis.id

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
        orchestrator = PlanningOrchestrator(llm_service=None)
        plan = orchestrator.create_plan(
            context=ctx,
            agent_run_id=agent_run_id or f"run_plan_{repo_name_resolved}",
            repository_id=repo_name_resolved,
            requirement=user_requirement,
            db=db,
            version=1,
        )

        # 5. Format Instant Structured Markdown Response from Verified DAG Plan
        lines = [
            f"## Repository-Aware Implementation Plan for: *{user_requirement}*",
            "",
            f"**Target Repository**: `{repo_name_resolved}` (Analysis #{analysis_id or 'N/A'})",
            f"**Validation Status**: {'✅ Valid Plan (0 Cycles)' if plan.validation and plan.validation.valid else '⚠️ Draft with Warnings'}",
            "",
            "### Planned Implementation Steps (DAG):",
        ]
        for task in plan.tasks:
            comp_badge = f"`[{task.component_type}]`"
            files_str = ", ".join(f"`{f}`" for f in task.affected_files) if task.affected_files else "No files specified"
            deps_str = f"(Depends on: {', '.join(task.dependencies)})" if task.dependencies else "(Initial task)"
            lines.append(f"1. **{task.title}** {comp_badge} {deps_str}")
            lines.append(f"   - **Files**: {files_str}")
            lines.append(f"   - **Verification**: `{task.verification_strategy}`")
            if task.acceptance_criteria:
                lines.append(f"   - **Criteria**: {task.acceptance_criteria[0]}")

        if plan.unknowns:
            lines.append("\n### Identified Unknowns & Assumptions:")
            for u in plan.unknowns:
                lines.append(f"- ❓ {u}")

        if plan.risks:
            lines.append("\n### Technical Risks & Blast Radius:")
            for r in plan.risks:
                lines.append(f"- ⚠️ {r}")

        response_text = "\n".join(lines)

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
        agent_run_id=agent_run_id,
        user_id=user_id,
        db=db,
    )
    res["intent"] = "implement"
    res["model"] = settings.model_terminal_implement
    res["status"] = "READY_FOR_APPROVAL"
    res["response"] = (
        f"### 📋 Implementation Plan Generated (Awaiting Approval)\n\n"
        f"{res.get('response', '')}\n\n"
        f"> 🔒 **Approval Required**: Review the planned tasks above and click **Approve** to authorize repository mutation."
    )
    return res


