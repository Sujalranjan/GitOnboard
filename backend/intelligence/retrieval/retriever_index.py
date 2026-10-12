"""
Index loading, document building, and artifact caching for HybridRetriever.
Handles BM25 and ChromaDB persistence and FactStore document indexing.
"""
from __future__ import annotations

import logging
import io
import re
import tempfile
import zipfile
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.intelligence.retrieval.lexical import BM25Index
from backend.models.fact_store import FactSymbol, FactFile, FactRoute, FactDatabaseObject

logger = logging.getLogger(__name__)


def extract_symbol_file_path(sym: Optional[FactSymbol]) -> str:
    if not sym:
        return ""
    if sym.file and sym.file.path:
        return sym.file.path
    if sym.id:
        match = re.search(r":urn:[^:]+:(.+?)#", sym.id)
        if match:
            return match.group(1)
    return ""


def build_factstore_documents(db: Session, analysis_id: int) -> List[Dict[str, Any]]:
    """Constructs in-memory indexable documents from FactStore tables."""
    docs: List[Dict[str, Any]] = []

    # 1. Index Files
    files = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).all()
    for f in files:
        search_text = f"file path {f.path} {f.language or ''} {f.content_type or ''}"
        docs.append({
            "id": f.id,
            "analysis_id": analysis_id,
            "name": f.path,
            "qualified_name": f.path,
            "type": "file",
            "file_path": f.path,
            "search_text": search_text,
            "line_start": 1,
            "line_end": 1,
            "match_type": "file",
            "match_name": f.path,
        })

    # 2. Index Symbols
    symbols = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis_id).all()
    for sym in symbols:
        fpath = extract_symbol_file_path(sym)
        meta = sym.metadata_json or {}
        docstring = meta.get("docstring", "")
        signature = meta.get("signature", "")

        search_text = f"{sym.name} {sym.qualified_name or ''} {sym.symbol_type} {fpath} {signature} {docstring}"
        docs.append({
            "id": sym.id,
            "analysis_id": analysis_id,
            "symbol_id": sym.id,
            "name": sym.name,
            "qualified_name": sym.qualified_name or sym.name,
            "type": sym.symbol_type,
            "file_path": fpath,
            "search_text": search_text,
            "line_start": sym.line_start,
            "line_end": sym.line_end,
            "match_type": sym.symbol_type,
            "match_name": sym.name,
        })

    # 3. Index Routes
    routes = db.query(FactRoute).filter(FactRoute.analysis_id == analysis_id).all()
    for r in routes:
        handler_id = r.handler_symbol_id or r.symbol_id
        fpath = ""
        l_start = None
        l_end = None
        if handler_id:
            sym = db.query(FactSymbol).filter(FactSymbol.id == handler_id).first()
            if sym:
                fpath = extract_symbol_file_path(sym)
                l_start = sym.line_start
                l_end = sym.line_end
        search_text = f"route {r.method} {r.path} {fpath}"
        docs.append({
            "id": r.id,
            "analysis_id": analysis_id,
            "name": f"{r.method} {r.path}",
            "qualified_name": f"{r.method} {r.path}",
            "type": "route",
            "file_path": fpath,
            "search_text": search_text,
            "match_type": "route",
            "match_name": f"{r.method} {r.path}",
            "symbol_id": handler_id or r.symbol_id or r.id,
            "line_start": l_start,
            "line_end": l_end,
        })

    # 4. Index DB Objects
    db_objs = db.query(FactDatabaseObject).filter(FactDatabaseObject.analysis_id == analysis_id).all()
    for d in db_objs:
        fpath = ""
        l_start = None
        l_end = None
        if d.symbol_id:
            sym = db.query(FactSymbol).filter(FactSymbol.id == d.symbol_id).first()
            if sym:
                fpath = extract_symbol_file_path(sym)
                l_start = sym.line_start
                l_end = sym.line_end
        search_text = f"database table {d.name} {d.object_type} {fpath}"
        docs.append({
            "id": d.id,
            "analysis_id": analysis_id,
            "name": d.name,
            "qualified_name": d.name,
            "type": "database_table",
            "file_path": fpath,
            "search_text": search_text,
            "match_type": "database_table",
            "match_name": d.name,
            "symbol_id": d.symbol_id or d.id,
            "line_start": l_start,
            "line_end": l_end,
        })

    return docs


def load_semantic_collection_from_artifact(db: Session, analysis_id: int):
    """
    Loads Chroma collection from analysis artifact.
    Returns (collection, degradation_reason).
    """
    try:
        from backend.models.repository import AnalysisArtifact
        artifact = db.query(AnalysisArtifact).filter(
            AnalysisArtifact.analysis_id == analysis_id,
            AnalysisArtifact.type == "semantic_index_db"
        ).first()

        if not artifact:
            return None, "artifact_not_found"

        if not artifact.blob_data:
            return None, "artifact_empty"

        try:
            import chromadb

            temp_dir = tempfile.mkdtemp(prefix="chroma_load_")
            try:
                with zipfile.ZipFile(io.BytesIO(artifact.blob_data)) as zf:
                    zf.extractall(temp_dir)

                client = chromadb.PersistentClient(path=temp_dir)
                collection = client.get_collection(name="semantic_index")
                return collection, None
            except Exception as e:
                return None, f"load_error: {str(e)[:50]}"

        except ImportError:
            return None, "chromadb_unavailable"

    except Exception as e:
        return None, f"artifact_load_error: {str(e)[:50]}"
