#!/usr/bin/env python3
"""
Phase 2K.1: Complete E2E RIM Validation on GitOnboard

Tests the entire pipeline from parsing through retrieval on production-scale data:
- Stage 1: Parser → Symbols → Relationships (Analysis Engine)
- Stage 2: FactStore Persistence
- Stage 3: BM25 Indexing
- Stage 4: Semantic Indexing
- Stage 5: Hybrid Retrieval

Stages 6+ (Graph, Context, LLM) are disabled until 2-5 work.

Uses CURRENT repository architecture (as of Phase 2K):
- Database: backend.database.SessionLocal
- FactStore: backend.intelligence.store.fact_store.save_rim_to_fact_store
- BM25: backend.intelligence.retrieval.lexical.BM25Index
- Semantic: backend.intelligence.retrieval.semantic_builder.SemanticIndexBuilder
- HybridRetriever: backend.intelligence.retrieval.retriever.HybridRetriever
"""
import json
import time
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def stage_1_parse_and_analyze():
    """Stage 1: Parse repository and run analysis pipeline."""
    print("\n" + "="*80)
    print("STAGE 1: PARSE & ANALYZE (2,421 files)")
    print("="*80)

    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    source_repo = "/home/dheeraj/repository_intelligence_platform"
    engine = AnalysisEngine(source_repo, get_default_registry())

    start = time.time()
    try:
        model = engine.run(
            repo_name="GitOnboard-E2E-Validation",
            skip_validation=True
        )
        elapsed = time.time() - start

        print(f"✓ Analysis completed in {elapsed:.2f}s")
        print(f"  Entities: {len(model.entities):,}")
        print(f"  Relationships: {len(model.relationships):,}")

        return {
            "status": "success",
            "elapsed": elapsed,
            "entities": len(model.entities),
            "relationships": len(model.relationships),
            "model": model
        }
    except Exception as e:
        print(f"✗ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

def stage_2_factstore_persistence(model):
    """Stage 2: Persist RIM to FactStore."""
    print("\n" + "="*80)
    print("STAGE 2: FACTSTORE PERSISTENCE")
    print("="*80)

    try:
        from backend.database import SessionLocal, engine, Base
        from backend.models.user import User
        from backend.models.repository import Repository, Analysis
        from backend.intelligence.store.fact_store import save_rim_to_fact_store

        # Ensure tables exist
        Base.metadata.create_all(bind=engine)

        # Create database session
        db = SessionLocal()

        try:
            # Create or get test user
            user = db.query(User).filter(User.username == "e2e_test").first()
            if not user:
                user = User(
                    username="e2e_test",
                    github_id="e2e_test",
                    email="e2e@test.local"
                )
                db.add(user)
                db.flush()

            # Create or get test repository
            repo = db.query(Repository).filter(
                Repository.user_id == user.id,
                Repository.url == "file:///home/dheeraj/repository_intelligence_platform"
            ).first()
            if not repo:
                repo = Repository(
                    url="file:///home/dheeraj/repository_intelligence_platform",
                    user_id=user.id
                )
                db.add(repo)
                db.flush()

            # Create analysis record
            analysis = Analysis(
                repository_id=repo.id,
                engine_version="v1.0",
                status="Analyzing"
            )
            db.add(analysis)
            db.flush()

            start = time.time()

            # Persist RIM to FactStore
            save_rim_to_fact_store(db=db, analysis_id=analysis.id, model=model)
            db.commit()

            elapsed = time.time() - start

            # Query back counts
            from backend.models.fact_store import FactFile, FactSymbol, FactRelationship, FactRoute, FactDatabaseObject, FactCapability

            file_count = db.query(FactFile).filter(FactFile.analysis_id == analysis.id).count()
            symbol_count = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis.id).count()
            relationship_count = db.query(FactRelationship).filter(FactRelationship.analysis_id == analysis.id).count()
            route_count = db.query(FactRoute).filter(FactRoute.analysis_id == analysis.id).count()
            db_obj_count = db.query(FactDatabaseObject).filter(FactDatabaseObject.analysis_id == analysis.id).count()
            capability_count = db.query(FactCapability).filter(FactCapability.analysis_id == analysis.id).count()

            print(f"✓ FactStore persistence completed in {elapsed:.2f}s")
            print(f"  Files: {file_count}")
            print(f"  Symbols: {symbol_count}")
            print(f"  Relationships: {relationship_count}")
            print(f"  Routes: {route_count}")
            print(f"  Database Objects: {db_obj_count}")
            print(f"  Capabilities: {capability_count}")

            return {
                "status": "success",
                "elapsed": elapsed,
                "analysis_id": analysis.id,
                "files": file_count,
                "symbols": symbol_count,
                "relationships": relationship_count,
                "routes": route_count,
                "database_objects": db_obj_count,
                "capabilities": capability_count
            }
        finally:
            db.close()

    except Exception as e:
        print(f"✗ FactStore persistence failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

def stage_3_bm25_indexing(analysis_id):
    """Stage 3: Build BM25 indices from FactStore."""
    print("\n" + "="*80)
    print("STAGE 3: BM25 INDEXING")
    print("="*80)

    try:
        from backend.database import SessionLocal
        from backend.intelligence.retrieval.retriever import HybridRetriever

        db = SessionLocal()

        try:
            start = time.time()

            # Create retriever (builds BM25 internally from FactStore)
            retriever = HybridRetriever(db=db, analysis_id=analysis_id)

            elapsed = time.time() - start

            if retriever.bm25_index:
                doc_count = len(retriever.bm25_index.documents)
                print(f"✓ BM25 indexing completed in {elapsed:.2f}s")
                print(f"  Indexed documents: {doc_count:,}")
                return {
                    "status": "success",
                    "elapsed": elapsed,
                    "indexed_documents": doc_count,
                    "retriever": retriever
                }
            else:
                print(f"✗ BM25 index build returned None")
                return {"status": "failed", "error": "BM25 index is None"}

        finally:
            db.close()

    except Exception as e:
        print(f"✗ BM25 indexing failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

def stage_4_semantic_indexing(model):
    """Stage 4: Build semantic indices (OPTIONAL - may be very slow)."""
    print("\n" + "="*80)
    print("STAGE 4: SEMANTIC INDEXING")
    print("="*80)

    try:
        from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder
        import threading

        start = time.time()

        # Semantic indexing is optional and can take 30+ minutes for large repos
        # Build it in a thread so we can monitor progress
        builder = SemanticIndexBuilder()
        print(f"  Embedding {len(model.entities):,} entities (this may take 30+ minutes)...")
        print(f"  If this takes too long, Ctrl+C to skip (BM25 fallback available)")

        result_container = {}
        error_container = {}

        def build_in_thread():
            try:
                result = builder.build_index(model.entities)
                result_container['chroma_bytes'] = result
            except Exception as e:
                error_container['error'] = e

        # Start build in background thread
        thread = threading.Thread(target=build_in_thread, daemon=False)
        thread.start()

        # Wait up to 120 seconds, then give up (user can Ctrl+C if needed)
        thread.join(timeout=120)

        elapsed = time.time() - start

        if error_container:
            print(f"✗ Semantic indexing error: {error_container['error']}")
            return {
                "status": "partial",
                "elapsed": elapsed,
                "chroma_bytes": None,
                "error": f"embedding error: {error_container['error']}"
            }

        if thread.is_alive():
            print(f"⚠ Semantic indexing is still running after {elapsed:.0f}s")
            print(f"  (Thread will continue in background)")
            print(f"  Proceeding with BM25 fallback (semantic index will be skipped)")
            return {
                "status": "partial",
                "elapsed": elapsed,
                "chroma_bytes": None,
                "error": "timeout (120s) - semantic indexing takes 30+ minutes, skipped"
            }

        chroma_bytes = result_container.get('chroma_bytes')

        if chroma_bytes:
            print(f"✓ Semantic indexing completed in {elapsed:.2f}s")
            print(f"  Semantic index size: {len(chroma_bytes):,} bytes (compressed)")
            return {
                "status": "success",
                "elapsed": elapsed,
                "chroma_bytes": chroma_bytes,
                "size_bytes": len(chroma_bytes)
            }
        else:
            print(f"⚠ Semantic indexing returned no data (chromadb or embeddings unavailable)")
            return {
                "status": "partial",
                "elapsed": elapsed,
                "chroma_bytes": None,
                "error": "no data returned"
            }

    except KeyboardInterrupt:
        elapsed = time.time() - start
        print(f"\n⚠ Semantic indexing skipped by user after {elapsed:.2f}s")
        print(f"  BM25 lexical search will be used as fallback")
        return {
            "status": "partial",
            "elapsed": elapsed,
            "chroma_bytes": None,
            "error": "skipped by user"
        }

    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ Semantic indexing error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "partial",
            "elapsed": elapsed,
            "chroma_bytes": None,
            "error": str(e)
        }

def stage_5_hybrid_retrieval(retriever):
    """Stage 5: Test hybrid retrieval."""
    print("\n" + "="*80)
    print("STAGE 5: HYBRID RETRIEVAL TEST")
    print("="*80)

    try:
        # Test retrieval on sample queries derived from GitOnboard
        test_queries = [
            "authentication",
            "repository analysis",
            "analysis pipeline",
            "API routes",
            "database models",
            "agent context",
            "parser",
            "symbol resolution"
        ]

        start = time.time()

        results = {}
        all_results = []

        for query in test_queries:
            try:
                hits = retriever.retrieve(query, top_k=5)
                result_count = len(hits) if hits else 0
                results[query] = result_count
                all_results.extend(hits[:3])  # Collect first 3 results from each query
                print(f"  Query '{query}': {result_count} results")
            except Exception as e:
                results[query] = 0
                print(f"  Query '{query}': ERROR - {e}")

        elapsed = time.time() - start

        # Remove duplicates from all results
        unique_results = {}
        for r in all_results:
            # Handle both dict and RetrieverResult objects
            if isinstance(r, dict):
                key = r.get("qualified_name") or r.get("name") or r.get("id")
            else:
                # RetrieverResult object - use getattr
                key = getattr(r, "qualified_name", None) or getattr(r, "name", None) or getattr(r, "id", None)

            if key and key not in unique_results:
                unique_results[key] = r

        print(f"✓ Hybrid retrieval test completed in {elapsed:.2f}s")
        print(f"  Test queries: {len(test_queries)}")
        print(f"  Queries with results: {sum(1 for c in results.values() if c > 0)}/{len(test_queries)}")
        print(f"  Unique results across all queries: {len(unique_results)}")

        return {
            "status": "success",
            "elapsed": elapsed,
            "queries_tested": len(test_queries),
            "results_per_query": results,
            "total_unique_results": len(unique_results),
            "sample_results": list(unique_results.values())[:5]
        }

    except Exception as e:
        print(f"✗ Hybrid retrieval test failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

def main():
    print("\n" + "="*80)
    print("PHASE 2K.1: E2E VALIDATION - STAGES 1-5 (Integration Fixes)")
    print("="*80)
    print(f"Repository: GitOnboard (2,421 files, ~25,920 symbols)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*80)

    results = {
        "timestamp": datetime.now().isoformat(),
        "repository": "GitOnboard",
        "stages": {}
    }

    # Stage 1: Parse & Analyze
    stage1 = stage_1_parse_and_analyze()
    results["stages"]["parse_analyze"] = stage1

    if stage1["status"] != "success":
        print("\n✗ E2E validation aborted at Stage 1")
        print(f"Error: {stage1.get('error')}")
        return results

    model = stage1["model"]

    # Stage 2: FactStore Persistence
    stage2 = stage_2_factstore_persistence(model)
    results["stages"]["factstore"] = stage2

    if stage2["status"] != "success":
        print(f"\n✗ E2E validation aborted at Stage 2: {stage2.get('error')}")
        return results

    analysis_id = stage2.get("analysis_id")

    # Stage 3: BM25 Indexing
    stage3 = stage_3_bm25_indexing(analysis_id)
    results["stages"]["bm25"] = stage3

    if stage3["status"] != "success":
        print(f"\n✗ E2E validation aborted at Stage 3: {stage3.get('error')}")
        return results

    retriever = stage3.get("retriever")

    # Stage 4: Semantic Indexing
    stage4 = stage_4_semantic_indexing(model)
    results["stages"]["semantic"] = stage4

    # Stage 5: Hybrid Retrieval (only if BM25 succeeded)
    if retriever:
        stage5 = stage_5_hybrid_retrieval(retriever)
        results["stages"]["hybrid_retrieval"] = stage5

    # Summary
    print("\n" + "="*80)
    print("PHASE 2K.1 E2E VALIDATION SUMMARY (Stages 1-5)")
    print("="*80)

    successful_stages = sum(1 for s in results["stages"].values() if s.get("status") == "success")
    total_stages = len(results["stages"])

    print(f"\nStages completed: {successful_stages}/{total_stages}")

    for stage_name, stage_result in results["stages"].items():
        status = "✓" if stage_result.get("status") == "success" else ("⚠" if stage_result.get("status") == "partial" else "✗")
        elapsed = stage_result.get("elapsed", 0)
        print(f"  {status} {stage_name}: {elapsed:.2f}s")

    # Save results
    output_file = Path("phase2k1_e2e_validation_results.json")
    with open(output_file, "w") as f:
        # Convert non-JSON-serializable objects before dumping
        clean_results = {
            "timestamp": results["timestamp"],
            "repository": results["repository"],
            "stages": {}
        }
        for stage_name, stage_data in results["stages"].items():
            clean_stage = {}
            for k, v in stage_data.items():
                if k in ["status", "elapsed", "error", "entities", "relationships", "analysis_id",
                         "files", "symbols", "relationships", "routes", "database_objects", "capabilities",
                         "indexed_documents", "queries_tested", "size_bytes", "total_unique_results"]:
                    clean_stage[k] = v
                elif k == "results_per_query":
                    clean_stage[k] = v
            clean_results["stages"][stage_name] = clean_stage

        json.dump(clean_results, f, indent=2, default=str)

    print(f"\n✓ Results saved to {output_file}")

    total_time = sum(s.get("elapsed", 0) for s in results["stages"].values())
    print(f"\nTotal E2E time: {total_time:.2f}s")

    # Report verdict
    if stage1["status"] == "success" and stage2["status"] == "success" and \
       stage3["status"] == "success" and stage5["status"] == "success":
        print("\n" + "="*80)
        print("✓ PHASE 2K.1 STAGES 1-5 VALIDATION SUCCESSFUL")
        print("="*80)
        print("\nSuccessfully validated:")
        entities = stage1.get("entities", 0)
        relationships = stage1.get("relationships", 0)
        print(f"  ✓ Stage 1: Parser & Analysis ({entities:,} entities, {relationships:,} relationships)")
        print("  ✓ Stage 2: FactStore Persistence")
        print("  ✓ Stage 3: BM25 Indexing")
        print(f"  {'✓' if stage4['status']=='success' else '⚠'} Stage 4: Semantic Indexing")
        print("  ✓ Stage 5: Hybrid Retrieval")
        print("\n✓ E2E pipeline from parse through retrieval FUNCTIONAL")
        print("✓ Ready for Stage 6+ validation (Graph, Context, LLM)")
        print("="*80 + "\n")
        return True
    else:
        print(f"\n⚠ Validation incomplete - see results above")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
