#!/usr/bin/env python3
"""
Diagnose why analysis 847121 has 0 FactStore entries despite showing symbol extraction progress.
"""
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from datetime import datetime

db = SessionLocal()

try:
    print("=" * 70)
    print("ANALYSIS 847121 DIAGNOSTIC")
    print("=" * 70)

    # Check analysis record
    analysis = db.query(Analysis).filter(Analysis.id == 847121).first()
    if analysis:
        print(f"\n✓ Analysis Record Found")
        print(f"  ID: {analysis.id}")
        print(f"  Status: {analysis.status}")
        print(f"  Progress Stage: {analysis.progress_stage}")
        print(f"  Progress Substage: {analysis.progress_substage}")
        print(f"  Progress Processed: {analysis.progress_processed}")
        print(f"  Progress Total: {analysis.progress_total}")
        print(f"  Progress Unit: {analysis.progress_unit}")
        print(f"  Created At: {analysis.created_at}")
        print(f"  Indexed At: {analysis.indexed_at}")
    else:
        print("❌ Analysis not found")
        exit(1)

    # Check job record
    job = db.query(AnalysisJob).filter(AnalysisJob.analysis_id == 847121).first()
    if job:
        print(f"\n✓ Analysis Job Found")
        print(f"  Job ID: {job.id}")
        print(f"  Status: {job.status}")
        print(f"  Error: {job.error}")
    else:
        print("\n⚠️  No job record found")

    # Check FactStore persistence
    file_count = db.query(FactFile).filter(FactFile.analysis_id == 847121).count()
    symbol_count = db.query(FactSymbol).filter(FactSymbol.analysis_id == 847121).count()
    rel_count = db.query(FactRelationship).filter(FactRelationship.analysis_id == 847121).count()

    print(f"\n✓ FactStore Persistence Check")
    print(f"  Files: {file_count}")
    print(f"  Symbols: {symbol_count}")
    print(f"  Relationships: {rel_count}")

    if symbol_count == 0 and analysis.progress_processed == 25824:
        print(f"\n⚠️  CRITICAL: Parser extracted {analysis.progress_processed} symbols but FactStore is empty!")
        print(f"  This indicates the analysis engine did NOT persist to FactStore.")

    # Check repository
    repo = db.query(Repository).filter(Repository.id == 84712001).first()
    if repo:
        print(f"\n✓ Repository Record")
        print(f"  ID: {repo.id}")
        print(f"  URL: {repo.url}")

    print("\n" + "=" * 70)

finally:
    db.close()
