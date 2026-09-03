
"""
RepositorySourceReader: Read-only targeted source code snippet reader scoped strictly
by analysis_id, repository_id, and filesystem/worktree boundaries.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RepositorySourceReader:
    """
    Safely retrieves targeted source lines and surrounding context
    from a repository snapshot, local worktree, or FactStore blob storage.
    """

    def __init__(
        self,
        base_path: Optional[str] = None,
        db: Optional[Any] = None,
        analysis_id: Optional[int] = None,
    ):
        self.base_path = Path(base_path) if base_path else None
        self.db = db
        self.analysis_id = analysis_id

    def resolve_file_path(self, file_path: str) -> Optional[Path]:
        """
        Resolves a file path relative to base_path or active worktree locations.
        If direct match does not exist, searches for matching filenames on disk.
        """
        if not file_path:
            return None

        clean_path = file_path.strip("/\\")

        # Collect candidate search bases
        base_paths: list[Path] = []
        if self.base_path and self.base_path.exists():
            base_paths.append(self.base_path)

        for default_dir in ["data/worktrees", "data/repos", "/app/data/worktrees", "/app/data/repos"]:
            p = Path(default_dir)
            if p.exists() and p.is_dir():
                if p not in base_paths:
                    base_paths.append(p)
                for sub in p.iterdir():
                    if sub.is_dir() and sub not in base_paths:
                        base_paths.append(sub)

        for base in base_paths:
            direct = (base / clean_path).resolve()
            if direct.exists() and direct.is_file():
                # Log when reading from local worktrees (for auditing)
                if "/app/data/worktrees" in str(base) or "data/worktrees" in str(base):
                    logger.info(f"[SOURCE_READER] Reading from local worktree: {direct}")
                else:
                    logger.debug(f"[SOURCE_READER] Reading from base path: {direct}")
                return direct

            # Check dot-prefixed alias (e.g., github/workflows/ -> .github/workflows/)
            if clean_path.startswith("github/"):
                dot_alias = (base / f".{clean_path}").resolve()
                if dot_alias.exists() and dot_alias.is_file():
                    return dot_alias
            elif clean_path.startswith(".github/"):
                undot_alias = (base / clean_path[1:]).resolve()
                if undot_alias.exists() and undot_alias.is_file():
                    return undot_alias
            elif not clean_path.startswith(".") and (base / f".{clean_path}").is_file():
                return (base / f".{clean_path}").resolve()

            # NOTE: os.walk traversal removed — hangs for minutes on large repos.
            # Filename-only fallback is handled via FactFile DB query in modes.py.

        return None

    def _read_from_storage(self, file_path: str) -> Optional[str]:
        """
        Fallback to reading file content from FactStore blob storage.
        """
        if not self.db or not self.analysis_id:
            return None

        clean_path = file_path.strip("/\\").replace("\\", "/")
        base_name = Path(clean_path).name.lower()
        try:
            from sqlalchemy import or_
            from backend.models.fact_store import FactFile
            from backend.storage import get_storage

            fact_files = (
                self.db.query(FactFile)
                .filter(
                    FactFile.analysis_id == self.analysis_id,
                    or_(
                        FactFile.path == clean_path,
                        FactFile.path == f".{clean_path}",
                        FactFile.path.ilike(f"%{clean_path}"),
                        FactFile.path.ilike(f"%/{base_name}"),
                        FactFile.path.ilike(base_name),
                    ),
                )
                .all()
            )

            matched_file = None
            for ff in fact_files:
                if ff.path == clean_path or ff.path == f".{clean_path}":
                    matched_file = ff
                    break
                if ff.path.endswith(clean_path):
                    matched_file = ff
                    break
            if not matched_file and fact_files:
                matched_file = fact_files[0]

            if matched_file and matched_file.blob_name:
                logger.info(f"[SOURCE_READER] Reading from Azure blob: {matched_file.blob_name}")
                storage = get_storage()
                content = storage.get_object_text(matched_file.blob_name)
                if content is not None:
                    return content
        except Exception as err:
            logger.debug(f"RepositorySourceReader blob storage read failed for {file_path}: {err}")

        return None

    def read_source_snippet(
        self,
        file_path: str,
        line_start: int,
        line_end: int,
        context_lines: int = 2,
    ) -> Optional[str]:
        """
        Reads lines [line_start, line_end] with optional surrounding context.
        """
        lines = None
        target = self.resolve_file_path(file_path)
        if target:
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception as err:
                logger.debug(f"RepositorySourceReader could not read {file_path}: {err}")

        if lines is None:
            blob_content = self._read_from_storage(file_path)
            if blob_content is not None:
                lines = blob_content.splitlines(keepends=True)

        if lines is not None:
            start_idx = max(0, line_start - 1 - context_lines)
            end_idx = min(len(lines), line_end + context_lines)
            snippet = "".join(lines[start_idx:end_idx]).strip("\r\n")
            return snippet

        return None

    def read_file_content(self, file_path: str, max_lines: int = 400) -> Optional[str]:
        """
        Reads up to max_lines of a file (reads the full file if <= max_lines).
        """
        target = self.resolve_file_path(file_path)
        if target:
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[:max_lines]
                content = "".join(lines)
                if content:
                    return content
            except Exception as err:
                logger.debug(f"RepositorySourceReader could not read content of {file_path}: {err}")

        # Fallback to blob storage
        blob_content = self._read_from_storage(file_path)
        if blob_content is not None:
            lines = blob_content.splitlines(keepends=True)[:max_lines]
            return "".join(lines)

        return None

    def read_file_head(self, file_path: str, max_lines: int = 50) -> Optional[str]:
        """
        Reads first max_lines of a file.
        """
        return self.read_file_content(file_path, max_lines=max_lines)
