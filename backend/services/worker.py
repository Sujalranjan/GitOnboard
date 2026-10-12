import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisJob, AnalysisArtifact
from backend.services.queue import WorkerInterface
from backend.services.github import download_repo_zipball
from backend.intelligence import RepositoryBuilder, RelationshipBuilder, AnalysisPipeline
from backend.intelligence.stages.metrics_stage import MetricsStage

logger = logging.getLogger(__name__)

from backend.services.worker_cleanup import (
    cleanup_orphaned_blobs,
    cleanup_orphaned_database_records,
)
from backend.services.worker_indexing import (
    build_and_record_indexes,
    build_semantic_index_background,
)

def _serialize_dataclass(obj):
    import dataclasses
    from enum import Enum
    if dataclasses.is_dataclass(obj):
        return {k: _serialize_dataclass(v) for k, v in dataclasses.asdict(obj).items()}
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, dict):
        return {k: _serialize_dataclass(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_dataclass(v) for v in obj]
    return obj

class AnalysisWorker(WorkerInterface):
    async def process(self, job_id: int):
        db: Session = SessionLocal()
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if not job:
                logger.error(f"Job {job_id} not found")
                return

            # Safety: Skip if job is already completed (prevent duplicate analysis runs)
            if job.status == "Completed":
                logger.info(f"Job {job_id}: Already completed, skipping duplicate processing")
                return

            analysis = db.query(Analysis).filter(Analysis.id == job.analysis_id).first()
            if analysis and analysis.status == "Completed":
                logger.info(f"Job {job_id}: Analysis already completed, skipping to avoid duplicate work")
                job.status = "Completed"
                db.commit()
                return

            repo = db.query(Repository).filter(Repository.id == analysis.repository_id).first()

            # FIX: Verify repository exists before proceeding
            if not repo:
                logger.error(f"[DESYNC_CLEANUP] Repository ID {analysis.repository_id} not found in database")
                logger.error(f"[DESYNC_CLEANUP] Analysis {job.analysis_id} exists but Repository doesn't")
                logger.error(f"[DESYNC_CLEANUP] Initiating cleanup of orphaned data...")

                repo_id = analysis.repository_id

                # Delete orphaned database records (Analysis and Job)
                try:
                    db.query(AnalysisJob).filter(AnalysisJob.analysis_id == analysis.id).delete()
                    db.query(Analysis).filter(Analysis.id == analysis.id).delete()
                    db.commit()
                    logger.info(f"[DESYNC_CLEANUP] Deleted orphaned Analysis {analysis.id} and Job {job.id} from database")
                except Exception as cleanup_err:
                    logger.error(f"[DESYNC_CLEANUP] Failed to clean up database records: {cleanup_err}")
                    db.rollback()

                # Delete orphaned blobs from Azure (try both possible snapshot IDs)
                for snapshot_id in [f"snap_{analysis.id}", ""]:
                    cleanup_orphaned_blobs(repo_id, snapshot_id)

                raise Exception(f"Repository {repo_id} missing - all orphaned data cleaned up from database and blob storage")

            # FIX: Verify analysis record is still accessible after loading
            analysis_check = db.query(Analysis).filter(Analysis.id == job.analysis_id).first()
            if not analysis_check:
                logger.error(f"[DESYNC_BUG] Analysis {job.analysis_id} is no longer accessible from database")
                job.status = "Failed"
                job.error = "Analysis record not accessible - database issue"
                db.commit()
                raise Exception(f"Analysis {job.analysis_id} not accessible - cannot proceed")

            # Parse owner/repo from url early so we can use repo_name for notifications
            # e.g., https://github.com/owner/repo
            parts = repo.url.rstrip('/').split('/')
            owner = parts[-2]
            repo_name = parts[-1]

            job.status = "Downloading"
            analysis.status = "Downloading"  # Keep Analysis status in sync with job
            job.started_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"Job {job_id}: status → Downloading")

            # Notify SSE subscribers
            from backend.task_manager import task_manager
            task_manager.notify(repo.user_id, repo_name, "import", "downloading")
            
            # TODO: get user token
            from backend.models.user import User
            user = db.query(User).filter(User.id == repo.user_id).first()
            token = user.github_access_token if user else None

            # Create temp dir
            base_tmp = Path("/tmp/repo-analysis")
            base_tmp.mkdir(parents=True, exist_ok=True)
            target_dir = base_tmp / f"job_{job_id}_{repo_name}"

            start_time = datetime.now(timezone.utc)
            repo_id = repo.id
            snapshot_id = None

            try:
                # 1. Download
                try:
                    download_result = await asyncio.wait_for(
                        download_repo_zipball(owner, repo_name, repo.default_branch, str(target_dir), token),
                        timeout=120.0
                    )
                    commit_info = download_result.get("commit_info")
                    # Capture snapshot_id for cleanup if needed later
                    snapshot_id = commit_info.get("hash") if commit_info else f"snap_{analysis.id}"
                except asyncio.TimeoutError:
                    raise Exception("Download timed out after 120 seconds")

                job.status = "Analyzing"
                analysis.status = "Analyzing"  # Keep Analysis status in sync with job
                db.commit()
                logger.info(f"Job {job_id}: status → Analyzing")

                # Notify SSE subscribers
                from backend.task_manager import task_manager
                task_manager.notify(repo.user_id, repo_name, "import", "analyzing")

                # 2. Analyze
                def run_analysis():
                    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
                    from backend.intelligence.engine.analyzers import get_default_registry
                    from backend.intelligence.capabilities.engine import CapabilityBuilderEngine
                    from backend.intelligence.features.engine import FeatureReconstructionEngine
                    from backend.intelligence.rim.serialization import serialize_rim
                    from backend.services.progress_tracker import ProgressTracker

                    # Run Static Analysis Pipeline with progress tracking
                    engine = AnalysisEngine(str(target_dir), get_default_registry())
                    model = engine.run(repo_name, commit_info=commit_info, analysis_id=analysis.id, db=db)

                    # Upload all repository files to Azure Blob Storage / Azurite
                    from backend.storage import get_storage, build_blob_key
                    from backend.intelligence.rim.enums import EntityType
                    from backend.intelligence.rim.entity import Entity
                    from backend.intelligence.rim.location import SourceLocation
                    from backend.intelligence.rim.identity import generate_entity_id
                    import mimetypes
                    import os

                    storage = get_storage()
                    storage.ensure_container_exists()

                    snapshot_id = (commit_info.get("hash") if commit_info else None) or f"snap_{analysis.id}"
                    repo_hash = repo.repository_hash  # Use UUID for blob key consistency

                    # Map existing file entities by relative path
                    file_entities_by_path = {}
                    for e in list(model.entities.values()):
                        if e.type == EntityType.FILE:
                            p = (e.location.repository_path or "").replace("\\", "/").removeprefix("./").lstrip("/")
                            if p:
                                file_entities_by_path[p] = e

                    # Skip critical system dirs (but store non-code files like .gitignore, .env.example, docs)
                    ignored_dirs = {
                        ".git", "node_modules", "venv", ".venv",
                        "build", "dist", "out", "target",
                        "__pycache__", ".pytest_cache", ".tox", ".mypy_cache",
                        "coverage", ".coverage"
                    }
                    code_extensions = {".py", ".js", ".ts", ".tsx", ".jsx"}

                    # Collect ALL files (including non-code), but skip system dirs
                    all_files = []
                    for root, dirs, files in os.walk(target_dir):
                        # Skip ignored system directories only
                        dirs[:] = [d for d in dirs if d not in ignored_dirs]
                        for f in files:
                            full_p = Path(root) / f
                            # Store ALL files to Azure (including hidden files and non-code)
                            if full_p.is_file():
                                all_files.append(full_p)

                    progress = ProgressTracker(db, analysis.id)
                    total_files = len(all_files)

                    # INSTRUMENTATION: Log file discovery
                    logger.info(f"[INSTRUMENTATION] Physical files discovered: {total_files}")
                    logger.info(f"[INSTRUMENTATION] RIM FILE entities before upload: {len(file_entities_by_path)}")

                    # Upload files with progress tracking
                    upload_stats = {
                        "attempted": 0,
                        "successful": 0,
                        "failed": 0,
                        "object_exists_failed": 0,
                        "exceptions": []
                    }

                    for file_idx, full_p in enumerate(all_files):
                        rel_p = str(full_p.relative_to(target_dir)).replace("\\", "/").removeprefix("./").lstrip("/")
                        upload_stats["attempted"] += 1

                        try:
                            blob_key = build_blob_key(repo_hash, snapshot_id, rel_p)
                            content_type, _ = mimetypes.guess_type(str(full_p))
                            content_type = content_type or "text/plain"
                            file_size = full_p.stat().st_size

                            # Upload to Azure blob storage (silently)
                            with open(full_p, "rb") as fh:
                                storage.put_object(blob_key, fh, content_type=content_type)

                            logger.debug(f"[INSTRUMENTATION] put_object succeeded for: {rel_p} ({file_size} bytes)")

                            # Verify blob exists in storage before recording in database
                            blob_exists_result = storage.object_exists(blob_key)
                            if not blob_exists_result:
                                upload_stats["object_exists_failed"] += 1
                                raise FileNotFoundError(f"Blob upload succeeded but verification failed: {blob_key} not found in storage")

                            logger.debug(f"[INSTRUMENTATION] object_exists returned True for: {rel_p}")
                            upload_stats["successful"] += 1

                            # Create or update file entity
                            f_ent = file_entities_by_path.get(rel_p)
                            if not f_ent:
                                logger.info(f"[INSTRUMENTATION] Creating new FILE entity for: {rel_p} (was in all_files but not in RIM)")
                                f_id = generate_entity_id(EntityType.FILE, rel_p, rel_p)
                                f_ent = Entity(
                                    id=f_id,
                                    type=EntityType.FILE,
                                    name=full_p.name,
                                    qualified_name=rel_p,
                                    location=SourceLocation(
                                        repository_path=rel_p,
                                        start_line=1,
                                        end_line=1,
                                        language=""
                                    ),
                                    metadata={}
                                )
                                model.entities[f_id] = f_ent
                                file_entities_by_path[rel_p] = f_ent

                            # Only record blob_name after successful upload AND verification
                            f_ent.metadata["blob_name"] = blob_key
                            f_ent.metadata["snapshot_id"] = snapshot_id
                            f_ent.metadata["content_type"] = content_type
                            f_ent.metadata["size"] = file_size

                            # Update progress every ~10 files or at end
                            if file_idx % 10 == 0 or file_idx == total_files - 1:
                                progress.update(
                                    "Persisting facts",
                                    f"Uploading repository files",
                                    file_idx + 1,
                                    total_files,
                                    "files"
                                )
                        except Exception as up_err:
                            upload_stats["failed"] += 1
                            error_msg = f"[BLOB_FAILED] Failed to upload blob for {rel_p}: {type(up_err).__name__}: {up_err}"
                            logger.error(error_msg)
                            upload_stats["exceptions"].append({
                                "path": rel_p,
                                "exception_type": type(up_err).__name__,
                                "message": str(up_err)
                            })

                    # INSTRUMENTATION: Log upload summary
                    logger.info(f"[INSTRUMENTATION] Upload summary: {upload_stats['successful']}/{upload_stats['attempted']} successful, {upload_stats['failed']} failed, {upload_stats['object_exists_failed']} object_exists failures")
                    logger.info(f"[INSTRUMENTATION] RIM FILE entities after upload: {len(file_entities_by_path)}")

                    # Run Capability Engine
                    capability_engine = CapabilityBuilderEngine()
                    model = capability_engine.run(model)

                    # Run Feature Reconstruction Engine
                    feature_engine = FeatureReconstructionEngine()
                    model = feature_engine.run(model)
                    
                    # Serialize the populated RIM
                    json_str = serialize_rim(model)
                    
                    # Generate Enriched Metadata
                    languages_dict = {lang: 1 for lang in model.metadata.languages}
                    enriched_metadata = {
                        "schema_version": 2,
                        "repository": {
                            "name": model.metadata.name,
                            "languages": languages_dict,
                            "primary_language": model.metadata.metadata.get("primary_language", "Unknown"),
                            "frameworks": model.metadata.metadata.get("frameworks", []),
                            "commit": model.metadata.commit,
                            "branch": model.metadata.branch
                        }
                    }
                    
                    # Generate metrics
                    from backend.intelligence.rim.enums import EntityType
                    import os
                    files = [e for e in model.entities.values() if e.type == EntityType.FILE]
                    functions = [e for e in model.entities.values() if e.type == EntityType.FUNCTION]
                    classes = [e for e in model.entities.values() if e.type == EntityType.CLASS]
                        
                    lines_of_code = 0
                    largest_files = []
                    for f in files:
                        path = os.path.join(str(target_dir), f.location.repository_path)
                        size = 0
                        if os.path.exists(path):
                            size = os.path.getsize(path)
                            try:
                                with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                                    lines_of_code += sum(1 for _ in fh)
                            except:
                                pass
                        largest_files.append({"file": f.location.repository_path, "size": size})
                        
                    largest_files.sort(key=lambda x: x["size"], reverse=True)
                    largest_files = largest_files[:5]
                    
                    module_funcs = {}
                    for fn in functions:
                        file_id = fn.metadata.get("file_id", fn.location.repository_path)
                        module_funcs[file_id] = module_funcs.get(file_id, 0) + 1
                    
                    largest_modules = [{"module": k, "functions": v} for k, v in module_funcs.items()]
                    largest_modules.sort(key=lambda x: x["functions"], reverse=True)
                    largest_modules = largest_modules[:5]
                    
                    avg_complexity = lines_of_code / max(1, len(functions))
                    
                    metrics_data = {
                        "total_files": len(files),
                        "lines_of_code": lines_of_code,
                        "total_functions": len(functions),
                        "total_classes": len(classes),
                        "total_modules": len(module_funcs) or len(files),
                        "test_coverage_approx_percent": 0.0,
                        "documentation_coverage_percent": 0.0,
                        "average_cyclomatic_complexity": round(avg_complexity, 2),
                        "largest_files": largest_files,
                        "largest_modules": largest_modules
                    }
                    
                    return {
                        "core_model": json_str.encode("utf-8"),
                        "metrics": metrics_data,
                        "enriched_metadata": enriched_metadata,
                        "rim_model": model
                    }

                logger.info(f"Analyzing {repo_name}...")
                results = await asyncio.wait_for(
                    asyncio.to_thread(run_analysis),
                    timeout=600.0 # 10 min
                )

                job.status = "Saving"
                analysis.status = "Saving"  # Keep Analysis status in sync with job
                db.commit()
                logger.info(f"Job {job_id}: status → Saving")

                # Notify SSE subscribers
                from backend.task_manager import task_manager
                task_manager.notify(repo.user_id, repo_name, "import", "saving")

                # 3. Save artifacts & canonical Layer 4 Fact Store
                logger.info("Saving artifacts and canonical Fact Store tables...")
                rim_model = results.pop("rim_model", None)

                # Initialize progress tracker for persistence phase
                from backend.services.progress_tracker import ProgressTracker
                progress = ProgressTracker(db, analysis.id)

                if rim_model:
                    exact_ok, bm25_ok, semantic_ok = build_and_record_indexes(
                        db=db,
                        analysis=analysis,
                        rim_model=rim_model,
                        results=results,
                        progress=progress,
                    )

                for art_type, data in results.items():
                    if isinstance(data, bytes):
                        art = AnalysisArtifact(
                            analysis_id=analysis.id,
                            type=art_type,
                            data={},
                            blob_data=data
                        )
                    else:
                        art = AnalysisArtifact(
                            analysis_id=analysis.id,
                            type=art_type,
                            data=_serialize_dataclass(data)
                        )
                    db.add(art)

                # Update Analysis
                analysis.status = "Completed"

                job.status = "Completed"
                job.completed_at = datetime.now(timezone.utc)

                # Mark progress as 100% complete
                progress.mark_complete()

                db.commit()
                logger.info(f"Job {job_id}: status → Completed")
                logger.info(f"Job {job_id} completed successfully.")

                # Clean up PostgreSQL temporary work files immediately
                # (prevents 1-2GB temp file accumulation per analysis)
                try:
                    import shutil
                    import os
                    pg_tmp_path = Path("/var/lib/postgresql/data/base/pgsql_tmp")
                    if pg_tmp_path.exists():
                        for tmp_file in pg_tmp_path.glob("pgsql_tmp*"):
                            try:
                                if tmp_file.is_file():
                                    tmp_file.unlink()
                                    logger.debug(f"Cleaned temp file: {tmp_file.name}")
                            except Exception:
                                pass
                except Exception as cleanup_err:
                    logger.debug(f"PostgreSQL temp cleanup note: {cleanup_err}")

                # Queue semantic indexing as background job (non-blocking, silent)
                # Runs after analysis is marked READY, doesn't interfere with retrieval
                if rim_model:
                    import threading
                    semantic_bg_thread = threading.Thread(
                        target=self._build_semantic_index_background,
                        args=(analysis.id,),  # Don't pass stale db session
                        daemon=False  # FIX: Make it non-daemon so it completes
                    )
                    semantic_bg_thread.start()
                    logger.info(f"Analysis {analysis.id}: Semantic indexing queued for background processing")

                # Notify SSE subscribers of completion
                from backend.task_manager import task_manager
                task_manager.notify(repo.user_id, repo_name, "import", "completed")

                # Record commit & analysis summary in dedicated log file
                try:
                    from backend.logger import log_commit_analysis
                    duration = (job.completed_at - start_time).total_seconds() if 'start_time' in locals() else 0.0
                    total_f = len(rim_model.entities) if rim_model else 0
                    log_commit_analysis(repo_name, commit_info, analysis.id, "Completed", file_count=total_f, duration_seconds=duration)
                except Exception as log_err:
                    logger.debug(f"Commit logging error: {log_err}")

            except Exception as e:
                import traceback
                logger.error(f"Job {job_id} failed: {traceback.format_exc()}")

                # DESYNC CLEANUP: Handle different failure scenarios
                error_msg = str(e)

                # Scenario 1: Blob upload/analysis failed → Clean both database and blobs
                if "Blob" in error_msg or "blob" in error_msg or "Azure" in error_msg or "storage" in error_msg:
                    logger.error(f"[DESYNC_CLEANUP] Blob storage error detected - cleaning up orphaned data...")

                    # Clean database records
                    if 'analysis' in locals() and analysis:
                        try:
                            db.query(AnalysisJob).filter(AnalysisJob.id == job_id).delete()
                            db.query(Analysis).filter(Analysis.id == analysis.id).delete()
                            db.commit()
                            logger.info(f"[DESYNC_CLEANUP] Deleted orphaned Analysis {analysis.id} from database")
                        except Exception as cleanup_err:
                            logger.error(f"[DESYNC_CLEANUP] Failed to clean database: {cleanup_err}")
                            db.rollback()

                    # Clean blobs from Azure
                    if snapshot_id and repo_id:
                        cleanup_orphaned_blobs(repo_id, snapshot_id)

                # Scenario 2: Database/persistence error → Clean database records and blobs
                elif "database" in error_msg.lower() or "persist" in error_msg.lower() or "commit" in error_msg.lower():
                    logger.error(f"[DESYNC_CLEANUP] Database error detected - cleaning up orphaned data...")

                    # Clean database records
                    if 'analysis' in locals() and analysis:
                        try:
                            db.query(AnalysisJob).filter(AnalysisJob.id == job_id).delete()
                            db.query(Analysis).filter(Analysis.id == analysis.id).delete()
                            db.commit()
                            logger.info(f"[DESYNC_CLEANUP] Deleted orphaned Analysis {analysis.id} from database")
                        except Exception as cleanup_err:
                            logger.error(f"[DESYNC_CLEANUP] Failed to clean database: {cleanup_err}")
                            db.rollback()

                    # Clean blobs from Azure
                    if repo_id:
                        cleanup_orphaned_blobs(repo_id, snapshot_id or "")

                # Scenario 3: Any other error → Try to clean both
                else:
                    logger.warning(f"[DESYNC_CLEANUP] Unknown error type - attempting comprehensive cleanup...")

                    # Clean database
                    if 'analysis' in locals() and analysis:
                        try:
                            db.query(AnalysisJob).filter(AnalysisJob.id == job_id).delete()
                            db.query(Analysis).filter(Analysis.id == analysis.id).delete()
                            db.commit()
                            logger.info(f"[DESYNC_CLEANUP] Deleted orphaned Analysis {analysis.id} from database")
                        except Exception as cleanup_err:
                            logger.error(f"[DESYNC_CLEANUP] Failed to clean database: {cleanup_err}")
                            db.rollback()

                    # Clean blobs
                    if repo_id:
                        cleanup_orphaned_blobs(repo_id, snapshot_id or "")

                # Update job status after cleanup
                try:
                    job.status = "Failed"
                    job.error = str(e)
                    job.completed_at = datetime.now(timezone.utc)
                    analysis.status = "Failed"
                    db.commit()
                except:
                    pass

                # Notify SSE subscribers of failure
                from backend.task_manager import task_manager
                task_manager.notify(repo.user_id, repo_name, "import", "failed")

                try:
                    from backend.logger import log_commit_analysis
                    duration = (job.completed_at - start_time).total_seconds() if 'start_time' in locals() else 0.0
                    log_commit_analysis(repo_name, commit_info if 'commit_info' in locals() else None, analysis.id if 'analysis' in locals() else 0, "Failed", duration_seconds=duration)
                except Exception:
                    pass
            finally:
                # Clean up temporary worktree
                if target_dir.exists():
                    try:
                        logger.info(f"[CLEANUP] Removing temporary worktree: {target_dir}")
                        shutil.rmtree(target_dir, ignore_errors=True)
                        if not target_dir.exists():
                            logger.info(f"[CLEANUP] Worktree cleanup successful: {target_dir}")
                        else:
                            logger.warning(f"[CLEANUP] Worktree cleanup failed - directory still exists: {target_dir}")
                    except Exception as cleanup_err:
                        logger.error(f"[CLEANUP] Exception during worktree cleanup: {type(cleanup_err).__name__}: {cleanup_err}")
                else:
                    logger.info(f"[CLEANUP] Temporary worktree already removed: {target_dir}")

        except Exception as e:
            logger.error(f"Critical worker error on job {job_id}: {e}")
        finally:
            db.close()

    def _build_semantic_index_background(self, analysis_id: int):
        return build_semantic_index_background(analysis_id)
