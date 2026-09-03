#!/usr/bin/env python3
"""
Verify the real analysis and test RIM with real data.
"""

import sys
import os
sys.path.insert(0, os.getcwd())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.fact_store import FactSymbol, FactFile, FactRelationship, FactRoute
from backend.models.repository import Analysis
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.services.rim_metadata import _build_rim_metadata_block_impl

engine = create_engine("sqlite:///./data/local.db")
Session = sessionmaker(bind=engine)
session = Session()

# Find Deep-Guard-Backend analysis (should be ID 3 from previous run)
analysis = session.query(Analysis).filter(Analysis.id == 3).first()

if not analysis:
    print("❌ Analysis 3 not found - run RUN_ANALYSIS_FIXED.py first")
    sys.exit(1)

print("=" * 80)
print(f"VERIFICATION & RIM TEST - Analysis {analysis.id}")
print("=" * 80)

# 1. Entity verification
print("\n=== ENTITY VERIFICATION ===")

files = session.query(FactFile).filter(FactFile.analysis_id == analysis.id).count()
symbols = session.query(FactSymbol).filter(FactSymbol.analysis_id == analysis.id).count()
relationships = session.query(FactRelationship).filter(FactRelationship.analysis_id == analysis.id).count()

print(f"Files: {files}")
print(f"Symbols: {symbols}")
print(f"Relationships: {relationships}")

# 2. Check specific auth entities
print("\n=== AUTH ENTITIES ===")

auth_entities = ["authMiddleware", "authenticateToken", "hashToken", "createSession"]
found_entities = {}

for entity_name in auth_entities:
    sym = session.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis.id,
        FactSymbol.name == entity_name
    ).first()

    if sym:
        print(f"✓ {entity_name}")
        print(f"    ID: {sym.id}")
        print(f"    Type: {sym.symbol_type}")
        print(f"    File: {sym.file_id}")
        print(f"    Lines: {sym.line_start}-{sym.line_end}")
        found_entities[entity_name] = sym
    else:
        print(f"✗ {entity_name} - NOT FOUND")

# 3. Check relationships
print("\n=== RELATIONSHIPS ===")

if found_entities:
    for entity_name, entity in found_entities.items():
        rels = session.query(FactRelationship).filter(
            FactRelationship.analysis_id == analysis.id,
            FactRelationship.from_symbol_id == entity.id
        ).all()

        if rels:
            print(f"\n{entity_name} relationships:")
            for rel in rels:
                target = session.query(FactSymbol).filter(FactSymbol.id == rel.to_symbol_id).first()
                target_name = target.name if target else rel.to_symbol_id
                print(f"  --[{rel.rel_type}]--> {target_name}")
        else:
            print(f"\n{entity_name}: No outgoing relationships")

# 4. Test retrieval
print("\n=== RETRIEVAL TEST ===")

retriever = HybridRetriever(session, analysis.id)

test_queries = [
    "auth",
    "authentication",
    "login",
    "authMiddleware"
]

for query in test_queries:
    results = retriever.retrieve(query, top_k=5, expand_with_fact_store=False)
    print(f"\nQuery: '{query}'")
    print(f"  Results: {len(results)}")
    for i, result in enumerate(results[:3]):
        print(f"    {i+1}. {result.entity_name} ({result.entity_type}) - score: {result.score:.3f}")

# 5. Test RIM
print("\n=== RIM METADATA TEST ===")

question = "How does auth work?"
print(f"Query: '{question}'")

metadata_block = _build_rim_metadata_block_impl(
    session,
    analysis.id,
    question,
    retriever,
    max_seed_entities=3,
    max_related_per_seed=8
)

print(f"\nRIM Results:")
print(f"  Metadata length: {len(metadata_block.text)}")
print(f"  Relationship types: {metadata_block.relationship_types_used}")
print(f"\nMetadata content:")
print(f"{metadata_block.text}")

# 6. Baseline retrieval comparison
print("\n=== BASELINE VS RIM COMPARISON ===")

print(f"\nBaseline retrieval for '{question}':")
baseline_results = retriever.retrieve(question, top_k=10, expand_with_fact_store=False)
print(f"  Total results: {len(baseline_results)}")
for i, result in enumerate(baseline_results[:5]):
    print(f"    {i+1}. {result.entity_name} - score: {result.score:.3f}")

print(f"\nRIM metadata facts:")
if "No structural facts" in metadata_block.text:
    print(f"  ✗ EMPTY - No facts generated")
else:
    fact_lines = metadata_block.text.strip().split('\n')
    print(f"  ✓ {len(fact_lines)} facts")
    for line in fact_lines[:5]:
        print(f"    - {line}")

# Final verdict
print("\n" + "=" * 80)
print("VERDICT")
print("=" * 80)

success = (
    files > 20 and
    symbols > 30 and
    relationships > 20 and
    len(found_entities) >= 2 and
    len(metadata_block.text) > 100 and
    "No structural facts" not in metadata_block.text
)

if success:
    print("✅ SUCCESS - Real analysis pipeline working end-to-end")
    print(f"   - Real entities: {symbols}")
    print(f"   - Real relationships: {relationships}")
    print(f"   - RIM metadata: Non-empty with facts")
else:
    print("❌ ISSUES FOUND")
    if symbols < 30:
        print(f"   - Low symbol count: {symbols}")
    if relationships < 20:
        print(f"   - Low relationship count: {relationships}")
    if len(found_entities) < 2:
        print(f"   - Missing key auth entities: {found_entities.keys()}")
    if "No structural facts" in metadata_block.text:
        print(f"   - RIM metadata empty")

session.close()
