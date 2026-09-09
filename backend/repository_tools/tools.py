"""
Repository Tool Layer - Clean internal repository tool interface.
Safe, repository-scoped inspection and hybrid retrieval.
"""
from __future__ import annotations
import fnmatch
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.models.fact_store import (
    FactFile,
    FactSymbol,
    FactRelationship,
    FactRoute,
)
from backend.models.repository import Repository, Analysis
from backend.intelligence.retrieval.retriever import HybridRetriever
from .security import (
    RepositorySecurityError,
    validate_repo_path,
    clamp_line_range,
    MAX_SEARCH_RESULTS,
    is_binary_file,
)
from .resolver import resolve_repo_root

logger = logging.getLogger(__name__)


class RepositoryToolLayer:
    """
    Safe repository inspection and search interface scoped to a specific repository snapshot.
    Combines relational Fact Store queries with direct snapshot filesystem access.
    """

    def __init__(
        self,
        repo_name: str,
        analysis_id: Optional[int] = None,
        db: Optional[Session] = None,
        repo_root: Optional[Path | str] = None,
        user_id: Optional[int] = None,
    ):
        self.repo_name = repo_name
        self.analysis_id = analysis_id
        self.db = db
        self.user_id = user_id
        self._retriever: Optional[HybridRetriever] = None  # lazily constructed on first search

        # Resolve repo root directory
        self.repo_root = resolve_repo_root(
            repo_name=repo_name,
            user_id=user_id,
            db=db,
            custom_root=repo_root,
        )

        # Resolve latest analysis_id if not explicitly provided
        if self.analysis_id is None and self.db is not None and repo_name and repo_name != "default":
            from backend.agent.modes import resolve_target_repository_and_analysis
            _, resolved_analysis_id, _ = resolve_target_repository_and_analysis(self.db, repo_name, user_id)
            if resolved_analysis_id:
                self.analysis_id = resolved_analysis_id

    # ──────────────────────────────────────────────────────────────────────────
    # 1. read_file
    # ──────────────────────────────────────────────────────────────────────────

    def read_file(
        self,
        path: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Reads a slice of a file from Azure Blob Storage.
        Worktrees are temporary and deleted after indexing.
        All persistent file content is stored in blob storage.
        """
        clean_path = path.replace("\\", "/").removeprefix("./").lstrip("/")

        # Azure Blob Storage (source of truth for all persistent file content)
        if self.db is not None and self.analysis_id is not None:
            fact_file = (
                self.db.query(FactFile)
                .filter(
                    FactFile.analysis_id == self.analysis_id,
                    FactFile.path == clean_path,
                )
                .first()
            )
            if fact_file and fact_file.blob_name:
                try:
                    from backend.storage import get_storage
                    storage = get_storage()
                    raw_text = storage.get_object_text(fact_file.blob_name)
                    lines = raw_text.splitlines(keepends=True)
                    total_lines = len(lines)
                    s, e = clamp_line_range(total_lines, start_line, end_line)
                    selected_lines = lines[s - 1 : e]
                    numbered_content = "".join(f"{s + idx:4d} | {line}" for idx, line in enumerate(selected_lines))
                    return {
                        "path": clean_path,
                        "start_line": s,
                        "end_line": e,
                        "total_lines": total_lines,
                        "content": numbered_content,
                        "raw_text": "".join(selected_lines),
                    }
                except Exception as err:
                    logger.warning(f"Error reading blob {fact_file.blob_name}: {err}")

        raise RepositorySecurityError(
            f"File not found in Blob Storage: '{path}'. "
            f"Ensure indexing captured this file and stored it in Azure Blob Storage."
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 2. find_files
    # ──────────────────────────────────────────────────────────────────────────

    def find_files(self, pattern: str = "*", limit: int = 50) -> List[Dict[str, Any]]:
        """
        Finds files in the repository matching a glob pattern (e.g. '*.py', 'docs/**/*.md').
        Uses Fact Store database manifest (metadata from indexing).
        Worktrees are temporary and deleted after indexing; all metadata is in the database.
        """
        results: List[Dict[str, Any]] = []

        if self.db is not None and self.analysis_id is not None:
            query = self.db.query(FactFile).filter(FactFile.analysis_id == self.analysis_id)
            files = query.all()
            for f in files:
                if fnmatch.fnmatch(f.path, pattern) or fnmatch.fnmatch(os.path.basename(f.path), pattern):
                    results.append({
                        "path": f.path,
                        "language": f.language,
                        "size": f.size,
                        "is_documentation": f.is_documentation,
                        "is_agent_instruction": f.is_agent_instruction,
                        "is_test": f.is_test,
                        "is_binary": f.is_binary,
                    })
                    if len(results) >= limit:
                        break

        return results

    # ──────────────────────────────────────────────────────────────────────────
    # 3. search_code (Lexical Search)
    # ──────────────────────────────────────────────────────────────────────────

    def search_code(
        self,
        query: str,
        file_pattern: Optional[str] = None,
        max_matches: int = 25,
        max_files_scanned: int = 40,
    ) -> List[Dict[str, Any]]:
        """
        Performs lexical regex/substring search over source files in Azure Blob Storage.
        Worktrees are temporary and deleted after indexing; all file content is persisted in blobs.

        Args:
            max_matches: Maximum number of match results to return
            max_files_scanned: Maximum number of files to scan (prevents unbounded Azure calls)
        """
        results: List[Dict[str, Any]] = []
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        # Search Azure Blob Storage via Fact Store manifest
        if self.db is not None and self.analysis_id is not None:
            files = (
                self.db.query(FactFile)
                .filter(
                    FactFile.analysis_id == self.analysis_id,
                    FactFile.is_binary == False,
                )
                .all()
            )
            from backend.storage import get_storage
            storage = get_storage()
            files_scanned = 0
            for f_rec in files:
                if file_pattern and not fnmatch.fnmatch(f_rec.path, file_pattern) and not fnmatch.fnmatch(os.path.basename(f_rec.path), file_pattern):
                    continue
                if not f_rec.blob_name:
                    continue

                # Stop scanning after max_files_scanned to prevent unbounded Azure calls
                files_scanned += 1
                if files_scanned > max_files_scanned:
                    break

                try:
                    text = storage.get_object_text(f_rec.blob_name)
                    for line_idx, line in enumerate(text.splitlines(), start=1):
                        if pattern.search(line):
                            results.append({
                                "file": f_rec.path,
                                "line": line_idx,
                                "snippet": line.strip()[:200],
                                "match_type": "lexical",
                            })
                            if len(results) >= max_matches:
                                return results
                except Exception:
                    continue

        return results

    # ──────────────────────────────────────────────────────────────────────────
    # 4. get_symbol & get_file_outline
    # ──────────────────────────────────────────────────────────────────────────

    def get_symbol(self, name: str) -> List[Dict[str, Any]]:
        """
        Looks up symbol definitions (functions, classes, methods) in the Fact Store.
        """
        if not self.db or not self.analysis_id:
            return []

        symbols = (
            self.db.query(FactSymbol, FactFile.path)
            .join(FactFile, FactSymbol.file_id == FactFile.id)
            .filter(
                FactSymbol.analysis_id == self.analysis_id,
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

    def get_file_outline(self, path: str) -> Dict[str, Any]:
        """
        Returns an outline of symbols (classes, functions, routes) in a file.
        """
        if not self.db or not self.analysis_id:
            return {"file": path, "symbols": []}

        symbols = (
            self.db.query(FactSymbol)
            .join(FactFile, FactSymbol.file_id == FactFile.id)
            .filter(
                FactSymbol.analysis_id == self.analysis_id,
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

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Call graph: get_callers & get_callees
    # ──────────────────────────────────────────────────────────────────────────

    def get_callers(self, symbol_name: str) -> List[Dict[str, Any]]:
        """Finds symbols that invoke or call the given symbol."""
        if not self.db or not self.analysis_id:
            return []

        # First, find the target symbol ID
        target_symbol = (
            self.db.query(FactSymbol.id)
            .filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.name.ilike(f"%{symbol_name}%"),
            )
            .first()
        )

        if not target_symbol:
            return []

        target_id = target_symbol.id

        # Find all symbols that call this target
        rel_rows = (
            self.db.query(FactRelationship, FactSymbol.name, FactSymbol.symbol_type)
            .join(FactSymbol, FactRelationship.from_symbol_id == FactSymbol.id)
            .filter(
                FactRelationship.analysis_id == self.analysis_id,
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

    def get_callees(self, symbol_name: str) -> List[Dict[str, Any]]:
        """Finds symbols that are called by the given symbol."""
        if not self.db or not self.analysis_id:
            return []

        # First, find the source symbol ID
        source_symbol = (
            self.db.query(FactSymbol.id)
            .filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.name.ilike(f"%{symbol_name}%"),
            )
            .first()
        )

        if not source_symbol:
            return []

        source_id = source_symbol.id

        rel_rows = (
            self.db.query(FactRelationship, FactSymbol.name, FactSymbol.symbol_type)
            .join(FactSymbol, FactRelationship.to_symbol_id == FactSymbol.id)
            .filter(
                FactRelationship.analysis_id == self.analysis_id,
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

    def get_related_files(self, path: str) -> List[Dict[str, Any]]:
        """Finds files related via imports or function calls."""
        if not self.db or not self.analysis_id:
            return []

        # Find symbol IDs in this file
        file_syms = (
            self.db.query(FactSymbol.id)
            .join(FactFile, FactSymbol.file_id == FactFile.id)
            .filter(FactSymbol.analysis_id == self.analysis_id, FactFile.path == path)
            .all()
        )
        sym_ids = [s[0] for s in file_syms]
        if not sym_ids:
            return []

        related_rows = (
            self.db.query(FactRelationship, FactFile.path)
            .join(FactSymbol, FactRelationship.to_symbol_id == FactSymbol.id)
            .join(FactFile, FactSymbol.file_id == FactFile.id)
            .filter(
                FactRelationship.analysis_id == self.analysis_id,
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

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Hybrid search_repository
    # ──────────────────────────────────────────────────────────────────────────

    def _get_retriever(self) -> Optional[HybridRetriever]:
        """Lazily construct and cache HybridRetriever to avoid rebuilding BM25 index per call."""
        if self._retriever is None and self.db is not None and self.analysis_id is not None:
            try:
                self._retriever = HybridRetriever(db=self.db, analysis_id=self.analysis_id)
            except Exception as e:
                logger.debug(f"Failed to initialize HybridRetriever: {e}")
                return None
        return self._retriever

    def search_repository(self, query: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Hybrid search using HybridRetriever with comma-separated multi-query batching.
        Supports: "mysql,db,connection,database" → splits into 3 queries, dedupes results.
        Pagination: use offset to fetch next batch (e.g., offset=30 to get results 31-60).
        Returns: [{"type", "file", "symbol"/"line", "lines"/"snippet", "query", "match_source", "score"}]
        """
        retriever = self._get_retriever()
        if retriever is None:
            # Fallback to original multi-method approach if retriever unavailable
            return self._search_repository_fallback(query, limit, offset)

        # Split query on commas (supports comma-separated multi-query batching)
        sub_queries = [q.strip() for q in query.split(",") if q.strip()]
        if not sub_queries:
            return []

        combined: List[Dict[str, Any]] = []
        seen_keys = set()
        max_total = min(limit * len(sub_queries), 30)  # hard cap at 30 results

        for sub_query in sub_queries:
            try:
                # Use HybridRetriever for better ranking
                top_k = max(limit, 10)
                results = retriever.retrieve(sub_query, top_k=top_k)

                for result in results:
                    # Map RetrieverResult to output dict shape
                    if result.symbol:
                        key = f"sym:{result.file_path}:{result.symbol}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            combined.append({
                                "type": "symbol",
                                "file": result.file_path,
                                "symbol": result.symbol,
                                "lines": f"{result.line_start}-{result.line_end}" if result.line_start else "",
                                "query": sub_query,
                                "match_source": result.score_type or "symbol_index",
                                "score": result.score,
                            })
                    else:
                        key = f"code:{result.file_path}:{result.line_number}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            combined.append({
                                "type": "code",
                                "file": result.file_path,
                                "line": result.line_number,
                                "snippet": result.snippet or "",
                                "query": sub_query,
                                "match_source": result.score_type or "hybrid",
                                "score": result.score,
                            })
            except Exception as e:
                logger.debug(f"Error retrieving for query '{sub_query}': {e}")
                continue

        # If HybridRetriever returned no results, fall back to basic search methods
        if not combined:
            logger.debug(f"HybridRetriever returned 0 results, falling back to basic search for queries: {sub_queries}")
            return self._search_repository_fallback(query, limit, offset)

        # Apply offset-based pagination
        start = offset
        end = offset + max_total
        return combined[start:end]

    def _search_repository_fallback(self, query: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Fallback to original multi-method search when HybridRetriever is unavailable."""
        combined: List[Dict[str, Any]] = []
        seen_keys = set()

        # Split query on commas to support multi-query batching in fallback
        sub_queries = [q.strip() for q in query.split(",") if q.strip()]
        if not sub_queries:
            return []

        max_total = min(limit * len(sub_queries), 30)

        for sub_query in sub_queries:
            # 1. Symbol search
            sym_matches = self.get_symbol(sub_query)
            for sym in sym_matches[:5]:
                key = f"sym:{sym['file']}:{sym['name']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    combined.append({
                        "type": "symbol",
                        "file": sym["file"],
                        "symbol": sym["name"],
                        "symbol_type": sym["symbol_type"],
                        "lines": f"{sym['line_start']}-{sym['line_end']}",
                        "query": sub_query,
                        "match_source": "symbol_index",
                        "score": 0,
                    })

            # 2. File path match
            file_matches = self.find_files(f"*{sub_query}*")
            for f in file_matches[:5]:
                key = f"file:{f['path']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    combined.append({
                        "type": "file",
                        "file": f["path"],
                        "size": f.get("size", 0),
                        "query": sub_query,
                        "match_source": "filename_manifest",
                        "score": 0,
                    })

            # 3. Lexical search in source files
            lex_matches = self.search_code(sub_query, max_matches=5)
            for lex in lex_matches:
                key = f"lex:{lex['file']}:{lex['line']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    combined.append({
                        "type": "code",
                        "file": lex["file"],
                        "line": lex["line"],
                        "snippet": lex["snippet"],
                        "query": sub_query,
                        "match_source": "lexical",
                        "score": 0,
                    })

        # Apply offset-based pagination
        start = offset
        end = offset + max_total
        return combined[start:end]
