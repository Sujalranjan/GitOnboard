#!/usr/bin/env python3
"""
Analyze Deep-Guard-Backend using the fixed environment.

This script runs in the uv environment where dependencies are properly installed.
"""

import sys
import os
sys.path.insert(0, os.getcwd())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from pathlib import Path

from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship, FactRoute

engine = create_engine("sqlite:///./data/local.db")
Session = sessionmaker(bind=engine)
session = Session()

print("=" * 80)
print("DEEP-GUARD-BACKEND ANALYSIS - FIXED ENVIRONMENT")
print("=" * 80)

# 1. Setup
print("\n=== SETUP ===")

deep_guard_url = "https://github.com/salianDheeraj/Deep-Guard-Backend"
deep_guard_path = Path("/home/dheeraj/Deep-Guard/Deep-Guard-Backend")

# Get user
user = session.query(User).first()
if not user:
    print("❌ No user found")
    sys.exit(1)

# Create repo
repo = session.query(Repository).filter(Repository.url.ilike("%Deep-Guard-Backend%")).first()
if not repo:
    repo = Repository(url=deep_guard_url, default_branch="main", user_id=user.id)
    session.add(repo)
    session.flush()

print(f"Repository: {repo.url} (ID: {repo.id})")

# Create analysis
analysis = Analysis(repository_id=repo.id, status="Queued", engine_version="v1.0")
session.add(analysis)
session.flush()

print(f"Analysis: {analysis.id}")

# Create job
job = AnalysisJob(analysis_id=analysis.id, status="Analyzing")
session.add(job)
session.flush()

print(f"Job: {job.id}")

session.commit()

# 2. Run analysis
print("\n=== RUNNING ANALYSIS ===")

try:
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry
    from backend.intelligence.capabilities.engine import CapabilityBuilderEngine
    from backend.intelligence.features.engine import FeatureReconstructionEngine
    from backend.intelligence.store.fact_store import save_rim_to_fact_store
    from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder
    from backend.intelligence.retrieval.retriever import HybridRetriever

    print(f"Analyzing {deep_guard_path}...")

    # 2a. Static analysis
    engine_obj = AnalysisEngine(str(deep_guard_path), get_default_registry())
    model = engine_obj.run("Deep-Guard-Backend", commit_info=None)

    print(f"✓ Analysis complete")
    print(f"  Entities: {len(model.entities)}")
    print(f"  Relationships: {len(model.relationships)}")

    # 2b. Capabilities
    print(f"Running capability engine...")
    cap_engine = CapabilityBuilderEngine()
    model = cap_engine.run(model)
    print(f"✓ Capabilities extracted")

    # 2c. Features
    print(f"Running feature engine...")
    feat_engine = FeatureReconstructionEngine()
    model = feat_engine.run(model)
    print(f"✓ Features extracted")

    # 2d. Persistence
    print(f"Persisting to FactStore...")
    save_rim_to_fact_store(session, analysis.id, model)
    session.commit()
    print(f"✓ Persisted")

    # 2e. Indexes
    print(f"Building retrieval indexes...")
    retriever_obj = HybridRetriever(db=session, analysis_id=analysis.id)
    print(f"  BM25 index: {len(retriever_obj.bm25_index.documents) if retriever_obj.bm25_index else 0} documents")

    semantic_builder = SemanticIndexBuilder()
    chroma_bytes = semantic_builder.build_index(model.entities)
    print(f"  Semantic index: {len(chroma_bytes) if chroma_bytes else 0} bytes")

    # Mark complete
    analysis.status = "Completed"
    job.status = "Completed"
    job.completed_at = datetime.now(timezone.utc)
    session.commit()

    print(f"\n✓ Analysis completed successfully!")

except Exception as e:
    print(f"\n❌ Analysis failed: {e}")
    import traceback
    traceback.print_exc()

    analysis.status = "Failed"
    job.status = "Failed"
    job.error = str(e)
    session.commit()
    sys.exit(1)

# 3. Verify results
print("\n=== VERIFICATION ===")

files = session.query(FactFile).filter(FactFile.analysis_id == analysis.id).count()
symbols = session.query(FactSymbol).filter(FactSymbol.analysis_id == analysis.id).count()
routes = session.query(FactRoute).filter(FactRoute.analysis_id == analysis.id).count()
relationships = session.query(FactRelationship).filter(FactRelationship.analysis_id == analysis.id).count()

print(f"Files: {files}")
print(f"Symbols: {symbols}")
print(f"Routes: {routes}")
print(f"Relationships: {relationships}")

# Check auth symbols
auth_symbols = session.query(FactSymbol).filter(
    FactSymbol.analysis_id == analysis.id,
    (FactSymbol.name.ilike("%auth%") | FactSymbol.name.ilike("%login%"))
).all()

if auth_symbols:
    print(f"\nAuth-related symbols ({len(auth_symbols)}):")
    for sym in auth_symbols[:10]:
        print(f"  - {sym.name} ({sym.symbol_type})")
else:
    print(f"\n⚠ No auth-related symbols found")

session.close()
print("\n✓ Complete")
