import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.models.repository import Repository, Analysis, AnalysisJob, AnalysisArtifact
from backend.dependencies.auth import get_current_user
from backend.services.github import check_repo_limits
from backend.routers.repo.schemas import ImportRequest
from backend.routers.repo.services.tasks import enqueue_job, get_task_status, set_task_status
from backend.routers.repo.services.analysis import get_latest_analysis
from backend.routers.repo.services.models import get_or_build_model

logger = logging.getLogger(__name__)

import_router = APIRouter()
core_router = APIRouter()

@import_router.post("")
async def import_repo(req: ImportRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    url = req.url
    if not url.startswith("https://github.com/"):
        raise HTTPException(status_code=400, detail="Only GitHub URLs are supported.")

    parts = url.rstrip("/").split("/")
    owner = parts[-2]
    repo_name = parts[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    # Pre-flight check
    try:
        limit_data = await check_repo_limits(owner, repo_name, current_user.github_access_token)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"GitHub API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to communicate with GitHub API.")

    # Check if repo exists by github_repo_id or url
    normalized_url = url.rstrip("/")
    repo = db.query(Repository).filter(
        (Repository.github_repo_id == str(limit_data["github_repo_id"])) | 
        (Repository.url == normalized_url) | 
        (Repository.url == normalized_url + "/")
    ).first()

    if not repo:
        try:
            repo = Repository(
                github_repo_id=str(limit_data["github_repo_id"]),
                url=normalized_url,
                default_branch=limit_data["default_branch"],
                user_id=current_user.id
            )
            db.add(repo)
            db.commit()
            db.refresh(repo)
        except Exception as err:
            db.rollback()
            # Retry fetching existing repo if concurrent insertion occurred
            repo = db.query(Repository).filter(
                (Repository.github_repo_id == str(limit_data["github_repo_id"])) | 
                (Repository.url == normalized_url)
            ).first()
            if not repo:
                logger.error(f"Database insertion failed: {err}")
                raise HTTPException(status_code=500, detail="Database error while registering repository.")
    else:
        # Assign ownership to current_user so the imported repo appears in their dashboard
        if repo.user_id != current_user.id:
            repo.user_id = current_user.id
            db.commit()
            db.refresh(repo)

    # Check for unfinished jobs
    unfinished = db.query(AnalysisJob).join(Analysis).filter(
        Analysis.repository_id == repo.id,
        AnalysisJob.status.in_(["Queued", "Downloading", "Analyzing", "Saving"])
    ).first()

    if unfinished:
        return {"message": "Analysis is already in progress.", "job_id": unfinished.id}

    # Create new analysis
    analysis = Analysis(repository_id=repo.id)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    job = AnalysisJob(analysis_id=analysis.id)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue
    enqueue_job(job.id)

    return {"message": "Repository import queued.", "job_id": job.id, "repo": repo_name}

@core_router.post("/{repo_name}/reanalyze")
async def reanalyze_repo(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    repo = None
    for r in repos:
        if r.url.rstrip("/").endswith(f"/{repo_name}") or r.url.rstrip("/").endswith(f"/{repo_name}.git"):
            repo = r
            break
            
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Check for unfinished jobs
    unfinished = db.query(AnalysisJob).join(Analysis).filter(
        Analysis.repository_id == repo.id,
        AnalysisJob.status.in_(["Queued", "Downloading", "Analyzing", "Saving"])
    ).first()

    if unfinished:
        return {"message": "Analysis is already in progress.", "job_id": unfinished.id}

    analysis = Analysis(repository_id=repo.id)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    job = AnalysisJob(analysis_id=analysis.id)
    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_job(job.id)
    return {"message": "Reanalysis queued.", "job_id": job.id}

def list_repos(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    results = []
    for r in repos:
        # Get latest analysis status
        latest = db.query(Analysis).filter(Analysis.repository_id == r.id).order_by(Analysis.created_at.desc()).first()
        status = latest.status if latest else "Unknown"
        
        parts = r.url.rstrip("/").split("/")
        repo_name = parts[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        
        # Fetch languages from enriched_metadata if available
        language_str = "Unknown"
        if latest:
            em_art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == latest.id, AnalysisArtifact.type == "enriched_metadata").first()
            if em_art and em_art.data and "repository" in em_art.data and "languages" in em_art.data["repository"]:
                langs_dict = em_art.data["repository"]["languages"]
                if langs_dict:
                    # Sort languages by count descending and take top 3
                    sorted_langs = sorted(langs_dict.keys(), key=lambda k: langs_dict[k], reverse=True)[:3]
                    language_str = ", ".join(sorted_langs)

        results.append({
            "id": r.id,
            "project_name": repo_name,
            "url": r.url,
            "status": status,
            "import_time": latest.created_at.isoformat() if latest else None,
            "language": language_str
        })
    return {"repositories": results}

@core_router.delete("/{repo_name}")
def delete_repo(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    repo = None
    for r in repos:
        if r.url.rstrip("/").endswith(f"/{repo_name}") or r.url.rstrip("/").endswith(f"/{repo_name}.git"):
            repo = r
            break
            
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    db.delete(repo)
    db.commit()
    return {"message": "Repository deleted successfully"}

@core_router.get("/{repo_name}/summary")
def get_summary(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        repo, analysis = get_latest_analysis(repo_name, db, current_user)
    except HTTPException:
        return {"summary": None, "outdated": False}
    
    summary_art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "summary").first()
    
    if not summary_art:
        return {"summary": None, "outdated": False}
        
    return {"summary": summary_art.data, "outdated": False}

@core_router.post("/{repo_name}/summary/generate")
def generate_summary(repo_name: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_status = get_task_status(repo_name, "summary", current_user, db)
    if current_status == "processing":
        return {"status": "processing"}
    
    set_task_status(repo_name, "summary", "processing", current_user, db)
    
    def background_generate_summary():
        # Get a new DB session for the background thread
        from backend.database import SessionLocal
        bg_db = SessionLocal()
        try:
            from backend.llm_service import llm_service
            query_layer = get_or_build_model(repo_name, bg_db, current_user)
            
            repo, analysis = get_latest_analysis(repo_name, bg_db, current_user)
            em_art = bg_db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "enriched_metadata").first()
            
            if em_art and em_art.data:
                metadata = em_art.data
            else:
                # Fallback: build basic metadata from existing artifacts
                # This handles repos analyzed before RepositoryMetadataStage was added
                metrics_art = bg_db.query(AnalysisArtifact).filter(
                    AnalysisArtifact.analysis_id == analysis.id,
                    AnalysisArtifact.type == "metrics"
                ).first()
                metrics = metrics_art.data if metrics_art else {}
                
                metadata = {
                    "schema_version": 1,
                    "note": "Basic metadata only. Re-analyze the repository to generate enriched metadata.",
                    "repository": {
                        "name": repo_name,
                    },
                    "statistics": {
                        "files": metrics.get("total_files", "unknown"),
                        "python_files": metrics.get("python_files", "unknown"),
                        "directories": metrics.get("total_directories", "unknown"),
                    },
                    "modules": [
                        {"name": m.get("module", ""), "function_count": m.get("count", 0)}
                        for m in metrics.get("largest_modules", [])[:5]
                    ],
                    "frameworks": [],
                    "entrypoints": [],
                    "architecture": {"style": "unknown", "components": []},
                    "readme_summary": None
                }
            
            summary_md = llm_service.generate_summary(metadata)
            
            # Save or update summary artifact
            summary_art = bg_db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "summary").first()
            if summary_art:
                summary_art.data = summary_md
            else:
                summary_art = AnalysisArtifact(analysis_id=analysis.id, type="summary", data=summary_md)
                bg_db.add(summary_art)
            bg_db.commit()
            
            set_task_status(repo_name, "summary", "completed", current_user, bg_db)
        except Exception as e:
            bg_db.rollback()
            import traceback
            logger.error(f"Summary generation failed: \n{traceback.format_exc()}")
            set_task_status(repo_name, "summary", "failed", current_user, bg_db)
        finally:
            bg_db.close()
            
    background_tasks.add_task(background_generate_summary)
    return {"status": "processing"}
