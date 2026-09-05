#!/usr/bin/env python3
"""
Phase 2H Optimized Analysis

Runs on full GitOnboard repository with minimal logging to test scaling predictions.
Based on profiling: 100 files = 12.14s → 2,421 files should ≈ 293 seconds
"""
from datetime import datetime, timezone
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactSymbol
import time

def main():
    db = SessionLocal()

    try:
        print("\n[1/5] Setting up...")
        from backend.dependencies.auth import get_or_create_local_dev_user
        user = get_or_create_local_dev_user(db)
        repo = db.query(Repository).filter(Repository.id == 84712001).first()

        if not repo:
            print("ERROR: Repository not found")
            return False

        print(f"  Repository: {repo.url}")

        # Create fresh analysis
        print("\n[2/5] Creating analysis...")
        analysis = Analysis(repository_id=repo.id)
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        analysis_id = analysis.id
        print(f"  Analysis ID: {analysis_id}")

        # Run engine on full repository
        print("\n[3/5] Running analysis on full repository...")
        print("  (skipping diagnostics for performance)")

        try:
            from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
            from backend.intelligence.engine.analyzers import get_default_registry

            local_repo_path = "/home/dheeraj/repository_intelligence_platform"
            engine = AnalysisEngine(local_repo_path, get_default_registry())

            start = time.time()

            # Run WITHOUT analysis_id to skip diagnostic logging
            model = engine.run(
                repo_name="GitOnboard",
                commit_info={
                    "hash": "008271024c10437aafe59a3df689759afad00cc9",
                    "branch": "main",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "remote_url": "https://github.com/salianDheeraj/GitOnboard"
                },
                analysis_id=None,  # Disable diagnostics
                db=None,  # Disable progress tracking
                skip_validation=True
            )

            elapsed = time.time() - start

            print(f"  ✓ Engine run completed in {elapsed:.2f}s")
            print(f"  Entities: {len(model.entities)}")
            print(f"  Relationships: {len(model.relationships)}")

            # Get timing data
            timings = getattr(model, '_analyzer_timings', {})
            if timings:
                print(f"\n  Analyzer timings:")
                sorted_analyzers = sorted(
                    timings.items(),
                    key=lambda x: x[1]["duration_seconds"],
                    reverse=True
                )
                for analyzer, timing in sorted_analyzers[:5]:
                    print(f"    {analyzer}: {timing['duration_seconds']:.2f}s")

        except Exception as e:
            print(f"ERROR in engine.run(): {e}")
            import traceback
            traceback.print_exc()

            analysis.status = "Failed"
            db.commit()
            return False

        # Persist to FactStore
        print(f"\n[4/5] Persisting to FactStore...")
        try:
            from backend.intelligence.store.fact_store import save_rim_to_fact_store
            save_rim_to_fact_store(db, analysis_id, model)
            db.commit()

            symbol_count = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis_id
            ).count()

            print(f"  Symbols persisted: {symbol_count}")

            if symbol_count == 0:
                print("ERROR: FactStore persistence returned 0 symbols")
                analysis.status = "Failed"
                db.commit()
                return False

        except Exception as e:
            print(f"ERROR in FactStore persistence: {e}")
            import traceback
            traceback.print_exc()

            analysis.status = "Failed"
            db.commit()
            return False

        # Update status
        print(f"\n[5/5] Finalizing...")
        analysis.status = "Completed"
        analysis.indexed_at = datetime.now(timezone.utc)
        db.commit()

        print(f"\n✓ OPTIMIZED ANALYSIS COMPLETE")
        print(f"  Analysis ID: {analysis_id}")
        print(f"  Status: {analysis.status}")
        print(f"  FactStore: {symbol_count} symbols persisted")

        return True

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
