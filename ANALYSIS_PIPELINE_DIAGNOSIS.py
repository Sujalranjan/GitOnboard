#!/usr/bin/env python3
"""
Comprehensive diagnosis of the repository analysis pipeline.

Trace: repository → analysis → FactStore → retrieval → RIM
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.repository import Analysis, Repository, AnalysisJob, AnalysisArtifact
from backend.models.fact_store import FactSymbol, FactFile, FactRoute, FactRelationship, FactCapability

engine = create_engine("sqlite:///./data/local.db")
Session = sessionmaker(bind=engine)
session = Session()

print("=" * 80)
print("ANALYSIS PIPELINE DIAGNOSIS")
print("=" * 80)

# 1. Check Repositories
print("\n=== REPOSITORIES ===")
repos = session.query(Repository).all()
print(f"Total repositories: {len(repos)}")
for repo in repos:
    print(f"\n  ID: {repo.id}")
    print(f"  URL: {repo.url}")
    print(f"  Default branch: {repo.default_branch}")

    # Check if Deep-Guard-Backend
    if "Deep-Guard" in repo.url:
        print("  ✓ This is Deep-Guard-Backend")

# 2. Check Analyses
print("\n=== ANALYSES ===")
analyses = session.query(Analysis).all()
print(f"Total analyses: {len(analyses)}")
for analysis in analyses:
    print(f"\n  Analysis ID: {analysis.id}")
    print(f"  Repository ID: {analysis.repository_id}")
    print(f"  Status: {analysis.status}")
    print(f"  Commit SHA: {analysis.commit_sha}")

    # Check AnalysisJobs for this analysis
    jobs = session.query(AnalysisJob).filter(AnalysisJob.analysis_id == analysis.id).all()
    print(f"  Jobs: {len(jobs)}")
    for job in jobs:
        print(f"    - Job {job.id}: {job.status} (started: {job.started_at}, completed: {job.completed_at})")
        if job.error:
            print(f"      Error: {job.error[:100]}")

    # Check Artifacts
    artifacts = session.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id).all()
    print(f"  Artifacts: {len(artifacts)}")
    for art in artifacts:
        data_size = len(art.blob_data) if art.blob_data else len(str(art.data))
        print(f"    - {art.type}: {data_size} bytes")

    # Count entities in this analysis
    print(f"\n  Entity counts for analysis {analysis.id}:")
    files = session.query(FactFile).filter(FactFile.analysis_id == analysis.id).count()
    symbols = session.query(FactSymbol).filter(FactSymbol.analysis_id == analysis.id).count()
    routes = session.query(FactRoute).filter(FactRoute.analysis_id == analysis.id).count()
    relationships = session.query(FactRelationship).filter(FactRelationship.analysis_id == analysis.id).count()
    capabilities = session.query(FactCapability).filter(FactCapability.analysis_id == analysis.id).count()

    print(f"    Files: {files}")
    print(f"    Symbols: {symbols}")
    print(f"    Routes: {routes}")
    print(f"    Relationships: {relationships}")
    print(f"    Capabilities: {capabilities}")

    # Check for auth-related symbols
    if symbols > 0:
        auth_symbols = session.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            FactSymbol.name.ilike("%auth%") | FactSymbol.name.ilike("%login%")
        ).all()

        if auth_symbols:
            print(f"\n    Auth-related symbols ({len(auth_symbols)}):")
            for sym in auth_symbols:
                print(f"      - {sym.name} ({sym.symbol_type}) at {sym.file_id}:{sym.line_start}")
        else:
            print(f"\n    No auth-related symbols found")

# 3. Check actual Deep-Guard-Backend repository
print("\n\n=== DEEP-GUARD-BACKEND STATUS ===")
deep_guard_path = Path("/home/dheeraj/Deep-Guard/Deep-Guard-Backend")
if deep_guard_path.exists():
    print(f"✓ Repository exists at {deep_guard_path}")

    # Count files
    auth_files = list(deep_guard_path.glob("**/*auth*"))
    login_files = list(deep_guard_path.glob("**/*login*"))

    print(f"  Auth files: {len(auth_files)}")
    for f in auth_files[:5]:
        print(f"    - {f.relative_to(deep_guard_path)}")

    print(f"  Login files: {len(login_files)}")
    for f in login_files[:5]:
        print(f"    - {f.relative_to(deep_guard_path)}")
else:
    print(f"✗ Repository not found at {deep_guard_path}")

# 4. Summary
print("\n\n=== DIAGNOSIS SUMMARY ===")
if len(analyses) == 0:
    print("❌ No analyses in database at all")
elif len(analyses) == 1 and analyses[0].status == "Completed":
    total_symbols = session.query(FactSymbol).filter(FactSymbol.analysis_id == analyses[0].id).count()
    if total_symbols == 1:
        print("❌ CRITICAL: Only 1 analysis with 1 symbol (synthetic test data only)")
        print("   Deep-Guard-Backend was never analyzed!")
    elif total_symbols > 100:
        print(f"✓ Analysis exists with {total_symbols} symbols")
        print("   Need to verify auth-related symbols are present")
else:
    print("⚠ Multiple analyses found - need to identify which is Deep-Guard-Backend")

session.close()
