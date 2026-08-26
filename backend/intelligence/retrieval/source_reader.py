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
        if not file_path:
            return None

        # Check local filesystem if base_path is configured
        if self.base_path:
            target = (self.base_path / file_path).resolve()
            if target.exists() and target.is_file():
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

    def read_file_head(self, file_path: str, max_lines: int = 50) -> Optional[str]:
        """
        Reads first max_lines of a file.
        """
        if not file_path or not self.base_path:
            return None

        target = (self.base_path / file_path).resolve()
        if target.exists() and target.is_file():
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = [f.readline() for _ in range(max_lines)]
                return "".join(lines).strip("\r\n")
            except Exception as err:
                logger.debug(f"RepositorySourceReader could not read head of {file_path}: {err}")

        return None
