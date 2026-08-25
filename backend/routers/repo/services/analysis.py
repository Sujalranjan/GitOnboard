import urllib.parse
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.user import User
from backend.models.repository import Repository, Analysis

def get_latest_analysis(repo_name: str, db: Session, current_user: User):
    repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    repo = None

    # Unquote URL-encoded chars if present
    decoded_name = urllib.parse.unquote(repo_name).strip()
    clean_name = decoded_name
    if clean_name.lower().startswith("repository "):
        clean_name = clean_name[11:].strip()

    # 1. Direct Integer repository.id match
    if clean_name.isdigit():
        target_int_id = int(clean_name)
        id_match = next((r for r in repos if r.id == target_int_id), None)
        if id_match:
            repo = id_match

    # 2. Exact URL match
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
            raise HTTPException(status_code=400, detail=f"Ambiguous repository '{repo_name}'. Multiple matches found. Please specify repository ID.")

    # 3. Slug suffix match
    if not repo:
        slug_matches = [
            r for r in repos
            if r.url.rstrip("/").lower().endswith(f"/{clean_name.lower()}")
            or r.url.rstrip("/").lower().endswith(f"/{clean_name.lower()}.git")
        ]
        if len(slug_matches) == 1:
            repo = slug_matches[0]
        elif len(slug_matches) > 1:
            raise HTTPException(status_code=400, detail=f"Ambiguous repository slug '{repo_name}'. Found {len(slug_matches)} repositories for this user. Please specify repository ID.")

    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    latest = db.query(Analysis).filter(Analysis.repository_id == repo.id).order_by(Analysis.created_at.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail=f"No analysis found for repository '{repo_name}'")
    return repo, latest
