"""
Symbol and call-graph query operations for RepositoryToolLayer.
Extracted from backend.repository_tools.tools to maintain modularity.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models.fact_store import FactFile, FactRelationship, FactSymbol

logger = logging.getLogger(__name__)


def get_symbol_ops(
    db: Optional[Session],
    analysis_id: Optional[int],
    name: str,
) -> List[Dict[str, Any]]:
    """Looks up symbol definitions (functions, classes, methods) in the Fact Store."""
    if not db or not analysis_id:
        return []

    symbols = (
        db.query(FactSymbol, FactFile.path)
        .join(FactFile, FactSymbol.file_id == FactFile.id)
        .filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.name.ilike(f"%{name}%"),
        )
        .limit(20)
        .all()
    )

    return [
        {
            "symbol_id": sym.id,
            "name": sym.name,
            "qualified_name": sym.qualified_name,
            "symbol_type": sym.symbol_type,
            "file": path,
            "line_start": sym.line_start,
            "line_end": sym.line_end,
        }
        for sym, path in symbols
    ]


def get_file_outline_ops(
    db: Optional[Session],
    analysis_id: Optional[int],
    path: str,
) -> Dict[str, Any]:
    """Returns an outline of symbols (classes, functions, routes) in a file."""
    if not db or not analysis_id:
        return {"file": path, "symbols": []}

    symbols = (
        db.query(FactSymbol)
        .join(FactFile, FactSymbol.file_id == FactFile.id)
        .filter(
            FactSymbol.analysis_id == analysis_id,
            FactFile.path == path,
        )
        .order_by(FactSymbol.line_start)
        .all()
    )

    return {
        "file": path,
        "symbols": [
            {
                "name": sym.name,
                "type": sym.symbol_type,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
            }
            for sym in symbols
        ],
    }


def get_callers_ops(
    db: Optional[Session],
    analysis_id: Optional[int],
    symbol_name: str,
) -> List[Dict[str, Any]]:
    """Finds symbols that invoke or call the given symbol."""
    if not db or not analysis_id:
        return []

    target_symbol = (
        db.query(FactSymbol.id)
        .filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.name.ilike(f"%{symbol_name}%"),
        )
        .first()
    )

    if not target_symbol:
        return []

    target_id = target_symbol.id

    rel_rows = (
        db.query(FactRelationship, FactSymbol.name, FactSymbol.symbol_type)
        .join(FactSymbol, FactRelationship.from_symbol_id == FactSymbol.id)
        .filter(
            FactRelationship.analysis_id == analysis_id,
            FactRelationship.rel_type == "CALLS",
            FactRelationship.to_symbol_id == target_id,
        )
        .limit(20)
        .all()
    )

    results = []
    for rel, name, sym_type in rel_rows:
        item = {
            "caller_symbol": name,
            "symbol_type": sym_type,
            "relationship": rel.rel_type,
        }
        if rel.evidence_line is not None:
            item["evidence_line"] = rel.evidence_line
        if rel.evidence_snippet is not None:
            item["snippet"] = rel.evidence_snippet
        results.append(item)
    return results


def get_callees_ops(
    db: Optional[Session],
    analysis_id: Optional[int],
    symbol_name: str,
) -> List[Dict[str, Any]]:
    """Finds symbols that are called by the given symbol."""
    if not db or not analysis_id:
        return []

    source_symbol = (
        db.query(FactSymbol.id)
        .filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.name.ilike(f"%{symbol_name}%"),
        )
        .first()
    )

    if not source_symbol:
        return []

    source_id = source_symbol.id

    rel_rows = (
        db.query(FactRelationship, FactSymbol.name, FactSymbol.symbol_type)
        .join(FactSymbol, FactRelationship.to_symbol_id == FactSymbol.id)
        .filter(
            FactRelationship.analysis_id == analysis_id,
            FactRelationship.rel_type == "CALLS",
            FactRelationship.from_symbol_id == source_id,
        )
        .limit(20)
        .all()
    )

    results = []
    for rel, name, sym_type in rel_rows:
        item = {
            "callee_symbol": name,
            "symbol_type": sym_type,
            "relationship": rel.rel_type,
        }
        if rel.evidence_line is not None:
            item["evidence_line"] = rel.evidence_line
        if rel.evidence_snippet is not None:
            item["snippet"] = rel.evidence_snippet
        results.append(item)
    return results


def get_related_files_ops(
    db: Optional[Session],
    analysis_id: Optional[int],
    path: str,
) -> List[Dict[str, Any]]:
    """Finds files related via imports or function calls."""
    if not db or not analysis_id:
        return []

    file_syms = (
        db.query(FactSymbol.id)
        .join(FactFile, FactSymbol.file_id == FactFile.id)
        .filter(FactSymbol.analysis_id == analysis_id, FactFile.path == path)
        .all()
    )
    sym_ids = [s[0] for s in file_syms]
    if not sym_ids:
        return []

    related_rows = (
        db.query(FactRelationship, FactFile.path)
        .join(FactSymbol, FactRelationship.to_symbol_id == FactSymbol.id)
        .join(FactFile, FactSymbol.file_id == FactFile.id)
        .filter(
            FactRelationship.analysis_id == analysis_id,
            FactRelationship.from_symbol_id.in_(sym_ids),
            FactFile.path != path,
        )
        .limit(15)
        .all()
    )

    return [
        {
            "related_file": r_path,
            "rel_type": rel.rel_type,
            "evidence": rel.evidence_snippet,
        }
        for rel, r_path in related_rows
    ]
