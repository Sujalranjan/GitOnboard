#!/usr/bin/env python3
"""
Reset analysis 847121 and re-run with FactStore persistence fix.
"""
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from datetime import datetime, timezone

db = SessionLocal()

try:
    # Delete old analysis data
    print("Cleaning up old analysis...")
    
    # Delete FactStore data for this analysis
    file_count = db.query(FactFile).filter(FactFile.analysis_id == 847121).delete()
    symbol_count = db.query(FactSymbol).filter(FactSymbol.analysis_id == 847121).delete()
    rel_count = db.query(FactRelationship).filter(FactRelationship.analysis_id == 847121).delete()
    
    print(f"  Deleted {file_count} files, {symbol_count} symbols, {rel_count} relationships")
    
    # Reset analysis status
    analysis = db.query(Analysis).filter(Analysis.id == 847121).first()
    if analysis:
        analysis.status = "Queued"
        analysis.progress_stage = None
        analysis.progress_substage = None
        analysis.progress_processed = 0
        analysis.progress_total = 0
        analysis.indexed_at = None
        print(f"  Reset analysis 847121 status to 'Queued'")
    
    # Reset job status
    job = db.query(AnalysisJob).filter(AnalysisJob.analysis_id == 847121).first()
    if job:
        job.status = "Queued"
        job.error = None
        print(f"  Reset job status to 'Queued'")
    
    db.commit()
    print(f"\n✓ Analysis cleaned and reset")
    print(f"Ready to run corrected trigger_analysis.py with FactStore persistence\n")

finally:
    db.close()
