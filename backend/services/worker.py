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
            try:
                # 1. Download
                try:
                    download_result = await asyncio.wait_for(
                        download_repo_zipball(owner, repo_name, repo.default_branch, str(target_dir), token),
                        timeout=120.0
                    )
                    commit_info = download_result.get("commit_info")
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
                    repo_id = repo.id

                    # Map existing file entities by relative path
                    file_entities_by_path = {}
                    for e in list(model.entities.values()):
                        if e.type == EntityType.FILE:
                            p = (e.location.repository_path or "").replace("\\", "/").removeprefix("./").lstrip("/")
                            if p:
                                file_entities_by_path[p] = e

                    # Only upload code files, skip dot-folders and build artifacts
                    ignored_dirs = {
                        ".git", ".gitignore", ".github",
                        "node_modules", "venv", ".venv", ".env",
                        "build", "dist", "out", "target",
                        "__pycache__", ".pytest_cache", ".tox", ".mypy_cache",
                        ".vscode", ".idea", ".next", ".nuxt", "coverage", ".coverage"
                    }
                    code_extensions = {".py", ".js", ".ts", ".tsx", ".jsx"}

                    # Count total files for progress tracking (code files only)
                    all_files = []
                    for root, dirs, files in os.walk(target_dir):
                        # Skip ignored directories and dot-folders
                        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
                        for f in files:
                            # Skip hidden files and non-code files
                            if f.startswith("."):
                                continue
                            full_p = Path(root) / f
                            # Only upload code files
                            if full_p.suffix.lower() in code_extensions and full_p.is_file():
                                all_files.append(full_p)

                    progress = ProgressTracker(db, analysis.id)
                    total_files = len(all_files)

                    # Upload files with progress tracking
                    for file_idx, full_p in enumerate(all_files):
                        rel_p = str(full_p.relative_to(target_dir)).replace("\\", "/").removeprefix("./").lstrip("/")
                        try:
                            blob_key = build_blob_key(repo_id, snapshot_id, rel_p)
                            content_type, _ = mimetypes.guess_type(str(full_p))
                            content_type = content_type or "text/plain"
                            file_size = full_p.stat().st_size

                            # Upload to Azure blob storage
                            with open(full_p, "rb") as fh:
                                logger.info(f"[BLOB_UPLOAD] Uploading {rel_p} to blob: {blob_key}")
                                storage.put_object(blob_key, fh, content_type=content_type)

                            # Verify blob exists in storage before recording in database
                            logger.info(f"[BLOB_VERIFY] Verifying blob exists: {blob_key}")
                            if not storage.object_exists(blob_key):
                                raise FileNotFoundError(f"Blob upload succeeded but verification failed: {blob_key} not found in storage")
                            logger.info(f"[BLOB_VERIFY] Blob verified: {blob_key} exists in storage")

                            # Create or update file entity
                            f_ent = file_entities_by_path.get(rel_p)
                            if not f_ent:
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
                            logger.info(f"[BLOB_RECORD] Recorded blob_name in metadata: {blob_key}")

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
                            logger.error(f"[BLOB_FAILED] Failed to upload blob for {rel_p}: {type(up_err).__name__}: {up_err}")

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

                # Track indexing health
                from backend.intelligence.retrieval.indexing_health import (
                    IndexStatus, OverallIndexingStatus, IndexFailureCode,
                    IndexingHealthReport, IndexHealthSnapshot, record_indexing_failure,
                    compute_overall_status
                )

                exact_ok = False
                bm25_ok = False
                semantic_ok = False

                if rim_model:
                    try:
                        from backend.intelligence.store.fact_store import save_rim_to_fact_store
                        save_rim_to_fact_store(db, analysis.id, rim_model)
                        entity_count = len(rim_model.entities)
                        logger.info(f"Saved {entity_count} entities to Fact Store")
                        exact_ok = True  # Exact search depends on FactStore

                        # Update progress after persistence
                        progress.update(
                            "Persisting facts",
                            f"Saved {entity_count} entities to database",
                            entity_count,
                            entity_count,
                            "entities"
                        )
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Error persisting facts to Fact Store: {e}")

                    # Generate immutability version for FactStore
                    # This ensures BM25 built now corresponds to current FactStore
                    analysis.fact_store_version = str(uuid.uuid4())

                    # Build retrieval indexes (BM25 and Chroma) for this analysis
                    logger.info("Building semantic and lexical indexes...")

                    bm25_doc_count = 0
                    bm25_error_code = None
                    bm25_error_msg = ""

                    semantic_doc_count = 0
                    semantic_error_code = None
                    semantic_error_msg = ""

                    try:
                        from backend.intelligence.retrieval.retriever import HybridRetriever

                        # Build BM25 index and store in memory for export
                        try:
                            retriever_temp = HybridRetriever(db=db, analysis_id=analysis.id)
                            if retriever_temp.bm25_index:
                                bm25_doc_count = retriever_temp.bm25_index.corpus_size
                                bm25_data = {
                                    "documents": retriever_temp.bm25_index.documents,
                                    "idf": dict(retriever_temp.bm25_index.idf),
                                    "doc_len": retriever_temp.bm25_index.doc_len,
                                    "corpus_size": retriever_temp.bm25_index.corpus_size,
                                    "avg_doc_len": retriever_temp.bm25_index.avg_doc_len,
                                    "fact_store_version": analysis.fact_store_version,  # Store version for staleness check
                                }
                                results["bm25_index"] = bm25_data
                                logger.info(f"BM25 index ready with {bm25_doc_count} documents (version={analysis.fact_store_version[:8]}...)")

                                # Update progress for BM25 indexing
                                progress.update(
                                    "Building indexes",
                                    f"Built BM25 index with {bm25_doc_count} documents",
                                    bm25_doc_count,
                                    bm25_doc_count,
                                    "documents"
                                )
                                bm25_ok = True
                            else:
                                if not rim_model.entities:
                                    bm25_error_code = IndexFailureCode.BM25_EMPTY_FACTSTORE
                                    bm25_error_msg = "No entities in FactStore"
                                else:
                                    bm25_error_code = IndexFailureCode.BM25_BUILD_FAILED
                                    bm25_error_msg = "BM25 index creation returned None"
                                record_indexing_failure(analysis.id, "bm25", bm25_error_code, bm25_error_msg)
                        except Exception as bm25_err:
                            bm25_error_code = IndexFailureCode.BM25_BUILD_FAILED
                            bm25_error_msg = str(bm25_err)[:100]
                            record_indexing_failure(analysis.id, "bm25", bm25_error_code, bm25_error_msg)

                        # Build Chroma semantic index (BACKGROUND, NON-BLOCKING)
                        # Semantic indexing is optional and will run async after analysis completes
                        logger.info("Semantic (Chroma) indexing: SCHEDULED for background processing (non-blocking)")
                        semantic_error_code = IndexFailureCode.CHROMA_UNAVAILABLE
                        semantic_error_msg = "Semantic indexing scheduled for background (non-blocking)"
                        # Don't block on semantic indexing - let it run after analysis READY
                        # semantic_ok remains False, which results in PARTIAL overall status

                    except Exception as e:
                        logger.error(f"Failed to build retrieval indexes: {e}", exc_info=True)
                        if not bm25_ok and not bm25_error_code:
                            bm25_error_code = IndexFailureCode.BM25_BUILD_FAILED
                            bm25_error_msg = str(e)[:100]
                        if not semantic_ok and not semantic_error_code:
                            semantic_error_code = IndexFailureCode.CHROMA_BUILD_FAILED
                            semantic_error_msg = str(e)[:100]

                    # Record indexing health
                    overall_status = compute_overall_status(exact_ok, bm25_ok, semantic_ok)
                    health_report = IndexingHealthReport(
                        overall_status=overall_status,
                        exact=IndexHealthSnapshot(
                            status=IndexStatus.SUCCESS if exact_ok else IndexStatus.FAILED,
                            document_count=len(rim_model.entities) if exact_ok else 0,
                        ),
                        bm25=IndexHealthSnapshot(
                            status=IndexStatus.SUCCESS if bm25_ok else IndexStatus.FAILED,
                            document_count=bm25_doc_count,
                            error_code=bm25_error_code,
                            error_message=bm25_error_msg,
                            created_at=datetime.now(timezone.utc),
                        ),
                        semantic=IndexHealthSnapshot(
                            status=IndexStatus.SUCCESS if semantic_ok else (
                                IndexStatus.UNAVAILABLE if semantic_error_code == IndexFailureCode.CHROMA_UNAVAILABLE else IndexStatus.FAILED
                            ),
                            document_count=semantic_doc_count,
                            error_code=semantic_error_code,
                            error_message=semantic_error_msg,
                            created_at=datetime.now(timezone.utc),
                        ),
                    )

                    analysis.indexing_status = overall_status.value
                    analysis.indexing_details = health_report.to_dict()
                    analysis.indexed_at = datetime.now(timezone.utc)
                    logger.info(f"Indexing health: overall={overall_status.value} exact={exact_ok} bm25={bm25_ok} semantic={semantic_ok}")

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
                if rim_model and rim_model.entities:
                    import threading
                    semantic_bg_thread = threading.Thread(
                        target=self._build_semantic_index_background,
                        args=(analysis.id, rim_model.entities, db),
                        daemon=True
                    )
                    semantic_bg_thread.start()
                    logger.debug(f"Analysis {analysis.id}: Semantic indexing queued for background processing")

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
                job.status = "Failed"
                job.error = str(e)
                job.completed_at = datetime.now(timezone.utc)
                analysis.status = "Failed"  # Already set above, just confirming
                db.commit()

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

    def _build_semantic_index_background(self, analysis_id: int, entities: dict, db: Session):
        """
        Build semantic (Chroma) index in background thread.

        Runs after analysis is marked COMPLETED, non-blocking.
        Stores semantic index in analysis_artifacts when complete.
        """
        logger.info(f"Analysis {analysis_id}: Background semantic indexing started (silent)")
        try:
            from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder
            from backend.models.repository import AnalysisArtifact

            builder = SemanticIndexBuilder()
            chroma_bytes = builder.build_index(entities)

            if chroma_bytes:
                # Store in database
                db_session = SessionLocal()
                try:
                    artifact = AnalysisArtifact(
                        analysis_id=analysis_id,
                        type="semantic_index_db",
                        data={},
                        blob_data=chroma_bytes
                    )
                    db_session.add(artifact)
                    db_session.commit()
                    logger.info(f"Analysis {analysis_id}: Semantic index built and stored ({len(chroma_bytes)} bytes)")
                except Exception as db_err:
                    logger.warning(f"Analysis {analysis_id}: Failed to store semantic index: {db_err}")
                    db_session.rollback()
                finally:
                    db_session.close()
            else:
                logger.debug(f"Analysis {analysis_id}: Semantic index build returned None")
        except ImportError:
            logger.debug(f"Analysis {analysis_id}: chromadb not available for semantic indexing")
        except Exception as bg_err:
            logger.debug(f"Analysis {analysis_id}: Background semantic indexing error: {bg_err}")
