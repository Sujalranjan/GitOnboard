#!/usr/bin/env python3
"""Test whether retrieval results can be resolved to real FactSymbol IDs."""
import logging
from backend.database import SessionLocal
from backend.models.fact_store import FactSymbol, FactFile
from backend.models.repository import Analysis
from backend.intelligence.retrieval import HybridRetriever

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

db = SessionLocal()

print("\n" + "=" * 80)
print("TEST: ANCHOR RESOLUTION")
print("=" * 80)

# Get analysis for Deep-Guard-ML-Engine (repository_id = 3)
analysis = db.query(Analysis).filter_by(
    repository_id=3,
    status='Completed'
).first()

if not analysis:
    print("ERROR: No analysis found")
    import sys
    sys.exit(1)

analysis_id = analysis.id

print(f"\nAnalysis ID: {analysis_id}")
print()

# Create retriever with graph expansion disabled (focus on retrieval only)
retriever = HybridRetriever(
    db=db,
    analysis_id=analysis_id,
    enable_graph_expansion=False,  # Disable expansion to test retrieval alone
)

# Test query
query = "What is the main entry point?"
print(f"Query: {query}")
print()

# Get retrieval candidates
results = retriever.retrieve(query, top_k=5, expand_with_fact_store=False, enable_graph_expansion=False)

print(f"Retrieved {len(results)} candidates:")
print()

for i, result in enumerate(results[:5], 1):
    result_dict = result if isinstance(result, dict) else result.__dict__
    print(f"{i}. {result_dict.get('name', 'N/A')}")
    print(f"   ID field: {result_dict.get('id', 'N/A')[:60]}")
    print(f"   Symbol ID: {result_dict.get('symbol_id', 'N/A')[:60]}")
    print(f"   File: {result_dict.get('file_path', 'N/A')}")
    print(f"   Type: {result_dict.get('type', 'N/A')}")
    print()

    # Try to resolve to FactSymbol
    candidate_symbol_id = result_dict.get('symbol_id') or result_dict.get('id')

    if candidate_symbol_id:
        sym = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.id == candidate_symbol_id
        ).first()

        if sym:
            print(f"   ✓ Resolves to FactSymbol: {sym.name}")

            # Check if this symbol has relationships
            from backend.models.fact_store import FactRelationship
            from sqlalchemy import func

            outgoing = db.query(func.count(FactRelationship.id)).filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.from_symbol_id == sym.id
            ).scalar()

            incoming = db.query(func.count(FactRelationship.id)).filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.to_symbol_id == sym.id
            ).scalar()

            print(f"   Outgoing relationships: {outgoing}")
            print(f"   Incoming relationships: {incoming}")
        else:
            print(f"   ✗ Does NOT resolve to any FactSymbol")
            print(f"     Tried to find: {candidate_symbol_id[:60]}")
    else:
        print(f"   ⚠ No symbol_id or id field found")

    print()

print("=" * 80 + "\n")

db.close()
