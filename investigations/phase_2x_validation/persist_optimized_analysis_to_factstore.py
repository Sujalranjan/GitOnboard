#!/usr/bin/env python3
"""
Phase 2J Task 11B: Persist optimized analysis results to FactStore.

Following the successful analysis completion, persist the RIM to database.
"""
import json
import time
from datetime import datetime
from pathlib import Path

def main():
    print("\n" + "="*80)
    print("PHASE 2J TASK 11B: PERSIST OPTIMIZED ANALYSIS TO FACTSTORE")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*80 + "\n")

    try:
        # Import database setup
        from backend.infrastructure.database import get_db_session
        from backend.intelligence.storage.factstore import FactStore

        # Create a new analysis ID
        analysis_id = "optimized_phase2j_analysis"

        print(f"Creating database session...")
        db_session = get_db_session()

        print(f"Running optimized analysis again for persistence...")
        from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
        from backend.intelligence.engine.analyzers import get_default_registry

        source_repo = "/home/dheeraj/repository_intelligence_platform"
        engine = AnalysisEngine(source_repo, get_default_registry())

        start_time = time.time()
        model = engine.run(
            repo_name="GitOnboard-FactStore",
            skip_validation=True
        )
        analysis_time = time.time() - start_time

        print(f"✓ Analysis completed in {analysis_time:.2f}s")
        print(f"  Entities: {len(model.entities):,}")
        print(f"  Relationships: {len(model.relationships):,}")

        # Persist to FactStore
        print(f"\nPersisting to FactStore...")
        factstore = FactStore(db_session)

        persist_start = time.time()
        try:
            # Save files
            file_count = 0
            for entity_id, entity in model.entities.items():
                from backend.intelligence.rim.enums import EntityType
                if entity.type == EntityType.FILE:
                    factstore.save_file(analysis_id, entity.qualified_name, entity.metadata)
                    file_count += 1

            # Save symbols
            symbol_count = 0
            for entity_id, entity in model.entities.items():
                from backend.intelligence.rim.enums import EntityType
                if entity.type not in (EntityType.FILE, EntityType.MODULE, EntityType.DIRECTORY):
                    factstore.save_symbol(
                        analysis_id,
                        entity_id,
                        entity.name,
                        entity.type.value,
                        entity.qualified_name,
                        entity.metadata
                    )
                    symbol_count += 1

            # Save relationships
            relationship_count = 0
            for rel_id, rel in model.relationships.items():
                factstore.save_relationship(
                    analysis_id,
                    rel.source_id,
                    rel.target_id,
                    rel.type.value,
                    rel.metadata
                )
                relationship_count += 1

            db_session.commit()
            persist_time = time.time() - persist_start

            print(f"✓ FactStore persistence completed in {persist_time:.2f}s")
            print(f"  Files saved: {file_count}")
            print(f"  Symbols saved: {symbol_count}")
            print(f"  Relationships saved: {relationship_count}")

            result = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "analysis_time_seconds": analysis_time,
                "persistence_time_seconds": persist_time,
                "files_saved": file_count,
                "symbols_saved": symbol_count,
                "relationships_saved": relationship_count
            }

            output_file = Path("phase2j_factstore_persistence_result.json")
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2, default=str)

            print(f"\n✓ Results saved to {output_file}")
            return True

        except Exception as e:
            print(f"\n✗ Persistence failed: {e}")
            import traceback
            traceback.print_exc()
            db_session.rollback()
            return False

    except Exception as e:
        print(f"\n✗ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()

    print(f"\n" + "="*80)
    if success:
        print(f"PHASE 2J TASK 11B: SUCCESS")
        print(f"Analysis persisted to FactStore successfully.")
        print(f"Ready for Phase 2J Task 12 (E2E Validation)...")
    else:
        print(f"PHASE 2J TASK 11B: FAILED")
        print(f"FactStore persistence did not complete.")
    print(f"="*80 + "\n")
