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
        Safely reads a slice of a file.
        Priority:
          1. Active temporary worktree (if repo_root is provided and exists)
          2. Azure Blob Storage (via FactFile.blob_name)
        """
        clean_path = path.replace("\\", "/").removeprefix("./").lstrip("/")

        # 1. Active Worktree (if present)
        if self.repo_root and self.repo_root.exists():
            target_file = validate_repo_path(self.repo_root, path, allow_binary=False)
            if target_file.exists():
                try:
                    with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    total_lines = len(lines)
                    s, e = clamp_line_range(total_lines, start_line, end_line)
                    selected_lines = lines[s - 1 : e]
                    numbered_content = "".join(f"{s + idx:4d} | {line}" for idx, line in enumerate(selected_lines))
                    rel_path = str(target_file.relative_to(self.repo_root)).replace("\\", "/")
                    return {
                        "path": rel_path,
                        "start_line": s,
                        "end_line": e,
                        "total_lines": total_lines,
                        "content": numbered_content,
                        "raw_text": "".join(selected_lines),
                    }
                except Exception as e:
                    logger.debug(f"Could not read from worktree {path}: {e}")

        # 2. Azure Blob Storage (persistent repository snapshots)
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

        raise RepositorySecurityError(f"File not found in active worktree or Blob Storage: '{path}'")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. find_files
    # ──────────────────────────────────────────────────────────────────────────

    def find_files(self, pattern: str = "*", limit: int = 50) -> List[Dict[str, Any]]:
        """
        Finds files in the repository matching a glob pattern (e.g. '*.py', 'docs/**/*.md').
        Uses Fact Store database manifest if available, with filesystem fallback.
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
            if results:
                return results

        # Fallback to filesystem scan
        if self.repo_root and self.repo_root.exists():
            for root, dirs, filenames in os.walk(self.repo_root):
                # Prune common ignore dirs
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}]
                for fname in filenames:
                    full_p = Path(root) / fname
                    rel_p = str(full_p.relative_to(self.repo_root)).replace("\\", "/")
                    if fnmatch.fnmatch(rel_p, pattern) or fnmatch.fnmatch(fname, pattern):
                        results.append({
                            "path": rel_p,
                            "size": full_p.stat().st_size if full_p.exists() else 0,
                            "is_binary": is_binary_file(full_p),
                        })
                        if len(results) >= limit:
                            break
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
        Performs lexical regex/substring search over source files in the repository.
        Searches active worktree if present, or queries Blob Storage via FactStore metadata.

        Args:
            max_matches: Maximum number of match results to return
            max_files_scanned: Maximum number of files to scan (prevents unbounded Azure calls)
        """
        results: List[Dict[str, Any]] = []
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        # 1. Active worktree search if available
        if self.repo_root and self.repo_root.exists():
            for root, dirs, files in os.walk(self.repo_root):
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}]
                for fname in files:
                    full_path = Path(root) / fname
                    rel_path = str(full_path.relative_to(self.repo_root)).replace("\\", "/")

                    if file_pattern and not fnmatch.fnmatch(rel_path, file_pattern) and not fnmatch.fnmatch(fname, file_pattern):
                        continue

                    if is_binary_file(full_path):
                        continue

                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line_idx, line in enumerate(f, start=1):
                                if pattern.search(line):
                                    results.append({
                                        "file": rel_path,
                                        "line": line_idx,
                                        "snippet": line.strip()[:200],
                                        "match_type": "lexical",
                                    })
                                    if len(results) >= max_matches:
                                        return results
                    except Exception:
                        continue
            if results:
                return results

        # 2. Azure Blob Storage search via Fact Store manifest
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

        rel_rows = (
            self.db.query(FactRelationship, FactSymbol.name, FactSymbol.symbol_type)
            .join(FactSymbol, FactRelationship.from_symbol_id == FactSymbol.id)
            .filter(
                FactRelationship.analysis_id == self.analysis_id,
                FactRelationship.rel_type == "CALLS",
                FactRelationship.to_symbol_id.ilike(f"%{symbol_name}%"),
            )
            .limit(20)
            .all()
        )

        return [
            {
                "caller_symbol": name,
                "symbol_type": sym_type,
                "relationship": rel.rel_type,
                "evidence_line": rel.evidence_line,
                "snippet": rel.evidence_snippet,
            }
            for rel, name, sym_type in rel_rows
        ]

    def get_callees(self, symbol_name: str) -> List[Dict[str, Any]]:
        """Finds symbols that are called by the given symbol."""
        if not self.db or not self.analysis_id:
            return []

        rel_rows = (
            self.db.query(FactRelationship, FactSymbol.name, FactSymbol.symbol_type)
            .join(FactSymbol, FactRelationship.to_symbol_id == FactSymbol.id)
            .filter(
                FactRelationship.analysis_id == self.analysis_id,
                FactRelationship.rel_type == "CALLS",
                FactRelationship.from_symbol_id.ilike(f"%{symbol_name}%"),
            )
            .limit(20)
            .all()
        )

        return [
            {
                "callee_symbol": name,
                "symbol_type": sym_type,
                "relationship": rel.rel_type,
                "evidence_line": rel.evidence_line,
                "snippet": rel.evidence_snippet,
            }
            for rel, name, sym_type in rel_rows
        ]

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

    def search_repository(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Hybrid search combining:
        1. Symbol matches (FactStore)
        2. Filename matches (Manifest)
        3. Lexical code matches (Source snapshot)
        """
        combined: List[Dict[str, Any]] = []
        seen_keys = set()

        # 1. Symbol search
        sym_matches = self.get_symbol(query)
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
                    "match_source": "symbol_index",
                })

        # 2. File path match
        file_matches = self.find_files(f"*{query}*")
        for f in file_matches[:5]:
            key = f"file:{f['path']}"
            if key not in seen_keys:
                seen_keys.add(key)
                combined.append({
                    "type": "file",
                    "file": f["path"],
                    "size": f.get("size", 0),
                    "match_source": "filename_manifest",
                })

        # 3. Lexical search in source files
        lex_matches = self.search_code(query, max_matches=5)
        for lex in lex_matches:
            key = f"lex:{lex['file']}:{lex['line']}"
            if key not in seen_keys:
                seen_keys.add(key)
                combined.append({
                    "type": "code",
                    "file": lex["file"],
                    "line": lex["line"],
                    "snippet": lex["snippet"],
                    "match_source": "lexical",
                })

        return combined[:limit]
