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

    for r in repos:
        r_url = r.url.rstrip("/").lower()
        # Check various name formats
        if (
            r_url.endswith(f"/{clean_name.lower()}")
            or r_url.endswith(f"/{clean_name.lower()}.git")
            or r_url.endswith(f"/{decoded_name.lower()}")
            or r_url.endswith(f"/{decoded_name.lower()}.git")
            or f"/{clean_name.lower()}" in r_url
            or f"/{decoded_name.lower()}" in r_url
        ):
            repo = r
            break

    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    latest = db.query(Analysis).filter(Analysis.repository_id == repo.id).order_by(Analysis.created_at.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail=f"No analysis found for repository '{repo_name}'")
    return repo, latest
