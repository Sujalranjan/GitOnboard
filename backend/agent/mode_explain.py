"""
Safe Non-Mutating Explanation Mode Handler (Phase 3).
Executes repository-grounded natural-language explanation using ContextAssembler and bounded evidence.
Extracted from backend.agent.modes to maintain modularity.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import ContextAssemblyRequest, ContextBudget
from backend.agent.context.rim_guidance import get_rim_guidance_for_system_prompt
from backend.ai.schemas import LLMRequest, Message, MessageRole
from backend.ai.service import LLMService, build_default_service
from backend.config import settings
from backend.database import SessionLocal
from backend.intelligence.retrieval.source_reader import RepositorySourceReader
from backend.models.fact_store import FactFile

logger = logging.getLogger(__name__)


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
    from backend.agent.modes import resolve_target_repository_and_analysis, resolve_worktree_path

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

        # Check if prompt mentions a directory/module
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

        # 2. Read actual source code for target files
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
