"""
Repository Path Resolver - Maps repository identity to local snapshot directory.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session

from backend.models.repository import Repository, Analysis

BASE_DIR = Path(__file__).parent.parent.parent.resolve()


def resolve_repo_root(
    repo_name: str,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
    custom_root: Optional[Path | str] = None,
) -> Optional[Path]:
    """
    Resolves the filesystem snapshot directory for a given repository.
    Checks multiple standard snapshot locations:
      1. custom_root (if explicitly passed, e.g., in test fixtures)
      2. data/repos/{user_id}_{repo_name}/source
      3. data/repos/{user_id}_{repo_name}
      4. data/repos/{repo_name}
    """
    if custom_root:
        p = Path(custom_root).resolve()
        if p.exists() and p.is_dir():
            return p

    # If user_id is not passed, attempt lookup in database
    if user_id is None and db is not None:
        repo = db.query(Repository).filter(Repository.url.contains(repo_name)).first()
        if repo:
            user_id = repo.user_id

    repos_dir = BASE_DIR / "data" / "repos"

    candidate_paths = []
    if user_id is not None:
        candidate_paths.append(repos_dir / f"{user_id}_{repo_name}" / "source")
        candidate_paths.append(repos_dir / f"{user_id}_{repo_name}")

    candidate_paths.append(repos_dir / repo_name / "source")
    candidate_paths.append(repos_dir / repo_name)

    for cand in candidate_paths:
        if cand.exists() and cand.is_dir():
            return cand.resolve()

    return None
