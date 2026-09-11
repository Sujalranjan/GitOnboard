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
        Requires analysis_id to be set. Constructs blob name from repo hash and path,
        fetches from blob storage, and returns specified line range.
        """
        from backend.storage import get_storage

        clean_path = path.replace("\\", "/").removeprefix("./").lstrip("/")
        storage = get_storage()

        # Convert string parameters to integers if needed (from LLM tool calls)
        try:
            start_line = int(start_line) if start_line else 1
            end_line = int(end_line) if end_line else None
        except (ValueError, TypeError):
            return {
                "path": clean_path,
                "error": "invalid_range",
                "message": "start_line and end_line must be valid integers."
            }

        # Need analysis_id to get repo hash
        if self.analysis_id is None or self.db is None:
            return {
                "path": clean_path,
                "error": "no_analysis",
                "message": "Analysis context not available. Cannot read file."
            }

        # Get repository hash from analysis
        try:
            analysis = self.db.query(Analysis).filter(Analysis.id == self.analysis_id).first()
            if not analysis:
                return {
                    "path": clean_path,
                    "error": "no_analysis",
                    "message": f"Analysis {self.analysis_id} not found."
                }

            repo = self.db.query(Repository).filter(Repository.id == analysis.repository_id).first()
            if not repo or not repo.repository_hash:
                return {
                    "path": clean_path,
                    "error": "no_repo",
                    "message": "Repository not found."
                }

            # Construct blob name directly
            blob_name = f"repositories/{repo.repository_hash}/snapshots/local_clone/{clean_path}"

            # Fetch from blob storage
            raw_text = storage.get_object_text(blob_name)
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

        except FileNotFoundError:
            return {
                "path": clean_path,
                "error": "wrong_path",
                "message": f"File not found: '{path}'. Check that the path is correct."
            }
        except Exception as err:
            return {
                "path": clean_path,
                "error": "read_error",
                "message": f"Error reading file: {str(err)}"
            }

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
    # 3. get_tree
    # ──────────────────────────────────────────────────────────────────────────

    def get_tree(self, path: str = "", depth: int = 2) -> Dict[str, Any]:
        """
        Returns tree structure of repository files starting from given path.
        Args:
            path: Starting path (e.g. 'backend' or 'backend/routers'). Empty string = root
            depth: How many directory levels to show (1-10)
        """
        if self.analysis_id is None or self.db is None:
            return {
                "error": "no_analysis",
                "message": "Analysis context not available."
            }

        # Normalize path
        clean_path = path.replace("\\", "/").strip("/") if path else ""
        depth = max(1, min(10, depth))  # Clamp between 1 and 10

        try:
            # Get all files for this analysis
            files = self.db.query(FactFile).filter(
                FactFile.analysis_id == self.analysis_id
            ).all()

            # Filter files under the specified path
            matching_files = []
            for f in files:
                if clean_path:
                    if f.path.startswith(clean_path + "/"):
                        matching_files.append(f.path)
                else:
                    matching_files.append(f.path)

            if not matching_files:
                return {
                    "path": clean_path or "/",
                    "tree": "No files found",
                    "file_count": 0
                }

            # Build tree structure
            tree_lines = []
            if clean_path:
                tree_lines.append(f"{clean_path}/")
            else:
                tree_lines.append(".")

            # Build tree structure: use dict with '__dirs' and '__files' keys
            def add_to_tree(tree, parts, depth_limit):
                if not parts:
                    return
                if len(parts) > depth_limit + 1:
                    return  # Beyond depth limit

                current = tree
                # Navigate/create directories
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    if not isinstance(current[part], dict):
                        current[part] = {}
                    current = current[part]

                # Add the file to the current directory
                if parts[-1]:
                    current[parts[-1]] = None

            dirs = {}
            for file_path in sorted(matching_files):
                # Remove the base path prefix
                relative = file_path[len(clean_path)+1:] if clean_path else file_path
                parts = relative.split("/")
                add_to_tree(dirs, parts, depth)

            # Format tree as string
            def format_tree(node, prefix="", is_last=True):
                lines = []
                if isinstance(node, dict):
                    items = sorted(node.items())
                    for i, (name, subtree) in enumerate(items):
                        is_last_item = (i == len(items) - 1)
                        connector = "└── " if is_last_item else "├── "
                        # subtree is None = file, dict = directory
                        is_dir = isinstance(subtree, dict) and subtree
                        lines.append(prefix + connector + name + ("/" if is_dir else ""))

                        if is_dir:
                            next_prefix = prefix + ("    " if is_last_item else "│   ")
                            lines.extend(format_tree(subtree, next_prefix, is_last_item))
                return lines

            tree_lines.extend(format_tree(dirs))
            tree_str = "\n".join(tree_lines)

            return {
                "path": clean_path or "/",
                "depth": depth,
                "tree": tree_str,
                "file_count": len(matching_files)
            }

        except Exception as err:
            return {
                "error": "tree_error",
                "message": f"Error building tree: {str(err)}"
            }

    # ──────────────────────────────────────────────────────────────────────────
    # 4. search_code (Lexical Search)
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

        # DIAGNOSTIC: Log precondition state at entry
        logger.error(f"[search_code:DIAGNOSTIC] ENTRY query='{query[:50]}' repo='{self.repo_name}' db={self.db is not None} analysis_id={self.analysis_id}")

        # Validate preconditions
        if self.db is None:
            try:
                logger.error(f"[search_code:FAILURE] Database session is None. Cannot search repository '{self.repo_name}'.")
            except:
                pass
            return results
        if self.analysis_id is None:
            try:
                logger.error(f"[search_code:FAILURE] Analysis ID is None for repository '{self.repo_name}'. Analysis may not be complete.")
            except:
                pass
            return results

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        # Search Azure Blob Storage via Fact Store manifest
        files = (
            self.db.query(FactFile)
            .filter(
                FactFile.analysis_id == self.analysis_id,
                FactFile.is_binary == False,
            )
            .all()
        )

        if not files:
            try:
                logger.debug(f"[search_code] No non-binary files found for analysis_id={self.analysis_id}")
            except:
                pass
            return results

        try:
            logger.debug(f"[search_code] Searching {len(files)} files for query='{query}' with pattern='{file_pattern}'")
        except:
            pass

        from backend.storage import get_storage
        storage = get_storage()
        files_scanned = 0
        files_with_matches = 0

        for f_rec in files:
            if file_pattern and not fnmatch.fnmatch(f_rec.path, file_pattern) and not fnmatch.fnmatch(os.path.basename(f_rec.path), file_pattern):
                continue
            if not f_rec.blob_name:
                try:
                    logger.debug(f"[search_code] File {f_rec.path} has no blob_name; skipping")
                except:
                    pass
                continue

            # Stop scanning after max_files_scanned to prevent unbounded Azure calls
            files_scanned += 1
            if files_scanned > max_files_scanned:
                try:
                    logger.debug(f"[search_code] Reached max_files_scanned limit ({max_files_scanned}); stopping scan")
                except:
                    pass
                break

            try:
                text = storage.get_object_text(f_rec.blob_name)
                matches_in_file = 0
                for line_idx, line in enumerate(text.splitlines(), start=1):
                    if pattern.search(line):
                        results.append({
                            "file": f_rec.path,
                            "line": line_idx,
                            "snippet": line.strip()[:200],
                            "match_type": "lexical",
                        })
                        matches_in_file += 1
                        if len(results) >= max_matches:
                            try:
                                logger.debug(f"[search_code] Found {len(results)} matches across {files_with_matches + 1} files; stopping")
                            except:
                                pass
                            return results
                if matches_in_file > 0:
                    files_with_matches += 1
            except Exception as e:
                try:
                    logger.debug(f"[search_code] Error reading blob {f_rec.blob_name}: {e}")
                except:
                    pass
                continue

        try:
            logger.debug(f"[search_code] Search complete: {len(results)} matches in {files_with_matches} files (scanned {files_scanned} files)")
        except:
            pass
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
