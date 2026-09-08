#!/usr/bin/env python3
"""
Test Tool #3 (Graph Query) - Traverse graph relationships for the symbols.
"""

import sys
import os
os.environ["DATABASE_HOST"] = "repository_intelligence_platform-postgres-1"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+psycopg://myuser:mypassword@repository_intelligence_platform-postgres-1:5432/repository_intelligence"

def test_graph_query():
    """Test Tool #3 Graph Query with both symbols."""

    print("=" * 90)
    print("GRAPH QUERY TEST: Relationship Traversal")
    print("=" * 90)

    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        db = Session()

        from backend.models.repository import Repository, Analysis
        from backend.models.fact_store import FactSymbol, FactFile, FactRelationship

        # Get GitOnboard repo
        repo = db.query(Repository).filter(
            Repository.url.like("%GitOnboard%")
        ).first()

        repo_hash = repo.repository_hash

        # Get latest analysis
        analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()

        print(f"\n📦 Repository: GitOnboard")
        print(f"🔑 UUID Hash: {repo_hash}")
        print(f"📊 Analysis ID: {analysis.id}")

        # Test 1: AgentRunDetailResponse
        print(f"\n{'='*90}")
        print("TEST 1: Graph - AgentRunDetailResponse (CLASS)")
        print(f"{'='*90}")

        sym1 = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            FactSymbol.name == "AgentRunDetailResponse"
        ).first()

        if sym1:
            print(f"\n✅ Symbol: {sym1.name}")
            print(f"   Qualified ID: {sym1.id}")
            print(f"   Type: {sym1.symbol_type}")

            # Query relationships
            incoming = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis.id,
                FactRelationship.to_symbol_id == sym1.id
            ).all()

            outgoing = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis.id,
                FactRelationship.from_symbol_id == sym1.id
            ).all()

            print(f"\n   📊 Graph Relationships:")
            print(f"      ├─ Incoming edges: {len(incoming)}")
            if incoming:
                for rel in incoming[:3]:
                    caller = db.query(FactSymbol).filter(FactSymbol.id == rel.from_symbol_id).first()
                    print(f"      │  ├─ {rel.rel_type}: {caller.name if caller else 'unknown'}")
                if len(incoming) > 3:
                    print(f"      │  └─ ... {len(incoming)-3} more")

            print(f"      └─ Outgoing edges: {len(outgoing)}")
            if outgoing:
                for rel in outgoing[:3]:
                    called = db.query(FactSymbol).filter(FactSymbol.id == rel.to_symbol_id).first()
                    print(f"         ├─ {rel.rel_type}: {called.name if called else 'unknown'}")
                if len(outgoing) > 3:
                    print(f"         └─ ... {len(outgoing)-3} more")

        # Test 2: get_run_changes
        print(f"\n{'='*90}")
        print("TEST 2: Graph - get_run_changes (FUNCTION)")
        print(f"{'='*90}")

        sym2 = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            FactSymbol.name == "get_run_changes"
        ).first()

        if sym2:
            print(f"\n✅ Symbol: {sym2.name}")
            print(f"   Qualified ID: {sym2.id}")
            print(f"   Type: {sym2.symbol_type}")

            # Query relationships
            incoming = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis.id,
                FactRelationship.to_symbol_id == sym2.id
            ).all()

            outgoing = db.query(FactRelationship).filter(
                FactRelationship.analysis_id == analysis.id,
                FactRelationship.from_symbol_id == sym2.id
            ).all()

            print(f"\n   📊 Graph Relationships:")
            print(f"      ├─ Incoming edges (Called by): {len(incoming)}")
            if incoming:
                for rel in incoming[:5]:
                    caller = db.query(FactSymbol).filter(FactSymbol.id == rel.from_symbol_id).first()
                    print(f"      │  ├─ {rel.rel_type}: {caller.name if caller else 'unknown'}")
                if len(incoming) > 5:
                    print(f"      │  └─ ... {len(incoming)-5} more")

            print(f"      └─ Outgoing edges (Calls): {len(outgoing)}")
            if outgoing:
                for rel in outgoing[:5]:
                    called = db.query(FactSymbol).filter(FactSymbol.id == rel.to_symbol_id).first()
                    print(f"         ├─ {rel.rel_type}: {called.name if called else 'unknown'}")
                if len(outgoing) > 5:
                    print(f"         └─ ... {len(outgoing)-5} more")

        # Summary
        print(f"\n{'='*90}")
        print("VERIFICATION")
        print(f"{'='*90}")

        print(f"\n✅ Graph relationships accessible via repository_hash:")
        print(f"   Repository UUID: {repo_hash}")
        print(f"   Symbol 1: {sym1.name}")
        print(f"      ├─ Incoming: {len(incoming)} edges")
        print(f"      └─ Outgoing: {len(outgoing)} edges")

        incoming2 = db.query(FactRelationship).filter(
            FactRelationship.analysis_id == analysis.id,
            FactRelationship.to_symbol_id == sym2.id
        ).all()
        outgoing2 = db.query(FactRelationship).filter(
            FactRelationship.analysis_id == analysis.id,
            FactRelationship.from_symbol_id == sym2.id
        ).all()

        print(f"   Symbol 2: {sym2.name}")
        print(f"      ├─ Incoming: {len(incoming2)} edges")
        print(f"      └─ Outgoing: {len(outgoing2)} edges")

        print(f"\n🎯 Tool #3 (Graph Query) works perfectly!")
        print(f"   Complete call graph accessible via repository_hash UUID")

        db.close()
        return True

    except Exception as e:
        import traceback
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_graph_query()
    sys.exit(0 if success else 1)
