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

import_router = APIRouter(tags=["repositories"])
core_router = APIRouter(tags=["repositories"])

@core_router.get("/{repo_name}/job-progress", include_in_schema=False)
def get_job_progress(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Return current job progress with percentage."""
    try:
        repo, analysis = get_latest_analysis(repo_name, db, current_user)
        job = db.query(AnalysisJob).filter(AnalysisJob.analysis_id == analysis.id).first()

        if not job:
            return {"status": "no_job", "progress": 0}

        # Map status to progress percentage
        status_map = {
            "Queued": 5,
            "Downloading": 20,
            "Analyzing": 50,
            "Saving": 75,
            "Completed": 100,
            "Failed": 0,
            "Cancelled": 0,
        }

        progress = status_map.get(job.status, 0)

        return {
            "job_id": job.id,
            "status": job.status.lower(),  # Lowercase for frontend consistency
            "progress": progress,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error": job.error,
        }
    except HTTPException:
        return {"status": "no_analysis", "progress": 0}

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

    # Check if repo exists
    repo = db.query(Repository).filter(
        Repository.user_id == current_user.id,
        Repository.github_repo_id == limit_data["github_repo_id"]
    ).first()

    if not repo:
        repo = Repository(
            github_repo_id=limit_data["github_repo_id"],
            url=url,
            default_branch=limit_data["default_branch"],
            user_id=current_user.id
        )
        db.add(repo)
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

@core_router.post("/{repo_name}/cancel")
async def cancel_repo_analysis(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    repo = None
    for r in repos:
        if r.url.rstrip("/").endswith(f"/{repo_name}") or r.url.rstrip("/").endswith(f"/{repo_name}.git"):
            repo = r
            break
            
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    unfinished = db.query(AnalysisJob).join(Analysis).filter(
        Analysis.repository_id == repo.id,
        AnalysisJob.status.in_(["Queued", "Downloading", "Analyzing", "Saving"])
    ).first()

    if not unfinished:
        raise HTTPException(status_code=400, detail="No active analysis to cancel.")

    # Cancel task in queue
    from backend.main import repo_queue
    from datetime import datetime, timezone
    
    # Try cancelling the active task. If it returns False, it might be in the queue waiting.
    # We update the DB regardless so the queue loop skips it.
    repo_queue.cancel(unfinished.id)
    
    unfinished.status = "Cancelled"
    unfinished.completed_at = datetime.now(timezone.utc)
    analysis = db.query(Analysis).filter(Analysis.id == unfinished.analysis_id).first()
    if analysis:
        analysis.status = "Cancelled"
    db.commit()

    return {"message": "Analysis cancelled successfully."}

def list_repos(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    results = []
    for r in repos:
        # Get latest analysis status
        all_analyses = db.query(Analysis).filter(Analysis.repository_id == r.id).order_by(Analysis.created_at.desc()).all()
        logger.info(f"[list_repos] {r.url}: Found {len(all_analyses)} analyses")
        for idx, analysis in enumerate(all_analyses[:3]):
            logger.info(f"  [{idx}] Analysis ID={analysis.id}, status={analysis.status}, created_at={analysis.created_at}")

        latest = all_analyses[0] if all_analyses else None
        status = latest.status if latest else "Unknown"
        job_status = "Unknown"
        progress = 0

        if latest:
            jobs = db.query(AnalysisJob).filter(AnalysisJob.analysis_id == latest.id).order_by(AnalysisJob.id.desc()).all()
            logger.info(f"[list_repos] Analysis ID={latest.id} has {len(jobs)} jobs")
            for idx, j in enumerate(jobs[:3]):
                logger.info(f"  Job [{idx}] ID={j.id}, status={j.status}, created_at={j.started_at}")

            job = jobs[0] if jobs else None
            if job:
                job_status = job.status.lower()  # Normalize to lowercase
                # Calculate progress based on job status
                # BACKEND PROGRESS MAP (changed for debugging)
                progress_map = {
                    "queued": 15,      # Backend: 15
                    "downloading": 25, # Backend: 25
                    "analyzing": 55,   # Backend: 55
                    "saving": 85,      # Backend: 85
                    "completed": 100,
                    "failed": 0,
                    "cancelled": 0
                }
                progress = progress_map.get(job_status, 0)
            else:
                job_status = latest.status.lower()
        
        parts = r.url.rstrip("/").split("/")
        repo_name = parts[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        
        # Fetch metadata from enriched_metadata if available
        language_str = "Unknown"
        frameworks = []
        commit = ""
        branch = ""
        
        if latest:
            em_art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == latest.id, AnalysisArtifact.type == "enriched_metadata").first()
            if em_art and em_art.data and "repository" in em_art.data:
                repo_meta = em_art.data["repository"]
                
                if repo_meta.get("primary_language") and repo_meta["primary_language"] != "Unknown":
                    language_str = repo_meta["primary_language"]
                elif "languages" in repo_meta and repo_meta["languages"]:
                    langs_dict = repo_meta["languages"]
                    sorted_langs = sorted(langs_dict.keys(), key=lambda k: langs_dict[k], reverse=True)[:3]
                    language_str = ", ".join(sorted_langs)
                    
                frameworks = repo_meta.get("frameworks", [])
                commit = repo_meta.get("commit", "")
                branch = repo_meta.get("branch", "")

        results.append({
            "id": r.id,
            "project_name": repo_name,
            "url": r.url,
            "status": status,
            "job_status": job_status,
            "progress": progress,
            "import_time": latest.created_at.isoformat() if latest else None,
            "language": language_str,
            "frameworks": frameworks,
            "commit": commit,
            "branch": branch
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

    from backend.services.repo_cleanup import delete_repository_state
    delete_repository_state(repo, repo_name)

    db.delete(repo)
    db.commit()
    return {"message": "Repository deleted successfully"}

@core_router.get("/{repo_name}/summary")
def get_summary(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        repo, analysis = get_latest_analysis(repo_name, db, current_user)
    except HTTPException:
        return {"summary": None, "outdated": False, "status": "not_found"}
    
    current_status = get_task_status(repo_name, "summary", current_user, db) or "idle"
    summary_art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "summary").first()
    
    if not summary_art:
        return {"summary": None, "outdated": False, "status": current_status}
        
    return {"summary": summary_art.data, "outdated": False, "status": "completed"}

@core_router.post("/{repo_name}/summary/generate")
def generate_summary(repo_name: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    set_task_status(repo_name, "summary", "processing", current_user, db)
    
    def background_generate_summary():
        import time
        start_time = time.time()
        # Get a new DB session for the background thread
        import asyncio
        from backend.database import SessionLocal
        from backend.summary import SummaryPipeline
        from backend.repository_tools import resolve_repo_root

        bg_db = SessionLocal()
        try:
            query_layer = get_or_build_model(repo_name, bg_db, current_user)
            repo, analysis = get_latest_analysis(repo_name, bg_db, current_user)
            
            em_art = bg_db.query(AnalysisArtifact).filter(
                AnalysisArtifact.analysis_id == analysis.id,
                AnalysisArtifact.type == "enriched_metadata"
            ).first()
            
            metrics_art = bg_db.query(AnalysisArtifact).filter(
                AnalysisArtifact.analysis_id == analysis.id,
                AnalysisArtifact.type == "metrics"
            ).first()
            metrics = metrics_art.data if metrics_art else {}
            
            if em_art and em_art.data:
                metadata = em_art.data
            else:
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
            
            repo_root = resolve_repo_root(repo_name, user_id=current_user.id, db=bg_db)
            
            pipeline = SummaryPipeline()
            result = asyncio.run(
                pipeline.run(
                    repo_name=repo_name,
                    metadata=metadata,
                    metrics=metrics,
                    repo_root=repo_root,
                    db=bg_db,
                    analysis_id=analysis.id,
                    user_id=current_user.id,
                    enable_progressive_grounding=True,
                )
            )
            
            # Save or update summary artifact
            summary_art = bg_db.query(AnalysisArtifact).filter(
                AnalysisArtifact.analysis_id == analysis.id,
                AnalysisArtifact.type == "summary"
            ).first()
            if summary_art:
                summary_art.data = result.summary_markdown
            else:
                summary_art = AnalysisArtifact(analysis_id=analysis.id, type="summary", data=result.summary_markdown)
                bg_db.add(summary_art)
            bg_db.commit()
            
            elapsed = time.time() - start_time
            logger.info(f"Summary generated successfully for {repo_name} in {elapsed:.2f}s")
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
