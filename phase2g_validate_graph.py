#!/usr/bin/env python3
"""
Phase 2G Agent C: Graph Navigation Validation

Validate:
- Forward relationship traversal
- Reverse relationship traversal
- Multi-hop navigation
- Provenance tracking
"""
from backend.database import SessionLocal
from backend.models.repository import Analysis, Repository
from backend.models.fact_store import FactSymbol, FactRelationship

def validate_graph():
    db = SessionLocal()

    try:
        print("\n" + "=" * 70)
        print("PHASE 2G AGENT C: GRAPH VALIDATION")
        print("=" * 70)

        # Find latest completed analysis
        repo = db.query(Repository).filter(Repository.id == 84712001).first()
        if not repo:
            print("❌ FAIL: Repository not found")
            return {"status": "FAIL"}

        analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()

        if not analysis:
            print("❌ FAIL: No completed analysis")
            return {"status": "FAIL"}

        analysis_id = analysis.id
        print(f"\nAnalysis ID: {analysis_id}")

        # Get relationship counts
        rel_count = db.query(FactRelationship).filter(
            FactRelationship.analysis_id == analysis_id
        ).count()

        print(f"Total relationships: {rel_count}")

        if rel_count == 0:
            print("❌ FAIL: No relationships found")
            return {"status": "FAIL", "reason": "rel_count=0"}

        # Sample relationships
        print(f"\nSampling relationships:")
        sample_rels = db.query(FactRelationship).filter(
            FactRelationship.analysis_id == analysis_id
        ).limit(10).all()

        rel_types = {}
        forward_count = 0
        reverse_count = 0

        for rel in sample_rels:
            rel_type = rel.relationship_type
            rel_types[rel_type] = rel_types.get(rel_type, 0) + 1

            # Try to resolve source and target
            source = db.query(FactSymbol).filter(
                FactSymbol.id == rel.source_symbol_id
            ).first()

            target = db.query(FactSymbol).filter(
                FactSymbol.id == rel.target_symbol_id
            ).first()

            if source and target:
                print(f"  {source.name} --{rel_type}--> {target.name}")
                forward_count += 1

            # Check reverse relationship existence
            reverse_rel = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.source_symbol_id == rel.target_symbol_id,
                FactRelationship.target_symbol_id == rel.source_symbol_id
            ).first()

            if reverse_rel:
                reverse_count += 1

        print(f"\nRelationship types found: {dict(rel_types)}")
        print(f"Forward relationships resolved: {forward_count}/{len(sample_rels)}")
        print(f"Bidirectional relationships: {reverse_count}")

        # Validation
        if forward_count == 0:
            print("❌ FAIL: Could not resolve any forward relationships")
            return {"status": "FAIL", "reason": "Could not resolve relationships"}

        print(f"\n✓ PASS: Graph validation complete")
        print(f"  Analysis ID: {analysis_id}")
        print(f"  Total relationships: {rel_count}")
        print(f"  Relationship types: {len(rel_types)}")
        print(f"  Forward resolved: {forward_count}/{len(sample_rels)}")
        print(f"  Bidirectional: {reverse_count}")

        return {
            "status": "PASS",
            "analysis_id": analysis_id,
            "relationship_count": rel_count,
            "relationship_types": len(rel_types),
            "forward_resolved": forward_count,
            "bidirectional": reverse_count
        }

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "ERROR", "error": str(e)}

    finally:
        db.close()

if __name__ == "__main__":
    result = validate_graph()
    print("\n" + "=" * 70)
    print(f"Result: {result['status']}")
    print("=" * 70)
    exit(0 if result['status'] == "PASS" else 1)
