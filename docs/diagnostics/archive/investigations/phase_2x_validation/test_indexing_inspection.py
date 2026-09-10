#!/usr/bin/env python3
"""
Inspect indexing and retrieval layers.

Objective: Determine whether extracted symbols are indexed in BM25 and semantic search,
and whether HybridRetriever works correctly.
"""

import sys
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
import logging

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Add repo to path
sys.path.insert(0, "/home/dheeraj/repository_intelligence_platform")

from backend.database import Base, get_db
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactSymbol, FactFile, FactRoute, FactDatabaseObject, FactCapability
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.lexical import BM25Index, CodeTokenizer


def get_analysis_with_symbols() -> tuple[Session, Analysis]:
    """Find an analysis with symbols."""
    db = next(get_db())

    # Get the most recent analysis with symbols
    analysis = db.query(Analysis).filter(
        Analysis.status == "Completed"
    ).order_by(Analysis.id.desc()).first()

    if not analysis:
        logger.error("No completed analyses found")
        db.close()
        return None, None

    return db, analysis


def inspect_fact_store(db: Session, analysis: Analysis):
    """Inspect what's in the Fact Store for this analysis."""
    logger.info(f"Analysis {analysis.id} (repo_id={analysis.repository_id})")

    files_count = db.query(FactFile).filter(FactFile.analysis_id == analysis.id).count()
    symbols_count = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis.id).count()
    routes_count = db.query(FactRoute).filter(FactRoute.analysis_id == analysis.id).count()
    db_objs_count = db.query(FactDatabaseObject).filter(FactDatabaseObject.analysis_id == analysis.id).count()
    caps_count = db.query(FactCapability).filter(FactCapability.analysis_id == analysis.id).count()

    logger.info(f"Fact Store Contents:")
    logger.info(f"  Files: {files_count}")
    logger.info(f"  Symbols: {symbols_count}")
    logger.info(f"  Routes: {routes_count}")
    logger.info(f"  DB Objects: {db_objs_count}")
    logger.info(f"  Capabilities: {caps_count}")

    # Sample symbols
    if symbols_count > 0:
        sample_symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id
        ).limit(10).all()

        logger.info(f"\nSample Symbols (first 10 of {symbols_count}):")
        for sym in sample_symbols:
            logger.info(f"  - {sym.name} ({sym.symbol_type}) in file_id={sym.file_id} line {sym.line_start}-{sym.line_end}")

        # Show baseline symbols if available
        baseline_symbols = ["authenticate_token", "AuthService", "login"]
        logger.info(f"\nSearching for baseline symbols: {baseline_symbols}")
        for base_sym in baseline_symbols:
            found = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis.id,
                FactSymbol.name.ilike(f"%{base_sym}%")
            ).all()
            if found:
                logger.info(f"  Found '{base_sym}': {[s.name for s in found]}")

    return files_count, symbols_count, routes_count, db_objs_count, caps_count


def inspect_bm25_indexing(db: Session, analysis: Analysis):
    """Inspect BM25 indexing."""
    logger.info(f"\n=== BM25 Index Inspection ===")

    # Create retriever to build BM25 index
    retriever = HybridRetriever(db, analysis_id=analysis.id)

    if not retriever.bm25_index:
        logger.error("BM25 index failed to build")
        return

    idx = retriever.bm25_index
    logger.info(f"BM25 Index Statistics:")
    logger.info(f"  Document count: {idx.corpus_size}")
    logger.info(f"  Average doc length: {idx.avg_doc_len:.2f} tokens")
    logger.info(f"  Vocabulary size (unique terms): {len(idx.idf)}")

    if idx.documents:
        logger.info(f"\nSample indexed documents (first 10 of {len(idx.documents)}):")
        for doc in idx.documents[:10]:
            logger.info(f"  - id={doc.get('id')}, name={doc.get('name', '?')}, type={doc.get('type', '?')}")

    # Test queries
    test_queries = [
        "authenticate_token",
        "authentication",
        "login",
    ]

    logger.info(f"\nBM25 Query Results:")
    for query in test_queries:
        results = idx.search(query, top_k=5)
        logger.info(f"  Query '{query}': {len(results)} results")
        for doc, score in results[:3]:
            logger.info(f"    - {doc.get('name', '?')} (score={score:.3f}, type={doc.get('type', '?')})")

    return idx.corpus_size


def inspect_semantic_indexing(db: Session, analysis: Analysis):
    """Inspect semantic index."""
    logger.info(f"\n=== Semantic Index Inspection ===")

    retriever = HybridRetriever(db, analysis_id=analysis.id)

    if not retriever.chroma_collection:
        logger.warning(f"Semantic index not available: {retriever.semantic_degradation or 'unknown reason'}")
        return 0

    # Get collection count
    collection = retriever.chroma_collection
    try:
        count = collection.count()
        logger.info(f"Semantic index document count: {count}")

        # Try a test query
        test_query = "how does authentication work"
        try:
            results = collection.query(query_texts=[test_query], n_results=5)
            logger.info(f"\nSemantic query '{test_query}':")
            if results and results.get("metadatas"):
                for idx, meta in enumerate(results["metadatas"][0]):
                    dist = results["distances"][0][idx] if results.get("distances") else 0.0
                    logger.info(f"  - {meta.get('name', '?')} (distance={dist:.3f}, type={meta.get('type', '?')})")
            else:
                logger.info("  No results")
        except Exception as e:
            logger.warning(f"Semantic query failed: {e}")

        return count
    except Exception as e:
        logger.warning(f"Could not get semantic index count: {e}")
        return 0


def test_hybrid_retriever(db: Session, analysis: Analysis):
    """Test HybridRetriever end-to-end."""
    logger.info(f"\n=== HybridRetriever End-to-End Test ===")

    retriever = HybridRetriever(db, analysis_id=analysis.id)

    test_queries = [
        ("authenticate_token", "exact symbol name"),
        ("authentication", "concept search"),
        ("how does authentication work", "natural language"),
    ]

    for query, desc in test_queries:
        logger.info(f"\nQuery: '{query}' ({desc})")
        results = retriever.retrieve(query, top_k=5, expand_with_fact_store=False)
        logger.info(f"  Results: {len(results)}")
        for res in results[:3]:
            logger.info(f"    - {res.entity_name} ({res.entity_type.value})")
            logger.info(f"      file={res.file_path}, score={res.score:.3f}, score_type={res.score_type}")


def main():
    logger.info("=== Indexing and Retrieval Layer Inspection ===\n")

    db, analysis = get_analysis_with_symbols()
    if not db or not analysis:
        logger.error("Cannot proceed without a valid analysis")
        return

    # 1. Inspect Fact Store
    files, symbols, routes, db_objs, caps = inspect_fact_store(db, analysis)

    # 2. Inspect BM25 indexing
    bm25_count = inspect_bm25_indexing(db, analysis)

    # 3. Inspect Semantic indexing
    semantic_count = inspect_semantic_indexing(db, analysis)

    # 4. Test HybridRetriever
    test_hybrid_retriever(db, analysis)

    # 5. Summary report
    logger.info(f"\n=== SUMMARY REPORT ===")
    logger.info(f"\nFact Store:")
    logger.info(f"  Files: {files}")
    logger.info(f"  Symbols: {symbols}")
    logger.info(f"  Routes: {routes}")
    logger.info(f"  DB Objects: {db_objs}")
    logger.info(f"  Capabilities: {caps}")

    logger.info(f"\nBM25 Index:")
    logger.info(f"  Document count: {bm25_count}")

    logger.info(f"\nSemantic Index:")
    logger.info(f"  Document count: {semantic_count}")

    db.close()


if __name__ == "__main__":
    main()
