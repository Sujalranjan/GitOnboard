import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.models.fact_store import (
    FactSymbol,
    FactFile,
    FactRelationship,
    FactRoute,
    FactDatabaseObject,
)
from backend.routers.repo.services.analysis import get_latest_analysis
from backend.storage import get_storage
from backend.ai.service import get_llm_service, LLMService
from backend.ai.schemas import LLMRequest, Message, MessageRole
from backend.ai.prompts.symbol_explain import (
    SYMBOL_EXPLAIN_SYSTEM_PROMPT,
    SYMBOL_EXPLAIN_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

symbols_router = APIRouter(tags=["symbols"])


class ExplainSymbolRequest(BaseModel):
    symbol_id: Optional[str] = Field(default=None, description="FactSymbol ID (e.g. {analysis_id}:{entity_id})")
    name: Optional[str] = Field(default=None, description="Symbol, function, or route name")
    file_path: Optional[str] = Field(default=None, description="Repository relative file path")
    match_type: Optional[str] = Field(default=None, description="Symbol type (function, class, method, route, database_table)")
    regenerate: bool = Field(default=False, description="Force LLM re-generation bypassing cache")


class ExplainSymbolResponse(BaseModel):
    symbol_id: str
    name: str
    symbol_type: str
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    signature: Optional[str] = None
    explanation: str
    cached: bool
    generated_at: str
    signature_hash: str
    outgoing_calls: List[str] = Field(default_factory=list)
    incoming_calls: List[str] = Field(default_factory=list)
    routes: List[str] = Field(default_factory=list)
    database_ops: List[str] = Field(default_factory=list)


def _compute_symbol_hash(sym: FactSymbol, fpath: str, snippet: str) -> str:
    """Computes a stable hash of the symbol's identity, signature, and source code snippet."""
    if sym.signature_hash:
        return sym.signature_hash
    hasher = hashlib.sha256()
    hasher.update(f"{sym.id}:{sym.name}:{sym.symbol_type}:{fpath}:{sym.line_start}:{sym.line_end}".encode("utf-8"))
    if snippet:
        hasher.update(snippet.encode("utf-8"))
    return hasher.hexdigest()[:16]


def _resolve_symbol_file_path(sym: FactSymbol, explicit_path: Optional[str] = None) -> str:
    """Extracts file path from explicit request, FactSymbol relationship, file_id, or URN ID."""
    if explicit_path and explicit_path.strip():
        return explicit_path.strip()
    if sym.file and sym.file.path:
        return sym.file.path
    if sym.file_id:
        clean = sym.file_id.split(":", 1)[-1] if ":" in sym.file_id else sym.file_id
        if "." in clean and "/" in clean:
            return clean
    if sym.id and "urn:" in sym.id:
        try:
            urn_body = sym.id.split("urn:", 1)[1]
            parts = urn_body.split(":", 1)
            if len(parts) == 2:
                path_part = parts[1].split("#", 1)[0]
                if "." in path_part:
                    return path_part
        except Exception:
            pass
    if sym.metadata_json and isinstance(sym.metadata_json, dict):
        if sym.metadata_json.get("file_path"):
            return sym.metadata_json["file_path"]
        if sym.metadata_json.get("path"):
            return sym.metadata_json["path"]
    return ""


def _extract_block_from_text(lines: List[str], line_start: Optional[int], line_end: Optional[int], sym_name: str) -> str:
    """Extracts the full multi-line implementation block for a symbol using brace tracking."""
    total = len(lines)
    if total == 0:
        return ""

    start_idx = None
    if line_start and 1 <= line_start <= total:
        start_idx = line_start - 1
    else:
        clean_name = sym_name.rstrip("()")
        for idx, line in enumerate(lines):
            if clean_name in line and any(kw in line for kw in ["function", "def ", "class ", "const ", "let ", "var ", "export ", "async "]):
                start_idx = idx
                break

    if start_idx is None:
        return ""

    # If line_end is given and spans multiple lines (> 2 lines difference), use it
    if line_end and line_end > (start_idx + 2) and line_end <= total:
        return "\n".join(lines[start_idx:line_end]).strip()

    # Otherwise (e.g. line_start == line_end == 74), scan forward to find the complete block
    brace_count = 0
    found_open_brace = False
    extracted_lines = []

    for i in range(start_idx, min(total, start_idx + 150)):
        line = lines[i]
        extracted_lines.append(line)

        for char in line:
            if char == "{":
                brace_count += 1
                found_open_brace = True
            elif char == "}":
                brace_count -= 1

        if found_open_brace and brace_count <= 0:
            break

    if not found_open_brace or brace_count > 0:
        extracted_lines = lines[start_idx : min(total, start_idx + 80)]

    return "\n".join(extracted_lines).strip()


async def _extract_source_snippet(
    sym: FactSymbol,
    fact_file: Optional[FactFile],
    repo: Any,
    repo_name: str,
    current_user: User,
    db: Session,
    analysis_id: int
) -> Tuple[str, str]:
    """
    Reads the full source implementation for the symbol using multi-source fallbacks:
    1. Resolves file path from FactSymbol / URN
    2. Azure Blob Storage (via FactFile.blob_name)
    3. Local workspace / worktree directories
    4. GitHub API (if token available)
    5. Extracts complete multi-line block
    Returns: (source_snippet, resolved_file_path)
    """
    meta = sym.metadata_json or {}
    fpath = _resolve_symbol_file_path(sym, fact_file.path if fact_file else None)

    if not fact_file:
        fact_file = db.query(FactFile).filter(
            FactFile.analysis_id == analysis_id,
            (FactFile.path == fpath) | (FactFile.id == sym.file_id) | (FactFile.id == f"{analysis_id}:{fpath}")
        ).first()

    if not fact_file and fpath:
        fact_file = db.query(FactFile).filter(
            FactFile.analysis_id == analysis_id,
            FactFile.path.endswith(fpath)
        ).first()

    if fact_file and not fpath:
        fpath = fact_file.path

    full_text = None

    # Priority 1: Fetch from Azure / Azurite Blob Storage
    if fact_file and fact_file.blob_name:
        try:
            storage = get_storage()
            full_text = storage.get_object_text(fact_file.blob_name)
        except Exception as e:
            logger.debug(f"Failed to read blob {fact_file.blob_name}: {e}")

    # Priority 2: Local filesystem cache / worktrees
    if not full_text and fpath:
        from backend.config import settings
        from pathlib import Path
        candidate_paths = [
            Path("data/repos") / repo_name / fpath,
            Path(settings.worktrees_dir) / f"{repo_name}_{analysis_id}" / fpath,
            Path(settings.worktrees_dir) / repo_name / fpath,
            Path("/tmp/repo-analysis") / repo_name / fpath,
        ]
        for cp in candidate_paths:
            if cp.exists() and cp.is_file():
                try:
                    full_text = cp.read_text(encoding="utf-8", errors="replace")
                    if full_text:
                        break
                except Exception:
                    pass

    # Priority 3: GitHub API fallback
    if not full_text and current_user.github_access_token and getattr(repo, "url", None) and fpath:
        try:
            from backend.services.github import fetch_file_content
            parts = repo.url.rstrip("/").split("/")
            if len(parts) >= 2:
                owner = parts[-2]
                full_text = await fetch_file_content(
                    owner, repo_name, getattr(repo, "default_branch", "main") or "main", fpath, current_user.github_access_token
                )
        except Exception as gh_err:
            logger.debug(f"GitHub fallback read failed for {fpath}: {gh_err}")

    # If full text was loaded, extract the actual function / class body
    if full_text:
        lines = full_text.splitlines()
        block = _extract_block_from_text(lines, sym.line_start, sym.line_end, sym.name)
        if len(block) > 10:
            return block, fpath

    # Priority 4: Metadata snippet / source segment (only if substantial)
    raw_snippet = meta.get("snippet") or meta.get("source_segment") or ""
    if raw_snippet and len(raw_snippet.strip()) > 30 and "\n" in raw_snippet:
        return raw_snippet.strip(), fpath

    fallback_code = meta.get("signature") or f"{sym.symbol_type} {sym.name}"
    return fallback_code, fpath


@symbols_router.post("/{repo_name}/symbols/explain", response_model=ExplainSymbolResponse)
async def explain_symbol(
    repo_name: str,
    req: ExplainSymbolRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm: LLMService = Depends(get_llm_service),
) -> ExplainSymbolResponse:
    """
    Explains what a function/class/route/database object does and how it works.
    - Caches the explanation in FactSymbol.metadata_json["ai_explanation"].
    - Validates signature/content hashes to automatically detect stale explanations.
    - Bypasses cache when regenerate=True.
    """
    repo, analysis = get_latest_analysis(repo_name, db, current_user)

    # 1. Resolve Target Symbol
    sym: Optional[FactSymbol] = None
    target_id = req.symbol_id

    # 1a. Try lookup by direct Symbol ID
    if target_id and ":" in target_id:
        sym = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            FactSymbol.id == target_id
        ).first()

    # 1b. If match_type is route or target_id matches route pattern, resolve handler
    if not sym and (req.match_type == "route" or (req.name and ("/" in req.name or "GET " in req.name or "POST " in req.name))):
        clean_path = req.name or ""
        for prefix in ["GET ", "POST ", "PUT ", "DELETE ", "PATCH "]:
            if clean_path.startswith(prefix):
                clean_path = clean_path[len(prefix):].strip()
        route = db.query(FactRoute).filter(
            FactRoute.analysis_id == analysis.id,
            (FactRoute.path == clean_path) | (FactRoute.path.ilike(f"%{clean_path}%")) | (FactRoute.id == target_id)
        ).first()
        if route:
            handler_id = route.handler_symbol_id or route.symbol_id
            if handler_id:
                sym = db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == analysis.id,
                    FactSymbol.id == handler_id
                ).first()

    # 1c. If match_type is database_table, resolve table symbol
    if not sym and (req.match_type == "database_table" or req.match_type == "table"):
        db_obj = db.query(FactDatabaseObject).filter(
            FactDatabaseObject.analysis_id == analysis.id,
            (FactDatabaseObject.name == req.name) | (FactDatabaseObject.id == target_id)
        ).first()
        if db_obj and db_obj.symbol_id:
            sym = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis.id,
                FactSymbol.id == db_obj.symbol_id
            ).first()

    # 1d. Fallback: Search by name and file_path
    if not sym and req.name:
        query = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis.id)
        if req.file_path:
            query = query.join(FactFile).filter(FactFile.path == req.file_path)
        sym = query.filter(
            (FactSymbol.name == req.name) | (FactSymbol.qualified_name == req.name)
        ).first()

    # 1e. Final Fallback: Name-only match across analysis
    if not sym and req.name:
        clean_name = req.name.rstrip("()")
        sym = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            (FactSymbol.name == clean_name) | (FactSymbol.qualified_name.ilike(f"%{clean_name}%"))
        ).first()

    if not sym:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{req.name or req.symbol_id}' not found in analyzed repository."
        )

    source_snippet, resolved_fpath = await _extract_source_snippet(sym, sym.file, repo, repo_name, current_user, db, analysis.id)
    fpath = resolved_fpath or (sym.file.path if sym.file else (req.file_path or ""))
    current_hash = _compute_symbol_hash(sym, fpath, source_snippet)

    # 2. Check Cache
    sym_meta = dict(sym.metadata_json or {})
    cached_exp = sym_meta.get("ai_explanation")

    if cached_exp and not req.regenerate:
        cached_hash = cached_exp.get("signature_hash")
        # If hash matches, return immediately from cache (0 latency, 0 LLM cost)
        if cached_hash == current_hash:
            logger.info(f"Symbol explanation cache HIT for {sym.name} ({sym.id})")
            return ExplainSymbolResponse(
                symbol_id=sym.id,
                name=sym.name,
                symbol_type=sym.symbol_type,
                file_path=fpath,
                line_start=sym.line_start,
                line_end=sym.line_end,
                signature=sym_meta.get("signature"),
                explanation=cached_exp.get("summary", ""),
                cached=True,
                generated_at=cached_exp.get("generated_at", ""),
                signature_hash=current_hash,
                outgoing_calls=cached_exp.get("outgoing_calls", []),
                incoming_calls=cached_exp.get("incoming_calls", []),
                routes=cached_exp.get("routes", []),
                database_ops=cached_exp.get("database_ops", []),
            )

    logger.info(f"Symbol explanation cache MISS/REGENERATE for {sym.name} ({sym.id}). Calling LLM...")

    # 3. Extract Focused Relational Fact Store Context
    # 3a. Outgoing calls (callees)
    outgoing_rels = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis.id,
        FactRelationship.from_symbol_id == sym.id,
        FactRelationship.rel_type == "CALLS"
    ).limit(10).all()
    outgoing_calls = []
    for r in outgoing_rels:
        target_sym = db.query(FactSymbol).filter(FactSymbol.id == r.to_symbol_id).first()
        if target_sym:
            outgoing_calls.append(f"{target_sym.name}() ({target_sym.file.path if target_sym.file else ''})")
        elif r.evidence_snippet:
            outgoing_calls.append(r.evidence_snippet)

    # 3b. Incoming callers
    incoming_rels = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis.id,
        FactRelationship.to_symbol_id == sym.id,
        FactRelationship.rel_type == "CALLS"
    ).limit(10).all()
    incoming_calls = []
    for r in incoming_rels:
        caller_sym = db.query(FactSymbol).filter(FactSymbol.id == r.from_symbol_id).first()
        if caller_sym:
            incoming_calls.append(f"{caller_sym.name}() ({caller_sym.file.path if caller_sym.file else ''})")

    # 3c. Attached Routes
    routes_found = db.query(FactRoute).filter(
        FactRoute.analysis_id == analysis.id,
        (FactRoute.symbol_id == sym.id) | (FactRoute.handler_symbol_id == sym.id)
    ).all()
    associated_routes = [f"{rt.method} {rt.path}" for rt in routes_found]

    # 3d. Database Objects
    db_objs = db.query(FactDatabaseObject).filter(
        FactDatabaseObject.analysis_id == analysis.id,
        FactDatabaseObject.symbol_id == sym.id
    ).all()
    database_ops = [f"{d.object_type}: {d.name}" for d in db_objs]

    # Detect language from file path
    ext = fpath.rsplit(".", 1)[-1].lower() if "." in fpath else "typescript"
    lang_map = {"ts": "typescript", "tsx": "tsx", "js": "javascript", "jsx": "jsx", "py": "python", "go": "go", "rs": "rust", "java": "java"}
    code_lang = lang_map.get(ext, "typescript")

    # 4. Construct Prompt & Call LLM
    line_range_str = f"L{sym.line_start}-L{sym.line_end}" if sym.line_start and sym.line_end else "Unknown"
    user_prompt = SYMBOL_EXPLAIN_USER_TEMPLATE.format(
        symbol_name=sym.name,
        symbol_type=sym.symbol_type,
        file_path=fpath or "Unknown",
        line_range=line_range_str,
        signature=sym_meta.get("signature") or sym.name,
        outgoing_calls=", ".join(outgoing_calls) if outgoing_calls else "None detected",
        incoming_calls=", ".join(incoming_calls) if incoming_calls else "None detected",
        associated_routes=", ".join(associated_routes) if associated_routes else "None",
        database_ops=", ".join(database_ops) if database_ops else "None",
        language=code_lang,
        source_code=source_snippet[:3500],  # Bounded window to prevent token overflow
    )

    llm_req = LLMRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content=SYMBOL_EXPLAIN_SYSTEM_PROMPT),
            Message(role=MessageRole.USER, content=user_prompt),
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    logger.info("=" * 80)
    logger.info("[SYMBOL EXPLAIN DEBUG]")
    logger.info(f"  symbol name: {sym.name}")
    logger.info(f"  symbol_id: {sym.id}")
    logger.info(f"  symbol type: {sym.symbol_type}")
    logger.info(f"  file path: {fpath}")
    logger.info(f"  line_start: {sym.line_start}")
    logger.info(f"  line_end: {sym.line_end}")
    logger.info(f"  length of source_snippet: {len(source_snippet)}")
    logger.info(f"  first 2000 characters of source_snippet:\n{source_snippet[:2000]}")
    logger.info("=" * 80)

    try:
        llm_resp = await llm.generate(llm_req)
        explanation_content = llm_resp.content.strip()
    except Exception as e:
        logger.error(f"LLM symbol explanation generation failed: {e}", exc_info=True)
        explanation_content = (
            f"### 1. What it does\n`{sym.name}` is a {sym.symbol_type} located in `{fpath}`.\n\n"
            f"### 2. How it works\nExecutes lines {line_range_str}.\n\n"
            f"### 3. Inputs & Outputs\nSignature: `{sym_meta.get('signature', sym.name)}`\n\n"
            f"### 4. Key Dependencies & Calls\nCalls: {', '.join(outgoing_calls) if outgoing_calls else 'None observed'}\n\n"
            f"### 5. Side Effects & State Changes\n{', '.join(database_ops) if database_ops else 'None observed'}"
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    # 5. Persist to Fact Store Cache
    sym_meta["ai_explanation"] = {
        "summary": explanation_content,
        "signature_hash": current_hash,
        "generated_at": now_iso,
        "outgoing_calls": outgoing_calls,
        "incoming_calls": incoming_calls,
        "routes": associated_routes,
        "database_ops": database_ops,
    }
    sym.metadata_json = sym_meta
    flag_modified(sym, "metadata_json")
    db.commit()

    return ExplainSymbolResponse(
        symbol_id=sym.id,
        name=sym.name,
        symbol_type=sym.symbol_type,
        file_path=fpath,
        line_start=sym.line_start,
        line_end=sym.line_end,
        signature=sym_meta.get("signature"),
        explanation=explanation_content,
        cached=False,
        generated_at=now_iso,
        signature_hash=current_hash,
        outgoing_calls=outgoing_calls,
        incoming_calls=incoming_calls,
        routes=associated_routes,
        database_ops=database_ops,
    )
