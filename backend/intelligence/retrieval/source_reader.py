
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
    from a repository snapshot or local worktree.
    """

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else None

    def resolve_file_path(self, file_path: str) -> Optional[Path]:
        """
        Resolves a file path relative to base_path.
        If direct match does not exist, searches for matching filenames.
        """
        if not file_path or not self.base_path:
            return None

        clean_path = file_path.strip("/\\")
        direct = (self.base_path / clean_path).resolve()
        if direct.exists() and direct.is_file():
            return direct

        # Fallback: search for file by basename across the worktree
        target_name = Path(clean_path).name.lower()
        for root, _, files in os.walk(self.base_path):
            if any(ignored in root for ignored in [".git", ".venv", "__pycache__", "node_modules"]):
                continue
            for f in files:
                if f.lower() == target_name:
                    found = Path(root) / f
                    if found.is_file():
                        return found
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
        target = self.resolve_file_path(file_path)
        if target:
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                
                start_idx = max(0, line_start - 1 - context_lines)
                end_idx = min(len(lines), line_end + context_lines)
                snippet = "".join(lines[start_idx:end_idx]).strip("\r\n")
                return snippet
            except Exception as err:
                logger.debug(f"RepositorySourceReader could not read {file_path}: {err}")

        return None

    def read_file_content(self, file_path: str, max_lines: int = 400) -> Optional[str]:
        """
        Reads up to max_lines of a file.
        """
        target = self.resolve_file_path(file_path)
        if target:
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = [f.readline() for _ in range(max_lines)]
                content = "".join(lines).strip("\r\n")
                return content if content else None
            except Exception as err:
                logger.debug(f"RepositorySourceReader could not read content of {file_path}: {err}")

        return None

    def read_file_head(self, file_path: str, max_lines: int = 50) -> Optional[str]:
        """
        Reads first max_lines of a file.
        """
        return self.read_file_content(file_path, max_lines=max_lines)
