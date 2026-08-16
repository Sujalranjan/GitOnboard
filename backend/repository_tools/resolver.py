"""
Repository Path Resolver - Maps repository identity to local snapshot directory if active worktree exists.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session


def resolve_repo_root(
    repo_name: str,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
    custom_root: Optional[Path | str] = None,
) -> Optional[Path]:
    """
    Resolves the filesystem snapshot directory for a given repository.
    Only returns an active worktree / custom root if explicitly passed.
    No permanent local filesystem folder fallback (storage resides in Azure Blob).
    """
    if custom_root:
        p = Path(custom_root).resolve()
        if p.exists() and p.is_dir():
            return p

    return None
