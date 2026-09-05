#!/usr/bin/env python3
"""Root cause investigation for graph expansion finding 0 neighbors."""
import logging
from sqlalchemy import func
from backend.database import SessionLocal
from backend.models.fact_store import FactRelationship, FactSymbol, FactFile
from backend.models.repository import Analysis, Repository

logging.basicConfig(level=logging.INFO)

db = SessionLocal()

print("\n" + "=" * 80)
print("RIM GRAPH EXPANSION ROOT CAUSE INVESTIGATION")
print("=" * 80)

# Get analysis for Deep-Guard-ML-Engine (repository_id = 3)
repo_id = 3
analysis = db.query(Analysis).filter_by(
    repository_id=repo_id,
    status='Completed'
).first()

repo = db.query(Repository).filter_by(id=repo_id).first() if analysis else None

if not analysis:
    print(f"ERROR: No completed analysis found for repository ID {repo_id}")
    import sys
    sys.exit(1)

print(f"\nRepository ID: {repo_id}")
print(f"Repository URL: {repo.url if repo else 'N/A'}")
print(f"Analysis ID: {analysis.id}")
print(f"Commit SHA: {analysis.commit_sha if analysis.commit_sha else 'N/A'}")
print(f"Engine Version: {analysis.engine_version if analysis.engine_version else 'N/A'}")

analysis_id = analysis.id

# Step 1: Total relationships
print(f"\n{'STEP 1: Total Relationships':-^80}")
total_rels = db.query(func.count(FactRelationship.id)).filter(
    FactRelationship.analysis_id == analysis_id
).scalar()
print(f"Total relationships: {total_rels}")

if total_rels == 0:
    print("WARNING: Zero relationships in database!")

# Step 2: Relationship types
print(f"\n{'STEP 2: Relationship Types Distribution':-^80}")
rel_types = db.query(
    FactRelationship.rel_type,
    func.count(FactRelationship.id)
).filter(FactRelationship.analysis_id == analysis_id).group_by(
    FactRelationship.rel_type
).order_by(func.count(FactRelationship.id).desc()).all()

if rel_types:
    for rel_type, count in rel_types:
        print(f"  {rel_type:25} {count:6} relationships")
else:
    print("  No relationship types found")

# Step 3: Key relationship types
print(f"\n{'STEP 3: Key Relationship Types':-^80}")
key_types = {}
for key_type in ['CALLS', 'IMPORTS', 'CONTAINS', 'DEPENDS_ON', 'INHERITS', 'USES']:
    count = db.query(func.count(FactRelationship.id)).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.rel_type == key_type
    ).scalar()
    key_types[key_type] = count
    status = "✓" if count > 0 else "✗"
    print(f"  {status} {key_type:20} {count:6} relationships")

# Step 4: Entity counts
print(f"\n{'STEP 4: Entity Count':-^80}")
symbols = db.query(func.count(FactSymbol.id)).filter(
    FactSymbol.analysis_id == analysis_id
).scalar()
files = db.query(func.count(FactFile.id)).filter(
    FactFile.analysis_id == analysis_id
).scalar()
print(f"  FactSymbol: {symbols}")
print(f"  FactFile:   {files}")

# Step 5: Sample relationships
print(f"\n{'STEP 5: Sample Relationships':-^80}")

# Try to find a relationship type that exists
found_samples = False
for rel_type in ['CALLS', 'IMPORTS', 'CONTAINS']:
    if key_types.get(rel_type, 0) > 0:
        samples = db.query(FactRelationship).filter(
            FactRelationship.analysis_id == analysis_id,
            FactRelationship.rel_type == rel_type
        ).limit(3).all()

        if samples:
            print(f"\n  Sample {rel_type} relationships:")
            for i, rel in enumerate(samples, 1):
                print(f"\n    {i}. Relationship ID: {rel.id}")
                print(f"       From Symbol ID: {rel.from_symbol_id[:60] if rel.from_symbol_id else 'None'}")
                print(f"       To Symbol ID:   {rel.to_symbol_id[:60] if rel.to_symbol_id else 'None'}")
                print(f"       Type: {rel.rel_type}")

                # Check if IDs resolve
                if rel.from_symbol_id:
                    src_symbol = db.query(FactSymbol).filter(
                        FactSymbol.id == rel.from_symbol_id,
                        FactSymbol.analysis_id == analysis_id
                    ).first()

                    if src_symbol:
                        print(f"       From resolves to: {src_symbol.name} ({src_symbol.symbol_type})")
                    else:
                        print(f"       ✗ From Symbol ID does NOT resolve to FactSymbol")

            found_samples = True
            break

if not found_samples:
    print("  No relationships found in database")

# Step 6: Check if any anchors would be found by retrieval
print(f"\n{'STEP 6: Test Anchor Retrieval':-^80}")

# A simple test: look for symbols that match common entry points
test_terms = ['main', 'init', 'start', 'app', 'handler', 'authenticate']
print(f"\n  Looking for symbols matching: {test_terms}")

found_any = False
for term in test_terms:
    symbols = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis_id,
        FactSymbol.name.ilike(f'%{term}%')
    ).limit(3).all()

    if symbols:
        found_any = True
        print(f"\n  Symbols matching '{term}':")
        for sym in symbols:
            print(f"    - {sym.name} (type: {sym.symbol_type}, file_id: {sym.file_id})")

            # Check if this symbol has any outgoing relationships
            outgoing = db.query(func.count(FactRelationship.id)).filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.from_symbol_id == sym.id
            ).scalar()

            incoming = db.query(func.count(FactRelationship.id)).filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.to_symbol_id == sym.id
            ).scalar()

            print(f"      Outgoing relationships: {outgoing}")
            print(f"      Incoming relationships: {incoming}")

if not found_any:
    print("  No symbols found matching common entry point names")

# Step 7: Summary
print(f"\n{'INVESTIGATION SUMMARY':-^80}")
print(f"\n  Relationships exist: {'YES' if total_rels > 0 else 'NO'}")
print(f"  CALLS relationships: {key_types.get('CALLS', 0)} > 0: {'YES' if key_types.get('CALLS', 0) > 0 else 'NO'}")
print(f"  Direct traversal should work: {'YES' if key_types.get('CALLS', 0) > 0 or key_types.get('IMPORTS', 0) > 0 else 'NO'}")

print("\n" + "=" * 80 + "\n")

db.close()
