#!/usr/bin/env python3
"""Test retriever graph expansion directly."""
import logging
from backend.database import SessionLocal
from backend.models.repository import Analysis
from backend.intelligence.retrieval import HybridRetriever

logging.basicConfig(level=logging.DEBUG, format="[%(name)s] %(message)s")

db = SessionLocal()

# Get analysis
analysis = db.query(Analysis).filter_by(
    repository_id=3,
    status='Completed'
).first()

if not analysis:
    print("ERROR: No analysis found")
    import sys
    sys.exit(1)

analysis_id = analysis.id
print(f"Analysis ID: {analysis_id}")
print()

# Test 1: Retriever WITHOUT graph expansion
print("=" * 80)
print("Test 1: Retriever WITHOUT graph expansion")
print("=" * 80)
retriever_no_expand = HybridRetriever(
    db=db,
    analysis_id=analysis_id,
    enable_graph_expansion=False
)

results_no_expand = retriever_no_expand.retrieve(
    "What is the main entry point?",
    top_k=5,
    expand_with_fact_store=False,
    enable_graph_expansion=False
)

print(f"Results: {len(results_no_expand)}")
for r in results_no_expand[:3]:
    r_dict = r if isinstance(r, dict) else r.__dict__
    print(f"  - {r_dict.get('name', 'N/A')} (type: {r_dict.get('type', 'N/A')})")

print()

# Test 2: Retriever WITH graph expansion
print("=" * 80)
print("Test 2: Retriever WITH graph expansion (enabled in constructor)")
print("=" * 80)
retriever_with_expand = HybridRetriever(
    db=db,
    analysis_id=analysis_id,
    enable_graph_expansion=True
)

results_with_expand = retriever_with_expand.retrieve(
    "What is the main entry point?",
    top_k=5,
    expand_with_fact_store=False,
    enable_graph_expansion=True
)

print(f"Results: {len(results_with_expand)}")
for r in results_with_expand[:3]:
    r_dict = r if isinstance(r, dict) else r.__dict__
    print(f"  - {r_dict.get('name', 'N/A')} (type: {r_dict.get('type', 'N/A')})")

print()
print("=" * 80)

db.close()
