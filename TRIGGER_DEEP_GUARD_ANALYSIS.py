#!/usr/bin/env python3
"""
Trigger analysis of Deep-Guard-Backend repository.

Creates proper Analysis and AnalysisJob records, then runs the analysis.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.user import User
from backend.models.fact_store import FactSymbol

engine = create_engine("sqlite:///./data/local.db")
Session = sessionmaker(bind=engine)
session = Session()

print("=" * 80)
print("DEEP-GUARD-BACKEND ANALYSIS TRIGGER")
print("=" * 80)

# 1. Create proper repository entry if needed
print("\n=== CHECKING REPOSITORY ===")

deep_guard_url = "https://github.com/salianDheeraj/Deep-Guard-Backend"
deep_guard_path = Path("/home/dheeraj/Deep-Guard/Deep-Guard-Backend")

# Try to find existing repo
repo = session.query(Repository).filter(
    Repository.url.ilike(f"%Deep-Guard-Backend%")
).first()

if not repo:
    print(f"Creating new repository record...")
    # Get existing user
    user = session.query(User).first()
    if not user:
        print("❌ No user found in database!")
        sys.exit(1)

    repo = Repository(
        url=deep_guard_url,
        default_branch="main",
        user_id=user.id
    )
    session.add(repo)
    session.flush()
    print(f"✓ Created repository ID {repo.id}")
else:
    print(f"✓ Found existing repository ID {repo.id}: {repo.url}")

# 2. Create new Analysis
print("\n=== CREATING ANALYSIS ===")

analysis = Analysis(
    repository_id=repo.id,
    status="Queued",
    engine_version="v1.0",
    commit_sha=None
)
session.add(analysis)
session.flush()

print(f"✓ Created analysis ID {analysis.id}")

# 3. Create AnalysisJob
print("\n=== CREATING ANALYSIS JOB ===")

job = AnalysisJob(
    analysis_id=analysis.id,
    status="Queued",
    started_at=None,
    completed_at=None
)
session.add(job)
session.flush()

print(f"✓ Created job ID {job.id}")
print(f"  Analysis: {analysis.id}")
print(f"  Repository: {repo.url}")
print(f"  Local path: {deep_guard_path}")

# Commit
session.commit()

# 4. Now run the analysis
print("\n=== RUNNING ANALYSIS ===")

try:
    from backend.services.worker import AnalysisWorker
    import asyncio

    print(f"Launching AnalysisWorker for job {job.id}...")

    async def run_job():
        worker = AnalysisWorker()
        await worker.process(job.id)

    # Run the analysis (this will download, analyze, and persist)
    asyncio.run(run_job())

    print("✓ Analysis complete!")

except Exception as e:
    print(f"❌ Analysis failed: {e}")
    import traceback
    traceback.print_exc()

# 5. Check results
print("\n=== CHECKING RESULTS ===")

session.refresh(analysis)
session.refresh(job)

print(f"Analysis status: {analysis.status}")
print(f"Job status: {job.status}")

if job.error:
    print(f"Job error: {job.error}")

# Count entities
symbols = session.query(FactSymbol).filter(FactSymbol.analysis_id == analysis.id).count()
print(f"\nEntities persisted:")
print(f"  Symbols: {symbols}")

if symbols > 0:
    # Show auth-related symbols
    auth_syms = session.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis.id,
        FactSymbol.name.ilike("%auth%") | FactSymbol.name.ilike("%login%")
    ).limit(10).all()

    if auth_syms:
        print(f"\n  Auth-related symbols:")
        for sym in auth_syms:
            print(f"    - {sym.name} ({sym.symbol_type})")

print("\n✓ Analysis triggered and completed")

session.close()
