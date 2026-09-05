#!/usr/bin/env python3
"""
Trigger analysis for imported GitOnboard repository.
"""
import asyncio
from datetime import datetime, timezone
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.user import User
from backend.dependencies.auth import get_or_create_local_dev_user
from backend.services.worker import AnalysisWorker

db = SessionLocal()

try:
    # Get the local user and find the analysis we just created
    user = get_or_create_local_dev_user(db)

    # Find the GitOnboard repository we just created
    repo = db.query(Repository).filter(
        Repository.id == 84712001,
        Repository.user_id == user.id
    ).first()

    if not repo:
        print("❌ Repository not found")
        exit(1)

    print(f"Found repository: {repo.url} (ID: {repo.id})")

    # Get the analysis
    analysis = db.query(Analysis).filter(
        Analysis.id == 847121,
        Analysis.repository_id == repo.id
    ).first()

    if not analysis:
        print("❌ Analysis not found")
        exit(1)

    print(f"Found analysis: {analysis.id}, Status: {analysis.status}")

    # Create an analysis job to trigger the worker
    print(f"\nCreating analysis job...")
    job = db.query(AnalysisJob).filter(
        AnalysisJob.analysis_id == analysis.id
    ).first()

    if not job:
        job = AnalysisJob(
            analysis_id=analysis.id,
            status="Queued"
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        print(f"✓ Created analysis job ID: {job.id}")
    else:
        print(f"✓ Job already exists: {job.id}, Status: {job.status}")

    # Now run the analysis directly
    print(f"\nRunning AnalysisEngine on local repository...")

    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    # Use the local repository path
    local_repo_path = "/home/dheeraj/repository_intelligence_platform"

    try:
        engine = AnalysisEngine(local_repo_path, get_default_registry())
        model = engine.run(
            repo_name="GitOnboard",
            commit_info={
                "hash": "008271024c10437aafe59a3df689759afad00cc9",
                "branch": "main",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "remote_url": "https://github.com/salianDheeraj/GitOnboard"
            },
            analysis_id=analysis.id,
            db=db
        )

        print(f"\n✓ Engine run completed!")
        print(f"\nModel Contents (before FactStore persistence):")
        print(f"  Total entities: {len(model.entities)}")
        print(f"  Total relationships: {len(model.relationships)}")

        # Count by type
        from collections import Counter
        entity_types = Counter(e.type for e in model.entities.values())
        rel_types = Counter(r.type for r in model.relationships.values())

        print(f"\nEntity counts by type:")
        for etype, count in sorted(entity_types.items()):
            print(f"  {etype}: {count}")

        print(f"\nRelationship counts by type:")
        for rtype, count in sorted(rel_types.items()):
            print(f"  {rtype}: {count}")

        # CRITICAL: Persist the model to FactStore
        print(f"\n📊 Persisting model to FactStore...")
        from backend.intelligence.store.fact_store import save_rim_to_fact_store
        save_rim_to_fact_store(db, analysis.id, model)
        print(f"✓ FactStore persistence complete!")

        # Update analysis status
        analysis.status = "Completed"
        analysis.indexed_at = datetime.now(timezone.utc)
        job.status = "Completed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        print(f"\n✓ Analysis completed!")

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        analysis.status = "Failed"
        job.status = "Failed"
        job.error = str(e)
        db.commit()
        exit(1)

    print(f"\n{'='*60}")
    print(f"ANALYSIS COMPLETE - Ready for Phase 2F")
    print(f"{'='*60}")
    print(f"Repository ID: {repo.id}")
    print(f"Analysis ID: {analysis.id}")
    print(f"Status: {analysis.status}")

finally:
    db.close()
