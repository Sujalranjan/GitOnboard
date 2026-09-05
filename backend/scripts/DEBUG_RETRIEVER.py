#!/usr/bin/env python3
"""Debug script to test retriever graph expansion."""
import sys
import logging

logging.basicConfig(level=logging.DEBUG, format="[%(name)s] %(message)s")

from backend.database import SessionLocal
from backend.models.repository import Analysis
from backend.intelligence.retrieval import HybridRetriever

# Get database session
db = SessionLocal()

# Get latest analysis (Deep-Guard-ML-Engine)
analysis = db.query(Analysis).filter_by(status='Completed').first()
if not analysis:
    print("No completed analysis found")
    sys.exit(1)

print(f"Testing with analysis: {analysis.repository.name} (id={analysis.id})")
print()

# Create retriever with graph expansion enabled
print("Creating retriever with enable_graph_expansion=True...")
retriever = HybridRetriever(
    db=db,
    analysis_id=analysis.id,
    enable_graph_expansion=True,
    graph_expansion_depth=2,
    graph_expansion_nodes_per_hop=3,
    graph_expansion_max_total=30,
)

print(f"Retriever instance: enable_graph_expansion={retriever.enable_graph_expansion}")
print()

# Test retrieval
query = "What is the main function?"
print(f"Testing retrieve with query: '{query}'")
print()

results = retriever.retrieve(query, top_k=5, expand_with_fact_store=False, enable_graph_expansion=True)

print(f"Retrieved {len(results)} results:")
for i, result in enumerate(results[:10]):
    result_dict = result if isinstance(result, dict) else result.__dict__
    print(f"{i+1}. {result_dict.get('name', 'N/A')}")
    print(f"   File: {result_dict.get('file_path', 'N/A')}")
    print(f"   Type: {result_dict.get('score_type', 'N/A')}")
    print(f"   Expansion source: {result_dict.get('expansion_source', 'none')}")
    print()
