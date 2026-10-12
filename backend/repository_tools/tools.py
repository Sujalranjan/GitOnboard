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
from backend.config import settings

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
        context_lines: int = 0,
        symbol: Optional[str] = None,
        max_content_tokens: Optional[int] = None,
        control_reservation_tokens: int = 60,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Reads a slice of a file from Azure Blob Storage or local clone.
        Requires analysis_id to be set when using blob storage.
        Supports optional context_lines to expand surrounding window.
        Supports optional symbol to auto-locate function/class definitions.
        Uses semantic truncation if max_content_tokens is provided.
        """
        from backend.storage import get_storage
        from .truncation import truncate_semantically

        clean_path = path.replace("\\", "/").removeprefix("./").lstrip("/")
        storage = get_storage()

        # Convert string parameters to integers if needed (from LLM tool calls)
        try:
            start_line = int(start_line) if start_line else 1
            end_line = int(end_line) if end_line else None
            context_lines = max(0, int(context_lines)) if context_lines else 0
        except (ValueError, TypeError):
            return {
                "path": clean_path,
                "error": "invalid_range",
                "message": "start_line, end_line, and context_lines must be valid integers."
            }

        try:
            # Check if reading from local repo_root or remote blob storage
            resolved_text = None
            if self.repo_root and Path(self.repo_root).exists():
                try:
                    full_path = validate_repo_path(Path(self.repo_root), clean_path)
                    if full_path.exists() and full_path.is_file():
                        resolved_text = full_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

                # If direct path wasn't found in repo_root, search for suffix / basename match within repo_root
                if resolved_text is None:
                    repo_path_obj = Path(self.repo_root)
                    for candidate in repo_path_obj.rglob("*"):
                        if candidate.is_file():
                            rel_cand = candidate.relative_to(repo_path_obj).as_posix()
                            if rel_cand.endswith(clean_path) or clean_path.endswith(rel_cand):
                                resolved_text = candidate.read_text(encoding="utf-8", errors="replace")
                                clean_path = rel_cand
                                break

            if resolved_text is None:
                # Need analysis_id to get repo hash
                if self.analysis_id is None or self.db is None:
                    return {
                        "path": clean_path,
                        "error": "wrong_path",
                        "message": f"File '{clean_path}' not found in repository."
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

                    # Try to find the file by searching across all snapshot directories for this repo
                    repo_prefix = f"repositories/{repo.repository_hash}/snapshots/"
                    all_blobs = storage.list_objects(prefix=repo_prefix)

                    # Look for the file in any snapshot directory
                    matching_blob = None
                    for blob in all_blobs:
                        if blob.endswith(f"/{clean_path}") or clean_path.endswith(blob.split("/snapshots/")[-1].split("/", 1)[-1]):
                            matching_blob = blob
                            break

                    if not matching_blob:
                        # Fallback: match by basename if unique
                        base_name = clean_path.split("/")[-1]
                        basename_matches = [b for b in all_blobs if b.endswith(f"/{base_name}")]
                        if len(basename_matches) == 1:
                            matching_blob = basename_matches[0]

                    if not matching_blob:
                        raise FileNotFoundError(f"File not found in any snapshot: {clean_path}")

                    # Fetch from blob storage
                    raw_text = storage.get_object_text(matching_blob)
                    from backend.intelligence.notebook import resolve_source_document
                    doc = resolve_source_document(clean_path, raw_text)
                    resolved_text = doc.source if not doc.conversion_error else raw_text
                except Exception as e:
                    raise e

            lines = resolved_text.splitlines(keepends=True)
            total_lines = len(lines)

            # 1. Resolve symbol if requested BEFORE context-overflow validation
            target_symbol = (symbol or kwargs.get("symbol") or "").strip()
            if target_symbol:
                sym_found = False
                if self.db is not None and self.analysis_id is not None:
                    try:
                        from backend.models.fact_store import FactSymbol, FactFile
                        # Scope search to this file first, fallback to analysis-wide match
                        sym_fact = (
                            self.db.query(FactSymbol)
                            .join(FactFile, FactSymbol.file_id == FactFile.id)
                            .filter(
                                FactSymbol.analysis_id == self.analysis_id,
                                FactFile.path == clean_path,
                                FactSymbol.name == target_symbol,
                            )
                            .first()
                        )
                        if not sym_fact:
                            # Try suffix match on path or case-insensitive match
                            sym_fact = (
                                self.db.query(FactSymbol)
                                .join(FactFile, FactSymbol.file_id == FactFile.id)
                                .filter(
                                    FactSymbol.analysis_id == self.analysis_id,
                                    FactFile.path.endswith(clean_path),
                                    FactSymbol.name.ilike(target_symbol),
                                )
                                .first()
                            )
                        if not sym_fact:
                            sym_fact = (
                                self.db.query(FactSymbol)
                                .filter(
                                    FactSymbol.analysis_id == self.analysis_id,
                                    FactSymbol.name == target_symbol,
                                )
                                .first()
                            )
                        if sym_fact and sym_fact.line_start:
                            start_line = max(1, sym_fact.line_start)
                            end_line = min(total_lines, sym_fact.line_end) if sym_fact.line_end else min(total_lines, start_line + 120)
                            sym_found = True
                    except Exception:
                        pass

                # If FactStore didn't find it, inspect source lines directly via AST/regex definition patterns
                if not sym_found:
                    import re
                    pattern = re.compile(rf"(?:async\s+)?(?:function\s+{re.escape(target_symbol)}\b|(?:const|let|var)\s+{re.escape(target_symbol)}\s*=|class\s+{re.escape(target_symbol)}\b|def\s+{re.escape(target_symbol)}\b)")
                    for idx, line in enumerate(lines, start=1):
                        if pattern.search(line):
                            start_line = idx
                            # Read until next top-level function or up to 60 lines
                            end_line = min(total_lines, idx + 60)
                            sym_found = True
                            break

            safe_limit = getattr(settings, "investigation_read_file_max_lines", 600)

            # 2. Check unbounded read on large files (> safe_limit lines)
            if end_line is None and total_lines > safe_limit:
                return {
                    "path": clean_path,
                    "error": "context_overflow_protection",
                    "message": (
                        f"Refusing full file read: '{clean_path}' has {total_lines} lines. "
                        f"Reading the entire file without line boundaries will cause context overflow. "
                        f"Please use start_line and end_line (safe read limit is {safe_limit} lines), "
                        f"or run get_file_outline first."
                    ),
                    "total_lines": total_lines,
                }

            # 3. Handle invalid/reversed/out-of-bounds line ranges consistently
            # If end_line was provided and end_line < start_line, swap them
            if end_line is not None and end_line < start_line:
                start_line, end_line = end_line, start_line

            # If start_line exceeds total_lines, return a clean error without crashing
            if start_line > total_lines:
                return {
                    "path": clean_path,
                    "error": "invalid_range",
                    "message": f"Start line {start_line} exceeds total file lines ({total_lines}).",
                    "total_lines": total_lines,
                }

            orig_requested_start = max(1, start_line)
            orig_requested_end = min(total_lines, end_line) if end_line is not None else min(total_lines, orig_requested_start + safe_limit - 1)

            # 3. Enforce safe line range limit
            range_clamped = False
            SAFE_MAX_LINES = safe_limit
            if (orig_requested_end - orig_requested_start + 1) > SAFE_MAX_LINES:
                target_end = orig_requested_start + SAFE_MAX_LINES - 1
                range_clamped = True
            else:
                target_end = orig_requested_end

            s = orig_requested_start
            e = target_end
            if context_lines > 0:
                s = max(1, s - context_lines)
                e = min(total_lines, e + context_lines)

            requested_slice = lines[s - 1 : e]

            # Semantic truncation based on pre-calculated budget
            # Default fallback: ~2500 tokens (enough for full 200-250 lines of code)
            budget_tokens = max_content_tokens if max_content_tokens and max_content_tokens > 0 else 2500

            selected_lines, count_taken, was_clamped = truncate_semantically(
                lines=requested_slice,
                max_tokens=budget_tokens,
                file_path=clean_path,
                reserved_control_tokens=control_reservation_tokens,
            )

            actual_end = s + count_taken - 1
            numbered_content = "".join(f"{s + idx:4d} | {line}" for idx, line in enumerate(selected_lines))

            # Provide transparent notices so the model knows exact status and how to fetch remaining content
            effective_is_truncated = (was_clamped and actual_end < e) or (range_clamped and target_end < orig_requested_end)
            if range_clamped and target_end < orig_requested_end:
                next_start = target_end + 1
                notice = (
                    f"\n\n[Notice: Requested range {orig_requested_start}-{orig_requested_end} exceeds safe limit of {SAFE_MAX_LINES} lines; "
                    f"clamped to lines {s}-{target_end}. "
                    f"Returned lines {s}-{target_end} of {total_lines}.\n"
                    f"Still unread: lines {next_start}-{orig_requested_end}.\n"
                    f"To inspect further, call read_file(path=\"{clean_path}\", start_line={next_start}, end_line={orig_requested_end}) "
                    f"or call get_file_outline(path=\"{clean_path}\") to locate symbols.]"
                )
                numbered_content += notice
            elif was_clamped and actual_end < e:
                next_start = actual_end + 1
                remaining_lines_count = e - actual_end
                unread_end = min(e, total_lines)
                notice = (
                    f"\n\n[CONTEXT PROTECTION - FILE TRUNCATED]\n"
                    f"File: {clean_path} (total {total_lines} lines)\n"
                    f"- Returned lines: {s}-{actual_end}\n"
                    f"- Still unread in this request: lines {next_start}-{unread_end} ({remaining_lines_count} lines remaining)\n"
                    f"Continue inspection with: read_file(path=\"{clean_path}\", start_line={next_start}, end_line={unread_end})."
                )
                numbered_content += notice

            effective_remaining = (orig_requested_end - actual_end) if actual_end < orig_requested_end else 0
            effective_next_start = (actual_end + 1) if actual_end < orig_requested_end else None

            return {
                "path": clean_path,
                "start_line": s,
                "end_line": actual_end,
                "requested_start_line": orig_requested_start,
                "requested_end_line": orig_requested_end,
                "total_lines": total_lines,
                "content": numbered_content,
                "raw_text": "".join(selected_lines),
                "is_truncated": effective_is_truncated,
                "next_start_line": effective_next_start,
                "remaining_lines": effective_remaining,
            }

        except FileNotFoundError:
            return {
                "path": clean_path,
                "error": "wrong_path",
                "message": f"File not found: '{clean_path}'. Check that the path is correct."
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
        elif self.repo_root and os.path.exists(self.repo_root):
            root_path = Path(self.repo_root)
            for file_path in root_path.rglob("*"):
                if not file_path.is_file():
                    continue
                rel_path = file_path.relative_to(root_path).as_posix()
                if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                    results.append({
                        "path": rel_path,
                        "language": "python" if rel_path.endswith(".py") else "text",
                        "size": file_path.stat().st_size,
                        "is_documentation": False,
                        "is_agent_instruction": False,
                        "is_test": False,
                        "is_binary": False,
                    })
                    if len(results) >= limit:
                        break

        return results

    # ──────────────────────────────────────────────────────────────────────────
    # 3. get_tree
    # ──────────────────────────────────────────────────────────────────────────

    def get_tree(self, path: str = "", depth: int = 0) -> Dict[str, Any]:
        """
        Returns complete directory tree from Azure Blob Storage snapshot.
        Shows ALL files in the repository snapshot (code + non-code files).

        Args:
            path: Starting path (e.g. 'backend' or 'backend/routers'). Empty string = root
            depth: How many directory levels to show (0-10). depth=0 shows only immediate contents.

        Note: Uses Blob Storage for complete picture, not PostgreSQL (which only indexes code files).
        """
        if self.analysis_id is None:
            if self.repo_root and os.path.exists(self.repo_root):
                clean_path = path.replace("\\", "/").strip("/") if path and path != "." else ""
                target_dir = Path(self.repo_root) / clean_path if clean_path else Path(self.repo_root)
                if not target_dir.exists():
                    return {"path": clean_path or "/", "tree": "Directory not found", "file_count": 0}
                
                lines = [f"{clean_path}/" if clean_path else "."]
                count = 0
                for item in sorted(target_dir.rglob("*")):
                    if ".git" in item.parts or ".venv" in item.parts or "__pycache__" in item.parts or "node_modules" in item.parts:
                        continue
                    rel = item.relative_to(target_dir).as_posix()
                    depth_level = len(rel.split("/")) - 1
                    if depth > 0 and depth_level >= depth:
                        continue
                    indent = "  " * (depth_level + 1)
                    prefix = "[dir]  " if item.is_dir() else "[file] "
                    lines.append(f"{indent}{prefix}{item.name}")
                    if item.is_file():
                        count += 1
                    if count >= 100:
                        lines.append(f"  ... ({count}+ files, truncated)")
                        break
                return {"path": clean_path or "/", "depth": depth, "tree": "\n".join(lines), "file_count": count}

            return {
                "error": "no_analysis",
                "message": "Analysis context not available."
            }

        # Normalize path (handle "." as root)
        clean_path = path.replace("\\", "/").strip("/") if path and path != "." else ""
        depth = max(0, min(10, depth))  # Clamp between 0 and 10

        try:
            # Get repository hash from analysis
            from backend.models.repository import Analysis, Repository
            analysis = self.db.query(Analysis).filter(Analysis.id == self.analysis_id).first()
            if not analysis:
                return {"error": "analysis_not_found", "message": f"Analysis {self.analysis_id} not found"}

            repo = self.db.query(Repository).filter(Repository.id == analysis.repository_id).first()
            if not repo:
                return {"error": "repo_not_found", "message": f"Repository for analysis {self.analysis_id} not found"}

            # List all objects in Blob Storage for this repository snapshot
            from backend.storage import get_storage
            storage = get_storage()
            repo_prefix = f"repositories/{repo.repository_hash}/snapshots/"

            # List all blobs in all snapshots for this repo
            all_blobs = storage.list_objects(repo_prefix)

            # Filter to only blobs under the requested path (or all if no path specified)
            matching_files = []

            for blob_name in all_blobs:
                # Extract the relative path from the blob
                # blob_name format: repositories/{hash}/snapshots/{snapshot_id}/{file_path}
                parts = blob_name.split("/")
                if len(parts) >= 5:  # repo/hash/snapshots/snapshot_id/file_path...
                    # Everything after snapshots/{snapshot_id}/ is the file path
                    file_path = "/".join(parts[4:])

                    # Filter by clean_path if specified
                    if clean_path:
                        if file_path.startswith(clean_path + "/"):
                            relative = file_path[len(clean_path) + 1:]
                            if relative:
                                matching_files.append(relative)
                    else:
                        # Include all files
                        matching_files.append(file_path)

            # Remove duplicates (same file in multiple snapshots)
            matching_files = sorted(set(matching_files))

            if not matching_files:
                return {
                    "path": clean_path or "/",
                    "depth": depth,
                    "tree": "No files found",
                    "file_count": 0
                }

            # Build tree structure
            tree_lines = []
            if clean_path:
                tree_lines.append(f"{clean_path}/")
            else:
                tree_lines.append(".")

            # Build tree structure from relative paths
            def add_to_tree(tree, parts, depth_limit):
                if not parts or not parts[0]:
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
                parts = file_path.split("/")
                add_to_tree(dirs, parts, depth)

            # Format tree as string with ASCII art
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
        # Convert string parameters to integers if needed (from LLM tool calls)
        try:
            max_matches = int(max_matches) if max_matches else 25
            max_files_scanned = int(max_files_scanned) if max_files_scanned else 40
        except (ValueError, TypeError):
            max_matches = 25
            max_files_scanned = 40

        results: List[Dict[str, Any]] = []

        # DIAGNOSTIC: Log precondition state at entry
        logger.error(f"[search_code:DIAGNOSTIC] ENTRY query='{query[:50]}' repo='{self.repo_name}' db={self.db is not None} analysis_id={self.analysis_id}")

        def _pattern_matches(path: str, pat: Optional[str]) -> bool:
            if not pat:
                return True
            base = os.path.basename(path)
            # Standard glob check
            if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base, pat):
                return True
            # When searching for python source files (e.g. *.py, **/*.py), also match jupyter notebooks
            if pat.endswith(".py") or pat == "*.py":
                if path.endswith(".ipynb") or base.endswith(".ipynb"):
                    return True
        # Validate preconditions
        if self.db is None or self.analysis_id is None:
            if self.repo_root and os.path.exists(self.repo_root):
                root_path = Path(self.repo_root)
                IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build", ".idea", ".vscode", "azurite_data", "archive"}
                SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".sql", ".ipynb"}

                # Extract individual search terms (length >= 3, skipping common stop words)
                raw_words = [w for w in re.findall(r'\b[a-zA-Z_]{3,}\b', query.lower()) if w not in {"how", "what", "where", "from", "into", "and", "the", "that", "this", "which"}]
                try:
                    pattern = re.compile(query, re.IGNORECASE)
                except re.error:
                    pattern = re.compile(re.escape(query), re.IGNORECASE)

                term_pattern = re.compile("|".join(re.escape(w) for w in raw_words), re.IGNORECASE) if raw_words else None

                # Collect candidate source files and sort core backend code first
                candidate_paths = []
                for p in root_path.rglob("*"):
                    if p.is_file() and not any(part in IGNORED_DIRS for part in p.parts):
                        if p.suffix.lower() in SOURCE_EXTS:
                            candidate_paths.append(p)

                def _sort_priority(p: Path) -> Tuple[int, str]:
                    rel = p.relative_to(root_path).as_posix()
                    is_code = rel.endswith((".py", ".ts", ".tsx"))
                    is_core = any(rel.startswith(pr) for pr in ("backend/agent/", "backend/intelligence/", "backend/repository_tools/", "backend/tests/", "backend/models/"))
                    # Score by matching query terms in file name or directory
                    query_match_bonus = sum(1 for w in raw_words if w in rel.lower())
                    category = 0 if (is_code and is_core) else (1 if is_code else 2)
                    return (category, -query_match_bonus, rel)

                candidate_paths.sort(key=_sort_priority)

                from backend.intelligence.notebook import resolve_source_document
                scanned = 0
                max_scanned = max(max_files_scanned, 100)

                for file_path in candidate_paths:
                    rel_path = file_path.relative_to(root_path).as_posix()
                    if not _pattern_matches(rel_path, file_pattern):
                        continue
                    scanned += 1
                    try:
                        raw_content = file_path.read_text(encoding="utf-8", errors="replace")
                        if rel_path.endswith(".ipynb"):
                            doc = resolve_source_document(rel_path, raw_content)
                            content = doc.source if not doc.conversion_error else raw_content
                        else:
                            content = raw_content

                        matches_in_this_file = 0
                        for idx, line in enumerate(content.splitlines(), start=1):
                            line_hit = False
                            # Exact regex match
                            if pattern.search(line):
                                line_hit = True
                            # Or multi-term density match (at least 2 query terms on the line)
                            elif term_pattern:
                                hits = set(term_pattern.findall(line.lower()))
                                if len(hits) >= 2 or ("isolation" in hits and "analysis" in hits):
                                    line_hit = True

                            if line_hit:
                                results.append({
                                    "path": rel_path,
                                    "file": rel_path,
                                    "line": idx,
                                    "snippet": line.strip()[:200],
                                    "query": query,
                                })
                                matches_in_this_file += 1
                                if matches_in_this_file >= 1:
                                    break
                        if len(results) >= max_matches:
                            return results

                    except Exception:
                        pass
                    if scanned >= max_files_scanned:
                        break
                return results

            try:
                logger.error(f"[search_code:FAILURE] Database session is None or Analysis ID is None. Cannot search repository '{self.repo_name}'.")
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
            if not _pattern_matches(f_rec.path, file_pattern):
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
                raw_text = storage.get_object_text(f_rec.blob_name)
                from backend.intelligence.notebook import resolve_source_document
                doc = resolve_source_document(f_rec.path, raw_text)
                text = doc.source if not doc.conversion_error else raw_text

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
    # 5. Symbol & Call Graph Queries
    # ──────────────────────────────────────────────────────────────────────────

    def get_symbol(self, name: str) -> List[Dict[str, Any]]:
        from .symbol_ops import get_symbol_ops
        return get_symbol_ops(self.db, self.analysis_id, name)

    def get_file_outline(self, path: str) -> Dict[str, Any]:
        from .symbol_ops import get_file_outline_ops
        return get_file_outline_ops(self.db, self.analysis_id, path)

    def get_callers(self, symbol_name: str) -> List[Dict[str, Any]]:
        from .symbol_ops import get_callers_ops
        return get_callers_ops(self.db, self.analysis_id, symbol_name)

    def get_callees(self, symbol_name: str) -> List[Dict[str, Any]]:
        from .symbol_ops import get_callees_ops
        return get_callees_ops(self.db, self.analysis_id, symbol_name)

    def get_related_files(self, path: str) -> List[Dict[str, Any]]:
        from .symbol_ops import get_related_files_ops
        return get_related_files_ops(self.db, self.analysis_id, path)

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
        from .search_ops import search_repository_ops
        return search_repository_ops(self, query, limit, offset)

    def _search_repository_fallback(self, query: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        from .search_ops import search_repository_fallback_ops
        return search_repository_fallback_ops(self, query, limit, offset)
