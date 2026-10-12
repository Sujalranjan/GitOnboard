"""
Repository Intelligence Tools for LLM Agents (/api/v1/agent/repository-tools).
Allows agents to query source files, symbol graphs, and symbol explanations.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.models.user import User
from backend.routers.agent_schemas import (
    ExplainSymbolRequest,
    FileContentRequest,
    FileContentResponse,
    SymbolExplanation,
    SymbolGraphEdge,
    SymbolGraphNode,
    SymbolGraphQueryRequest,
    SymbolGraphQueryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Engineering Agent Tools"])


@router.post("/repository-tools/read-file", response_model=FileContentResponse)
def agent_read_file(
    req: FileContentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileContentResponse:
    """Read file content from repository (Agent version of Tool #2)."""
    from backend.routers.repo.services.hash_resolution import get_latest_analysis_by_hash
    from backend.models.fact_store import FactFile
    from backend.storage import get_storage
    from backend.utils.repo_paths import normalize_relative, PathTraversalError

    try:
        repo, analysis = get_latest_analysis_by_hash(req.repo_hash, db, current_user)

        try:
            clean_path = normalize_relative(req.file_path)
        except PathTraversalError:
            raise HTTPException(status_code=400, detail=f"Invalid path: {req.file_path}")

        fact_file = db.query(FactFile).filter(
            FactFile.analysis_id == analysis.id,
            FactFile.path == clean_path,
        ).first()

        if not fact_file:
            raise HTTPException(status_code=404, detail=f"File not found: {clean_path}")

        if not fact_file.blob_name:
            raise HTTPException(status_code=500, detail="File content unavailable")

        storage = get_storage()
        full_content = storage.get_object_text(fact_file.blob_name)

        if not full_content:
            raise HTTPException(status_code=500, detail="Failed to read file content")

        lines = full_content.split("\n")
        total_lines = len(lines)

        start = (req.start_line - 1) if req.start_line else 0
        end = req.end_line if req.end_line else total_lines

        if start < 0 or start >= total_lines:
            raise HTTPException(status_code=400, detail=f"Invalid start_line: {req.start_line}")
        if end < start or end > total_lines:
            raise HTTPException(status_code=400, detail=f"Invalid end_line: {req.end_line}")

        content = "\n".join(lines[start:end])

        return FileContentResponse(
            file_path=clean_path,
            content=content,
            total_lines=total_lines,
            returned_lines=end - start,
            start_line=req.start_line,
            end_line=req.end_line,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/repository-tools/query-graph", response_model=SymbolGraphQueryResponse)
def agent_query_symbol_graph(
    req: SymbolGraphQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SymbolGraphQueryResponse:
    """Query symbol relationships (Agent version of Tool #3)."""
    from backend.routers.repo.services.hash_resolution import get_latest_analysis_by_hash
    from backend.models.fact_store import FactFile, FactRelationship, FactSymbol

    try:
        repo, analysis = get_latest_analysis_by_hash(req.repo_hash, db, current_user)

        center_sym = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            FactSymbol.id == req.symbol_id,
        ).first()

        if not center_sym:
            raise HTTPException(status_code=404, detail=f"Symbol not found: {req.symbol_id}")

        nodes = {}
        edges = []

        file_obj = db.query(FactFile).filter(FactFile.id == center_sym.file_id).first()
        nodes[center_sym.id] = SymbolGraphNode(
            symbol_id=center_sym.id,
            name=center_sym.name,
            symbol_type=center_sym.symbol_type,
            file_path=file_obj.path if file_obj else "",
        )

        if req.direction in ["outgoing", "both"]:
            outgoing = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis.id,
                FactRelationship.from_symbol_id == center_sym.id,
            ).limit(50).all()

            for rel in outgoing:
                to_sym = db.query(FactSymbol).filter(FactSymbol.id == rel.to_symbol_id).first()
                if to_sym:
                    file_obj = db.query(FactFile).filter(FactFile.id == to_sym.file_id).first()
                    if rel.to_symbol_id not in nodes:
                        nodes[rel.to_symbol_id] = SymbolGraphNode(
                            symbol_id=to_sym.id,
                            name=to_sym.name,
                            symbol_type=to_sym.symbol_type,
                            file_path=file_obj.path if file_obj else "",
                        )
                    edges.append(SymbolGraphEdge(
                        from_id=center_sym.id,
                        to_id=rel.to_symbol_id,
                        rel_type=rel.rel_type,
                    ))

        if req.direction in ["incoming", "both"]:
            incoming = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis.id,
                FactRelationship.to_symbol_id == center_sym.id,
            ).limit(50).all()

            for rel in incoming:
                from_sym = db.query(FactSymbol).filter(FactSymbol.id == rel.from_symbol_id).first()
                if from_sym:
                    file_obj = db.query(FactFile).filter(FactFile.id == from_sym.file_id).first()
                    if rel.from_symbol_id not in nodes:
                        nodes[rel.from_symbol_id] = SymbolGraphNode(
                            symbol_id=from_sym.id,
                            name=from_sym.name,
                            symbol_type=from_sym.symbol_type,
                            file_path=file_obj.path if file_obj else "",
                        )
                    edges.append(SymbolGraphEdge(
                        from_id=rel.from_symbol_id,
                        to_id=center_sym.id,
                        rel_type=rel.rel_type,
                    ))

        return SymbolGraphQueryResponse(
            nodes=list(nodes.values()),
            edges=edges,
            center_symbol=center_sym.name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/repository-tools/explain-symbol", response_model=SymbolExplanation)
def agent_explain_symbol(
    req: ExplainSymbolRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SymbolExplanation:
    """Explain a symbol (Agent version of Tool #4)."""
    from backend.routers.repo.services.hash_resolution import get_latest_analysis_by_hash
    from backend.models.fact_store import FactFile, FactSymbol

    try:
        repo, analysis = get_latest_analysis_by_hash(req.repo_hash, db, current_user)

        sym = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            FactSymbol.id == req.symbol_id,
        ).first()

        if not sym:
            raise HTTPException(status_code=404, detail=f"Symbol not found: {req.symbol_id}")

        file_obj = db.query(FactFile).filter(FactFile.id == sym.file_id).first()
        file_path = file_obj.path if file_obj else ""

        meta = dict(sym.metadata_json or {})
        cached_exp = meta.get("ai_explanation")

        explanation = None
        cached = False

        if cached_exp:
            explanation = cached_exp.get("summary")
            cached = True
        else:
            explanation = meta.get("signature") or f"{sym.symbol_type} {sym.name}"

        return SymbolExplanation(
            symbol_id=sym.id,
            name=sym.name,
            symbol_type=sym.symbol_type,
            file_path=file_path,
            explanation=explanation,
            cached=cached,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error explaining symbol: {e}")
        raise HTTPException(status_code=500, detail=str(e))
