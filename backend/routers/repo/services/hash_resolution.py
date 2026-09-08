"""
Repository Hash Resolution - Replace ambiguous name-based resolution with UUID-based.

All tools use repository_hash (UUID) for unambiguous, production-ready identification.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from typing import Tuple


def get_repo_by_hash(repo_hash: str, db: Session, current_user: User) -> Repository:
    """
    Resolve repository by UUID hash - unambiguous, always works.

    Args:
        repo_hash: UUID v4 of repository
        db: Database session
        current_user: Authenticated user

    Returns:
        Repository object

    Raises:
        HTTPException 404: If repo_hash not found
    """
    repo = db.query(Repository).filter(
        Repository.repository_hash == repo_hash
    ).first()

    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repository not found: {repo_hash}"
        )

    # Verify user has access (optional - remove if multi-tenant not required)
    if repo.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Access denied to this repository"
        )

    return repo


def get_latest_analysis_by_hash(
    repo_hash: str,
    db: Session,
    current_user: User,
    require_completed: bool = True
) -> Tuple[Repository, Analysis]:
    """
    Get repository and its latest analysis using UUID hash.

    Args:
        repo_hash: UUID v4 of repository
        db: Database session
        current_user: Authenticated user
        require_completed: If True, only return completed analyses

    Returns:
        Tuple of (Repository, Analysis)

    Raises:
        HTTPException 404: If repo or analysis not found
    """
    repo = get_repo_by_hash(repo_hash, db, current_user)

    query = db.query(Analysis).filter(Analysis.repository_id == repo.id)

    if require_completed:
        query = query.filter(Analysis.status == "Completed")

    analysis = query.order_by(Analysis.created_at.desc()).first()

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"No {'completed ' if require_completed else ''}analysis found for repository: {repo_hash}"
        )

    return repo, analysis
