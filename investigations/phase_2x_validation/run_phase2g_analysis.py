#!/usr/bin/env python3
"""
Phase 2G: Real GitOnboard E2E Analysis

Minimal, robust analysis script with explicit error handling.
"""
from datetime import datetime, timezone
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from backend.dependencies.auth import get_or_create_local_dev_user

def main():
    db = SessionLocal()

    try:
        # Step 1: Get user and repository
        print("\n[1/6] Setting up...")
        user = get_or_create_local_dev_user(db)
        repo = db.query(Repository).filter(Repository.id == 84712001).first()

        if not repo:
            print("ERROR: Repository 84712001 not found")
            return False

        print(f"  Repository: {repo.url}")

        # Step 2: Create fresh analysis
        print("\n[2/6] Creating fresh analysis...")
        analysis = Analysis(repository_id=repo.id)
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        analysis_id = analysis.id
        print(f"  Analysis ID: {analysis_id}")

        # Step 3: Run parser and symbol extraction
        print("\n[3/6] Running parser and symbol extraction...")
        try:
            from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
            from backend.intelligence.engine.analyzers import get_default_registry

            local_repo_path = "/home/dheeraj/repository_intelligence_platform"
            engine = AnalysisEngine(local_repo_path, get_default_registry())

            model = engine.run(
                repo_name="GitOnboard",
                commit_info={
                    "hash": "008271024c10437aafe59a3df689759afad00cc9",
                    "branch": "main",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "remote_url": "https://github.com/salianDheeraj/GitOnboard"
                },
                analysis_id=analysis_id,
                db=db,
                skip_validation=True  # Skip validation for performance on large repos
            )

            print(f"  Entities: {len(model.entities)}")
            print(f"  Relationships: {len(model.relationships)}")

        except Exception as e:
            print(f"ERROR in engine.run(): {e}")
            import traceback
            traceback.print_exc()

            analysis.status = "Failed"
            db.commit()
            return False

        # Step 4: Persist to FactStore
        print("\n[4/6] Persisting to FactStore...")
        try:
            from backend.intelligence.store.fact_store import save_rim_to_fact_store
            save_rim_to_fact_store(db, analysis_id, model)
            db.commit()

            # Verify persistence
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

        # Step 5: Update analysis status
        print("\n[5/6] Updating analysis status...")
        analysis.status = "Completed"
        analysis.indexed_at = datetime.now(timezone.utc)
        db.commit()

        print(f"  Status: {analysis.status}")

        # Step 6: Verify complete state
        print("\n[6/6] Verifying complete state...")
        file_count = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).count()
        symbol_count = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis_id).count()
        rel_count = db.query(FactRelationship).filter(FactRelationship.analysis_id == analysis_id).count()

        print(f"  Files: {file_count}")
        print(f"  Symbols: {symbol_count}")
        print(f"  Relationships: {rel_count}")

        print("\n" + "=" * 70)
        print("✓ PHASE 2G ANALYSIS COMPLETE")
        print("=" * 70)
        print(f"Analysis ID: {analysis_id}")
        print(f"Repository ID: {repo.id}")
        print(f"Status: {analysis.status}")
        print(f"FactStore: {file_count} files, {symbol_count} symbols, {rel_count} relationships")

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
