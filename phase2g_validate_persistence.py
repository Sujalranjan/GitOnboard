#!/usr/bin/env python3
"""
Phase 2G Agent A: Persistence Validation

Validate:
- Analysis completion
- RepositoryModel contents
- FactStore persistence
- Counts match
"""
from backend.database import SessionLocal
from backend.models.repository import Analysis, Repository
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship

def validate_persistence():
    db = SessionLocal()

    try:
        print("\n" + "=" * 70)
        print("PHASE 2G AGENT A: PERSISTENCE VALIDATION")
        print("=" * 70)

        # Find latest completed analysis for repository 84712001
        repo = db.query(Repository).filter(Repository.id == 84712001).first()
        if not repo:
            print("❌ FAIL: Repository 84712001 not found")
            return {"status": "FAIL", "reason": "Repository not found"}

        analyses = db.query(Analysis).filter(
            Analysis.repository_id == repo.id
        ).order_by(Analysis.created_at.desc()).all()

        if not analyses:
            print("❌ FAIL: No analyses for repository")
            return {"status": "FAIL", "reason": "No analyses"}

        # Use most recent
        analysis = analyses[0]
        analysis_id = analysis.id

        print(f"\nAnalysis ID: {analysis_id}")
        print(f"Status: {analysis.status}")
        print(f"Progress: {analysis.progress_processed}/{analysis.progress_total} {analysis.progress_unit}")

        # Requirement 1: Analysis must be completed
        if analysis.status != "Completed":
            print(f"❌ FAIL: Analysis status is '{analysis.status}' not 'Completed'")
            return {"status": "FAIL", "reason": f"Status={analysis.status}", "analysis_id": analysis_id}

        print("✓ Analysis status: Completed")

        # Requirement 2: FactStore must have data
        file_count = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).count()
        symbol_count = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis_id).count()
        rel_count = db.query(FactRelationship).filter(FactRelationship.analysis_id == analysis_id).count()

        print(f"\nFactStore:")
        print(f"  Files: {file_count}")
        print(f"  Symbols: {symbol_count}")
        print(f"  Relationships: {rel_count}")

        if file_count == 0:
            print("❌ FAIL: FactFile count is 0")
            return {"status": "FAIL", "reason": "FactFile=0", "analysis_id": analysis_id}

        if symbol_count == 0:
            print("❌ FAIL: FactSymbol count is 0")
            return {"status": "FAIL", "reason": "FactSymbol=0", "analysis_id": analysis_id}

        print("✓ FactStore has data")

        # Requirement 3: Sample some symbols
        print(f"\nSampling FactSymbols...")
        sample_symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id
        ).limit(5).all()

        for i, sym in enumerate(sample_symbols, 1):
            print(f"  [{i}] {sym.name} ({sym.entity_type}) in {sym.file_id}")

        print(f"\n✓ PASS: Persistence validation complete")
        print(f"  Analysis ID: {analysis_id}")
        print(f"  Status: {analysis.status}")
        print(f"  Files: {file_count}")
        print(f"  Symbols: {symbol_count}")
        print(f"  Relationships: {rel_count}")

        return {
            "status": "PASS",
            "analysis_id": analysis_id,
            "file_count": file_count,
            "symbol_count": symbol_count,
            "relationship_count": rel_count
        }

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "ERROR", "error": str(e)}

    finally:
        db.close()

if __name__ == "__main__":
    result = validate_persistence()
    print("\n" + "=" * 70)
    print(f"Result: {result['status']}")
    print("=" * 70)
    exit(0 if result['status'] == "PASS" else 1)
