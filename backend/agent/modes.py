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
# Re-export modular mode handlers
from backend.agent.mode_explore import execute_explore  # noqa: F401
from backend.agent.mode_explain import execute_explain  # noqa: F401

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
        if agent_run_id:
            from backend.models.implementation import AgentRun
            agent_run = db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
            if agent_run:
                from backend.agent.engineering_agent import EngineeringAgent
                eng_agent = EngineeringAgent()
                repo_revision = eng_agent.get_repository_revision(agent_run.repository_id, agent_run.worktree_path)
        elif repo_name_resolved:
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


