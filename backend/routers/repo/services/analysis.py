from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.user import User
from backend.models.repository import Repository, Analysis

def get_latest_analysis(repo_name: str, db: Session, current_user: User):
    repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    repo = None
    for r in repos:
        if r.url.rstrip("/").endswith(f"/{repo_name}") or r.url.rstrip("/").endswith(f"/{repo_name}.git"):
            repo = r
            break
            
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    latest = db.query(Analysis).filter(Analysis.repository_id == repo.id).order_by(Analysis.created_at.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No analysis found for this repository")
    return repo, latest
