#!/usr/bin/env python3
"""
Phase 2A Diagnostic: Trace HybridRetriever at each stage
Measures exact candidate counts for "How does authentication work?" query
"""

import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s] %(message)s",
)
logger = logging.getLogger("PHASE2A")

# Silence verbose loggers
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


def main():
    from backend.database import SessionLocal
    from backend.models.user import User
    from backend.routers.repo.services.analysis import get_latest_analysis
    from backend.intelligence.retrieval.retriever import HybridRetriever
    from backend.models.fact_store import FactSymbol

    db = SessionLocal()

    try:
        print("\n" + "=" * 80)
        print("PHASE 2A: HybridRetriever Diagnostic Trace")
        print("=" * 80)

        # Get user and analysis
        user = db.query(User).first()
        if not user:
            print("[✗] No users found in database")
            return False

        repo, analysis = get_latest_analysis("GitOnboard", db, current_user=user)
        analysis_id = analysis.id

        print(f"\n[Repository]")
        print(f"  Analysis ID: {analysis_id}")
        print(f"  Repository: GitOnboard")

        # Get baseline stats from FactStore
        auth_symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.name.ilike("%auth%")
        ).all()

        print(f"\n[FactStore Baseline]")
        print(f"  Total auth symbols: {len(auth_symbols)}")
        for s in auth_symbols[:5]:
            print(f"    - {s.name}")

        # ──────────────────────────────────────────────────────────────
        # Initialize HybridRetriever
        # ──────────────────────────────────────────────────────────────
        print(f"\n{'=' * 80}")
        print("Initializing HybridRetriever")
        print("=" * 80)

        retriever = HybridRetriever(
            db=db,
            analysis_id=analysis_id,
            enable_graph_expansion=False,  # Disable expansion for stage tracing
        )

        # Report index status
        bm25_status = "✓ Loaded" if retriever.bm25_index else "✗ None"
        chroma_status = "✓ Available" if retriever.chroma_collection else "✗ None"

        print(f"\n[Index Status]")
        print(f"  BM25: {bm25_status}")
        if retriever.bm25_index:
            print(f"    - Corpus size: {retriever.bm25_index.corpus_size}")
            print(f"    - Documents: {len(retriever.bm25_index.documents) if retriever.bm25_index.documents else 0}")
            print(f"    - Avg doc len: {retriever.bm25_index.avg_doc_len:.1f}")

        print(f"  Chroma: {chroma_status}")
        if retriever.semantic_degradation:
            print(f"    - Degradation reason: {retriever.semantic_degradation}")

        # ──────────────────────────────────────────────────────────────
        # Test queries
        # ──────────────────────────────────────────────────────────────
        test_queries = [
            "How does authentication work?",
            "authentication",
            "authenticateToken",
            "auth",
        ]

        for query in test_queries:
            print(f"\n{'=' * 80}")
            print(f"Query: '{query}'")
            print("=" * 80)

            # Test each retrieval method directly
            print(f"\n[Stage 1: Exact Facts Search]")
            exact_results = retriever._search_exact_facts(query)
            print(f"  Candidates: {len(exact_results)}")
            for r in exact_results[:3]:
                print(f"    - {r.get('name')} ({r.get('type')})")

            print(f"\n[Stage 2: Lexical (BM25) Search]")
            lexical_results = retriever._search_lexical(query, top_k=30)
            print(f"  Candidates: {len(lexical_results)}")
            for r in lexical_results[:3]:
                name = r.get('name', r.get('match_name', '?'))
                score = r.get('bm25_score', 0)
                print(f"    - {name} (score: {score:.2f})")

            print(f"\n[Stage 3: Semantic Search]")
            semantic_results = retriever._search_semantic(query, top_k=30)
            print(f"  Candidates: {len(semantic_results)}")
            for r in semantic_results[:3]:
                name = r.get('name', '?')
                dist = r.get('distance', 0)
                print(f"    - {name} (distance: {dist:.2f})")

            print(f"\n[Stage 4: RRF Fusion]")
            ranked_lists = []
            weights = []

            if exact_results:
                ranked_lists.append(exact_results)
                weights.append(retriever.exact_weight)
            if lexical_results:
                ranked_lists.append(lexical_results)
                weights.append(retriever.lexical_weight)
            if semantic_results:
                ranked_lists.append(semantic_results)
                weights.append(retriever.semantic_weight)

            if ranked_lists:
                from backend.intelligence.retrieval.fusion import reciprocal_rank_fusion
                fused = reciprocal_rank_fusion(
                    ranked_lists=ranked_lists,
                    weights=weights,
                    rrf_k=retriever.rrf_k,
                    key_field="id",
                    top_k=30
                )
                print(f"  Fused candidates: {len(fused)}")
                for r in fused[:3]:
                    name = r.get('name', r.get('match_name', '?'))
                    score = r.get('rrf_score', 0)
                    sources = r.get('sources', [])
                    print(f"    - {name} (RRF: {score:.2f}, sources: {sources})")
            else:
                print(f"  [✗] No ranked lists to fuse")
                fused = []

            print(f"\n[Stage 5: Full retrieve() call]")
            full_results = retriever.retrieve(query, top_k=10, enable_graph_expansion=False)
            print(f"  Final results: {len(full_results)}")
            for r in full_results[:3]:
                print(f"    - {r.entity_name} ({r.entity_type})")

            # Summary table
            print(f"\n[Summary]")
            print(f"  Exact: {len(exact_results):2d} | Lexical: {len(lexical_results):2d} | Semantic: {len(semantic_results):2d} | Fused: {len(fused):2d} | Final: {len(full_results):2d}")

        # ──────────────────────────────────────────────────────────────
        # BM25 Corpus Inspection
        # ──────────────────────────────────────────────────────────────
        if retriever.bm25_index and retriever.bm25_index.documents:
            print(f"\n{'=' * 80}")
            print("BM25 Corpus Inspection")
            print("=" * 80)

            auth_in_corpus = [d for d in retriever.bm25_index.documents if "auth" in d.lower()]
            print(f"\n[BM25 Corpus Docs Containing 'auth']")
            print(f"  Count: {len(auth_in_corpus)}")
            for doc in auth_in_corpus[:5]:
                print(f"    - {doc[:80]}...")

        # ──────────────────────────────────────────────────────────────
        # Final Verdict
        # ──────────────────────────────────────────────────────────────
        print(f"\n{'=' * 80}")
        print("DIAGNOSTIC VERDICT")
        print("=" * 80)

        if not retriever.bm25_index:
            print("\n[✗] CRITICAL: BM25 index is None")
            print("    Cannot perform lexical retrieval at all")
            return False

        if retriever.bm25_index.corpus_size == 0:
            print("\n[✗] CRITICAL: BM25 corpus is empty")
            print("    No documents in index")
            return False

        if len(exact_results) == 0 and len(lexical_results) == 0 and len(semantic_results) == 0:
            print("\n[✗] CRITICAL: All retrieval methods returned 0 candidates")
            print("    Even for exact match queries")
            return False

        print("\n[✓] Retrieval pipeline functional")
        print("    Some candidates found in at least one method")
        return True

    finally:
        db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
