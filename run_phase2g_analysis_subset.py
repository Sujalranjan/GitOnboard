#!/usr/bin/env python3
"""
Phase 2G: Analysis on Backend Subset

Test on smaller codebase to complete validation faster,
then diagnose why full repository is slow.
"""
from datetime import datetime, timezone
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis
from backend.dependencies.auth import get_or_create_local_dev_user

def main():
    db = SessionLocal()

    try:
        print("\n[1/5] Setting up...")
        user = get_or_create_local_dev_user(db)
        repo = db.query(Repository).filter(Repository.id == 84712001).first()

        if not repo:
            print("ERROR: Repository not found")
            return False

        # Create fresh analysis for subset
        print("\n[2/5] Creating analysis...")
        analysis = Analysis(repository_id=repo.id)
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        analysis_id = analysis.id
        print(f"  Analysis ID: {analysis_id}")

        # Run on backend subset (much smaller)
        subset_path = "/home/dheeraj/repository_intelligence_platform/backend"
        print(f"\n[3/5] Running analysis on subset: {subset_path}")

        try:
            from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
            from backend.intelligence.engine.analyzers import get_default_registry
            import time

            start = time.time()

            engine = AnalysisEngine(subset_path, get_default_registry())
            model = engine.run(
                repo_name="GitOnboard-Backend",
                commit_info={
                    "hash": "008271024c10437aafe59a3df689759afad00cc9",
                    "branch": "main",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "remote_url": "https://github.com/salianDheeraj/GitOnboard"
                },
                analysis_id=analysis_id,
                db=db
            )

            elapsed = time.time() - start
            print(f"  ✓ Engine run completed in {elapsed:.1f}s")
            print(f"  Entities: {len(model.entities)}")
            print(f"  Relationships: {len(model.relationships)}")

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

            from backend.models.fact_store import FactSymbol, FactRelationship

            symbol_count = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis_id
            ).count()

            rel_count = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis_id
            ).count()

            print(f"  Symbols persisted: {symbol_count}")
            print(f"  Relationships persisted: {rel_count}")

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

        print(f"\n✓ SUBSET ANALYSIS COMPLETE")
        print(f"  Analysis ID: {analysis_id}")
        print(f"  Status: {analysis.status}")
        print(f"  Symbols: {symbol_count}")
        print(f"  Relationships: {rel_count}")

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
