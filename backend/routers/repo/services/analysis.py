import urllib.parse
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.user import User
from backend.models.repository import Repository, Analysis

def resolve_repository(repo_identifier: str, db: Session, current_user: User) -> Repository:
    """
    Resolve repository by name or hash - backwards compatible.

    Supports:
    - UUID hash (repository_hash): Fast direct lookup
    - Integer ID (repository.id)
    - Exact URL
    - URL slug suffix

    Args:
        repo_identifier: Repository hash, ID, URL, or slug
        db: Database session
        current_user: Authenticated user

    Returns:
        Repository object

    Raises:
        HTTPException: If not found or ambiguous
    """
    repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    repo = None

    # Unquote URL-encoded chars if present
    decoded_name = urllib.parse.unquote(repo_identifier).strip()
    clean_name = decoded_name
    if clean_name.lower().startswith("repository "):
        clean_name = clean_name[11:].strip()

    # 1. Direct UUID hash match (most efficient)
    if len(clean_name) == 36:  # UUID format check (8-4-4-4-12)
        hash_match = next((r for r in repos if r.repository_hash == clean_name), None)
        if hash_match:
            repo = hash_match

    # 2. Direct Integer repository.id match
    if not repo and clean_name.isdigit():
        target_int_id = int(clean_name)
        id_match = next((r for r in repos if r.id == target_int_id), None)
        if id_match:
            repo = id_match

    # 3. Exact URL match
    if not repo:
        exact_matches = [
            r for r in repos
            if r.url.rstrip("/").lower() == clean_name.lower()
            or r.url.rstrip("/").lower() == f"https://github.com/{clean_name.lower()}"
            or r.url.rstrip("/").lower() == f"https://github.com/{clean_name.lower()}.git"
        ]
        if len(exact_matches) == 1:
            repo = exact_matches[0]
        elif len(exact_matches) > 1:
            raise HTTPException(status_code=400, detail=f"Ambiguous repository '{repo_identifier}'. {len(exact_matches)} repositories match. Please specify repository hash or ID.")

    # 4. Slug suffix match
    if not repo:
        slug_matches = [
            r for r in repos
            if r.url.rstrip("/").lower().endswith(f"/{clean_name.lower()}")
            or r.url.rstrip("/").lower().endswith(f"/{clean_name.lower()}.git")
        ]
        if len(slug_matches) == 1:
            repo = slug_matches[0]
        elif len(slug_matches) > 1:
            raise HTTPException(status_code=400, detail=f"Ambiguous repository slug '{repo_identifier}'. Found {len(slug_matches)} repositories for this user. Please specify repository hash or ID.")

    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_identifier}' not found")

    return repo

def get_latest_analysis(repo_name: str, db: Session, current_user: User):
    repo = resolve_repository(repo_name, db, current_user)
    latest = db.query(Analysis).filter(Analysis.repository_id == repo.id).order_by(Analysis.created_at.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail=f"No analysis found for repository '{repo_name}'")
    return repo, latest
