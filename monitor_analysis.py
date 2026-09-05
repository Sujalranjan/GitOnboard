#!/usr/bin/env python3
"""
Monitor the analysis progress and wait for completion.
"""
import time
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship

def check_progress():
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(Analysis.id == 847121).first()
        job = db.query(AnalysisJob).filter(AnalysisJob.analysis_id == 847121).first()

        if not analysis:
            print("❌ Analysis not found")
            return False

        print(f"\nAnalysis Status: {analysis.status}")
        if job:
            print(f"Job Status: {job.status}")
            if analysis.progress_stage:
                print(f"Progress: {analysis.progress_stage} / {analysis.progress_substage}")
                if analysis.progress_total:
                    pct = int((analysis.progress_processed / analysis.progress_total) * 100)
                    print(f"  {analysis.progress_processed} / {analysis.progress_total} {analysis.progress_unit} ({pct}%)")

        # Check FactStore counts
        file_count = db.query(FactFile).filter(FactFile.analysis_id == 847121).count()
        symbol_count = db.query(FactSymbol).filter(FactSymbol.analysis_id == 847121).count()
        rel_count = db.query(FactRelationship).filter(FactRelationship.analysis_id == 847121).count()

        print(f"\nFactStore (analysis_id=847121):")
        print(f"  Files: {file_count}")
        print(f"  Symbols: {symbol_count}")
        print(f"  Relationships: {rel_count}")

        if analysis.status == "Completed":
            print(f"\n✓ ANALYSIS COMPLETE")
            return True
        elif analysis.status == "Failed":
            print(f"\n❌ ANALYSIS FAILED")
            if job and job.error:
                print(f"Error: {job.error}")
            return True
        else:
            print(f"\n⧲ Waiting for analysis to complete...")
            return False

    finally:
        db.close()

if __name__ == "__main__":
    print("Monitoring analysis progress...")
    start = time.time()
    timeout = 600  # 10 minutes

    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            print(f"\n⏱️ Timeout after {int(elapsed)}s")
            break

        complete = check_progress()
        if complete:
            break

        time.sleep(10)  # Check every 10 seconds
        print(f"[{int(elapsed)}s elapsed]")
