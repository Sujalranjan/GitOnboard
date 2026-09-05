#!/usr/bin/env python3
"""
Discover existing GitOnboard repository in the application database.
"""
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis
import json
from datetime import datetime

db = SessionLocal()

try:
    # Find GitOnboard repository
    repo = db.query(Repository).filter(
        Repository.url.ilike('%GitOnboard%')
    ).first()

    if not repo:
        print("❌ GitOnboard repository not found")
        print("\nSearching for all repositories...")
        repos = db.query(Repository).all()
        for r in repos:
            print(f"  - ID: {r.id}, URL: {r.url}")
        exit(1)

    print("✓ GitOnboard Repository Found")
    print(f"  ID: {repo.id}")
    print(f"  URL: {repo.url}")
    print(f"  Default Branch: {repo.default_branch}")
    print(f"  User ID: {repo.user_id}")

    # Get analysis history
    analyses = db.query(Analysis).filter(
        Analysis.repository_id == repo.id
    ).order_by(Analysis.created_at.desc()).all()

    print(f"\n✓ Analysis History ({len(analyses)} total)")
    for i, analysis in enumerate(analyses[:5]):  # Show most recent 5
        created_time = analysis.created_at.strftime("%Y-%m-%d %H:%M:%S") if analysis.created_at else "N/A"
        print(f"\n  [{i+1}] Analysis ID: {analysis.id}")
        print(f"      Created: {created_time}")
        print(f"      Status: {analysis.status}")
        print(f"      Engine Version: {analysis.engine_version}")
        print(f"      Indexing Status: {analysis.indexing_status}")
        print(f"      Fact Store Version: {analysis.fact_store_version}")

        # Get progress
        if analysis.progress_stage:
            print(f"      Progress: {analysis.progress_stage}/{analysis.progress_substage}")
            print(f"                {analysis.progress_percentage}% ({analysis.progress_processed}/{analysis.progress_total} {analysis.progress_unit})")

    # Check if most recent analysis has symbols
    if analyses:
        latest = analyses[0]
        print(f"\n✓ Latest Analysis Details")
        print(f"  ID: {latest.id}")
        print(f"  Status: {latest.status}")

        # Query FactStore for this analysis
        from backend.models.fact_store import FactFile, FactSymbol, FactRelationship

        file_count = db.query(FactFile).filter(FactFile.analysis_id == latest.id).count()
        symbol_count = db.query(FactSymbol).filter(FactSymbol.analysis_id == latest.id).count()
        rel_count = db.query(FactRelationship).filter(FactRelationship.analysis_id == latest.id).count()

        print(f"\n  FactStore Counts:")
        print(f"    Files: {file_count}")
        print(f"    Symbols: {symbol_count}")
        print(f"    Relationships: {rel_count}")

        if symbol_count == 0:
            print(f"\n  ⚠️  Latest analysis has 0 symbols - likely created before parser fix")
            print(f"      Need to create fresh analysis")
        else:
            print(f"\n  ✓ Latest analysis has symbols - parser fix may be applied")

    print(f"\n✓ Output saved")
    print(f"  Repository ID: {repo.id}")
    print(f"  Latest Analysis ID: {analyses[0].id if analyses else 'N/A'}")

finally:
    db.close()
