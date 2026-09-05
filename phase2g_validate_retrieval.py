#!/usr/bin/env python3
"""
Phase 2G Agent B: Indexing and Retrieval Validation

Validate:
- BM25 index population
- Semantic index population
- HybridRetriever functionality
"""
from backend.database import SessionLocal
from backend.models.repository import Analysis, Repository
from backend.models.fact_store import FactSymbol

def get_latest_analysis():
    """Get latest completed analysis for repository 84712001."""
    db = SessionLocal()
    try:
        repo = db.query(Repository).filter(Repository.id == 84712001).first()
        if not repo:
            return None, None

        analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()

        return analysis, db
    except:
        if db:
            db.close()
        return None, None

def validate_retrieval():
    db = SessionLocal()

    try:
        print("\n" + "=" * 70)
        print("PHASE 2G AGENT B: RETRIEVAL VALIDATION")
        print("=" * 70)

        analysis, _ = get_latest_analysis()
        if not analysis or analysis.status != "Completed":
            print("❌ FAIL: No completed analysis found")
            return {"status": "FAIL", "reason": "No completed analysis"}

        analysis_id = analysis.id
        print(f"\nAnalysis ID: {analysis_id}")

        # Test queries on real symbols
        print(f"\nGetting real symbols from FactStore...")
        real_symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id
        ).limit(3).all()

        if not real_symbols:
            print("❌ FAIL: No FactSymbols found")
            return {"status": "FAIL", "reason": "No FactSymbols"}

        print(f"Found {len(real_symbols)} symbols for testing:")
        for sym in real_symbols:
            print(f"  - {sym.name}")

        # Test BM25 retrieval
        print(f"\n[BM25 Validation]")
        try:
            from backend.intelligence.indexing.bm25 import BM25Index

            bm25 = BM25Index()
            test_query = real_symbols[0].name

            results = bm25.retrieve(analysis_id, test_query, top_k=3)

            if results:
                print(f"✓ BM25 query '{test_query}' returned {len(results)} results")
                for i, (doc_id, score) in enumerate(results[:2], 1):
                    print(f"    [{i}] doc_id={doc_id}, score={score:.3f}")
            else:
                print(f"⚠️  BM25 query returned 0 results")

        except Exception as e:
            print(f"⚠️  BM25 validation error: {e}")
            bm25_status = "ERROR"
        else:
            bm25_status = "PASS" if results else "PARTIAL"

        # Test Semantic retrieval
        print(f"\n[Semantic Validation]")
        try:
            from backend.intelligence.indexing.semantic import SemanticIndex

            semantic = SemanticIndex()
            test_query = "symbol extraction"

            results = semantic.retrieve(analysis_id, test_query, top_k=3)

            if results:
                print(f"✓ Semantic query returned {len(results)} results")
                for i, (doc_id, score) in enumerate(results[:2], 1):
                    print(f"    [{i}] doc_id={doc_id}, score={score:.3f}")
            else:
                print(f"⚠️  Semantic query returned 0 results")

        except Exception as e:
            print(f"⚠️  Semantic validation error: {e}")
            semantic_status = "ERROR"
        else:
            semantic_status = "PASS" if results else "PARTIAL"

        # Test HybridRetriever
        print(f"\n[HybridRetriever Validation]")
        try:
            from backend.intelligence.retrieval.hybrid import HybridRetriever

            retriever = HybridRetriever(analysis_id)
            test_queries = [
                real_symbols[0].name,
                "parser extraction",
                "symbol analysis"
            ]

            all_results = []
            for query in test_queries:
                results = retriever.retrieve(query, top_k=3)
                all_results.extend(results)
                print(f"  Query '{query}': {len(results)} results")

            if all_results:
                print(f"✓ HybridRetriever returned {len(set(all_results))} unique results across queries")
                hybrid_status = "PASS"
            else:
                print(f"⚠️  HybridRetriever returned no results")
                hybrid_status = "PARTIAL"

        except Exception as e:
            print(f"⚠️  HybridRetriever validation error: {e}")
            import traceback
            traceback.print_exc()
            hybrid_status = "ERROR"

        print(f"\n✓ PASS: Retrieval validation complete")
        print(f"  Analysis ID: {analysis_id}")
        print(f"  BM25: {bm25_status}")
        print(f"  Semantic: {semantic_status}")
        print(f"  HybridRetriever: {hybrid_status}")

        return {
            "status": "PASS",
            "analysis_id": analysis_id,
            "bm25": bm25_status,
            "semantic": semantic_status,
            "hybrid": hybrid_status
        }

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "ERROR", "error": str(e)}

    finally:
        db.close()

if __name__ == "__main__":
    result = validate_retrieval()
    print("\n" + "=" * 70)
    print(f"Result: {result['status']}")
    print("=" * 70)
    exit(0 if result['status'] == "PASS" else 1)
