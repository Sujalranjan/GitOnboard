import asyncio
import logging
import os
import shutil
import tempfile
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

            analysis = db.query(Analysis).filter(Analysis.id == job.analysis_id).first()
            repo = db.query(Repository).filter(Repository.id == analysis.repository_id).first()

            job.status = "Downloading"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

            # Parse owner/repo from url
            # e.g., https://github.com/owner/repo
            parts = repo.url.rstrip('/').split('/')
            owner = parts[-2]
            repo_name = parts[-1]
            
            # TODO: get user token
            from backend.models.user import User
            user = db.query(User).filter(User.id == repo.user_id).first()
            token = user.github_access_token if user else None

            # Create temp dir
            base_tmp = Path("/tmp/repo-analysis")
            base_tmp.mkdir(parents=True, exist_ok=True)
            target_dir = base_tmp / f"job_{job_id}_{repo_name}"

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
                db.commit()

                # 2. Analyze
                def run_analysis():
                    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
                    from backend.intelligence.engine.analyzers import get_default_registry
                    from backend.intelligence.patterns.engine import PatternRecognitionEngine
                    from backend.intelligence.patterns.registry import PatternRegistry
                    from backend.intelligence.capabilities.engine import CapabilityBuilderEngine
                    from backend.intelligence.features.engine import FeatureReconstructionEngine
                    from backend.intelligence.rim.serialization import serialize_rim
                    
                    # Run Phase 2 Static Analysis Pipeline
                    engine = AnalysisEngine(str(target_dir), get_default_registry())
                    model = engine.run(repo_name, commit_info=commit_info)
                    
                    # Run Phase 3 Pattern Recognition Engine
                    pattern_registry = PatternRegistry()
                    pattern_engine = PatternRecognitionEngine(pattern_registry)
                    model = pattern_engine.run(model)
                    
                    # Run Phase 4 Capability Engine
                    capability_engine = CapabilityBuilderEngine()
                    model = capability_engine.run(model)
                    
                    # Run Phase 5 Feature Reconstruction Engine
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
                db.commit()

                # 3. Save artifacts & canonical Layer 4 Fact Store
                logger.info("Saving artifacts and canonical Fact Store tables...")
                rim_model = results.pop("rim_model", None)
                if rim_model:
                    try:
                        from backend.intelligence.store.fact_store import save_rim_to_fact_store
                        save_rim_to_fact_store(db, analysis.id, rim_model)
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Error persisting facts to Fact Store: {e}")
                
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
                db.commit()
                logger.info(f"Job {job_id} completed successfully.")

            except Exception as e:
                import traceback
                logger.error(f"Job {job_id} failed: {traceback.format_exc()}")
                job.status = "Failed"
                job.error = str(e)
                job.completed_at = datetime.now(timezone.utc)
                analysis.status = "Failed"
                db.commit()
            finally:
                if target_dir.exists():
                    shutil.rmtree(target_dir, ignore_errors=True)

        except Exception as e:
            logger.error(f"Critical worker error on job {job_id}: {e}")
        finally:
            db.close()
