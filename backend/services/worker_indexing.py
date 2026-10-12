"""
Indexing and Analysis Artifact Persistence helpers for AnalysisWorker.
Handles BM25 index creation, health tracking, and background Chroma semantic indexing.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.repository import Analysis, AnalysisArtifact
from backend.models.fact_store import FactSymbol
from backend.intelligence.retrieval.indexing_health import (
    IndexStatus, OverallIndexingStatus, IndexFailureCode,
    IndexingHealthReport, IndexHealthSnapshot, record_indexing_failure,
    compute_overall_status
)

logger = logging.getLogger(__name__)


def build_and_record_indexes(
    db: Session,
    analysis: Analysis,
    rim_model: Any,
    results: Dict[str, Any],
    progress: Any
) -> Tuple[bool, bool, bool]:
    """
    Builds BM25 index, records indexing health, and updates analysis record.
    Returns (exact_ok, bm25_ok, semantic_ok).
    """
    exact_ok = False
    bm25_ok = False
    semantic_ok = False

    if rim_model:
        try:
            from backend.intelligence.store.fact_store import save_rim_to_fact_store
            save_rim_to_fact_store(db, analysis.id, rim_model)
            entity_count = len(rim_model.entities)
            logger.info(f"Saved {entity_count} entities to Fact Store")
            exact_ok = True  # Exact search depends on FactStore

            # Update progress after persistence
            progress.update(
                "Persisting facts",
                f"Saved {entity_count} entities to database",
                entity_count,
                entity_count,
                "entities"
            )
        except Exception as e:
            db.rollback()
            logger.error(f"Error persisting facts to Fact Store: {e}")

        # Generate immutability version for FactStore
        analysis.fact_store_version = str(uuid.uuid4())

        logger.info("Building semantic and lexical indexes...")

        bm25_doc_count = 0
        bm25_error_code = None
        bm25_error_msg = ""

        semantic_doc_count = 0
        semantic_error_code = None
        semantic_error_msg = ""

        try:
            from backend.intelligence.retrieval.retriever import HybridRetriever

            # Build BM25 index and store in memory for export
            try:
                retriever_temp = HybridRetriever(db=db, analysis_id=analysis.id)
                if retriever_temp.bm25_index:
                    bm25_doc_count = retriever_temp.bm25_index.corpus_size
                    bm25_data = {
                        "documents": retriever_temp.bm25_index.documents,
                        "idf": dict(retriever_temp.bm25_index.idf),
                        "doc_len": retriever_temp.bm25_index.doc_len,
                        "corpus_size": retriever_temp.bm25_index.corpus_size,
                        "avg_doc_len": retriever_temp.bm25_index.avg_doc_len,
                        "fact_store_version": analysis.fact_store_version,
                    }
                    results["bm25_index"] = bm25_data
                    logger.info(f"BM25 index ready with {bm25_doc_count} documents (version={analysis.fact_store_version[:8]}...)")

                    progress.update(
                        "Building indexes",
                        f"Built BM25 index with {bm25_doc_count} documents",
                        bm25_doc_count,
                        bm25_doc_count,
                        "documents"
                    )
                    bm25_ok = True
                else:
                    if not rim_model.entities:
                        bm25_error_code = IndexFailureCode.BM25_EMPTY_FACTSTORE
                        bm25_error_msg = "No entities in FactStore"
                    else:
                        bm25_error_code = IndexFailureCode.BM25_BUILD_FAILED
                        bm25_error_msg = "BM25 index creation returned None"
                    record_indexing_failure(analysis.id, "bm25", bm25_error_code, bm25_error_msg)
            except Exception as bm25_err:
                bm25_error_code = IndexFailureCode.BM25_BUILD_FAILED
                bm25_error_msg = str(bm25_err)[:100]
                record_indexing_failure(analysis.id, "bm25", bm25_error_code, bm25_error_msg)

            # Build Chroma semantic index (BACKGROUND, NON-BLOCKING)
            logger.info("Semantic (Chroma) indexing: SCHEDULED for background processing (non-blocking)")
            semantic_error_code = IndexFailureCode.CHROMA_UNAVAILABLE
            semantic_error_msg = "Semantic indexing scheduled for background (non-blocking)"

        except Exception as e:
            logger.error(f"Failed to build retrieval indexes: {e}", exc_info=True)
            if not bm25_ok and not bm25_error_code:
                bm25_error_code = IndexFailureCode.BM25_BUILD_FAILED
                bm25_error_msg = str(e)[:100]
            if not semantic_ok and not semantic_error_code:
                semantic_error_code = IndexFailureCode.CHROMA_BUILD_FAILED
                semantic_error_msg = str(e)[:100]

        # Record indexing health
        overall_status = compute_overall_status(exact_ok, bm25_ok, semantic_ok)
        health_report = IndexingHealthReport(
            overall_status=overall_status,
            exact=IndexHealthSnapshot(
                status=IndexStatus.SUCCESS if exact_ok else IndexStatus.FAILED,
                document_count=len(rim_model.entities) if exact_ok else 0,
            ),
            bm25=IndexHealthSnapshot(
                status=IndexStatus.SUCCESS if bm25_ok else IndexStatus.FAILED,
                document_count=bm25_doc_count,
                error_code=bm25_error_code,
                error_message=bm25_error_msg,
                created_at=datetime.now(timezone.utc),
            ),
            semantic=IndexHealthSnapshot(
                status=IndexStatus.SUCCESS if semantic_ok else (
                    IndexStatus.UNAVAILABLE if semantic_error_code == IndexFailureCode.CHROMA_UNAVAILABLE else IndexStatus.FAILED
                ),
                document_count=semantic_doc_count,
                error_code=semantic_error_code,
                error_message=semantic_error_msg,
                created_at=datetime.now(timezone.utc),
            ),
        )

        analysis.indexing_status = overall_status.value
        analysis.indexing_details = health_report.to_dict()
        analysis.indexed_at = datetime.now(timezone.utc)
        logger.info(f"Indexing health: overall={overall_status.value} exact={exact_ok} bm25={bm25_ok} semantic={semantic_ok}")

    return exact_ok, bm25_ok, semantic_ok


def build_semantic_index_background(analysis_id: int):
    """
    Build semantic (Chroma) index in background thread.

    Loads entities from FactStore (not stale in-memory dict).
    Runs after analysis is marked COMPLETED, non-blocking.
    Stores semantic index in analysis_artifacts when complete.
    """
    logger.info(f"[SEMANTIC_INDEX] Analysis {analysis_id}: Background semantic indexing started")
    db_session = None
    try:
        from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder

        # Fresh session (don't use stale worker session)
        db_session = SessionLocal()

        entities_from_db = db_session.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id
        ).all()

        if not entities_from_db:
            logger.info(f"[SEMANTIC_INDEX] Analysis {analysis_id}: No symbols, skipping")
            return

        logger.info(f"[SEMANTIC_INDEX] Analysis {analysis_id}: Found {len(entities_from_db)} symbols")

        entities_dict = {}
        for symbol in entities_from_db:
            entities_dict[symbol.id] = {
                'name': symbol.name,
                'type': symbol.symbol_type,
                'file_path': symbol.file.path if symbol.file else '',
                'qualified_name': symbol.qualified_name,
            }

        builder = SemanticIndexBuilder()
        chroma_bytes = builder.build_index_from_symbols(entities_dict)

        if chroma_bytes:
            try:
                artifact = AnalysisArtifact(
                    analysis_id=analysis_id,
                    type="semantic_index_db",
                    data={},
                    blob_data=chroma_bytes
                )
                db_session.add(artifact)
                db_session.commit()
                logger.info(f"[SEMANTIC_INDEX] Analysis {analysis_id}: Stored ({len(chroma_bytes)} bytes)")
            except Exception as db_err:
                logger.error(f"[SEMANTIC_INDEX] Analysis {analysis_id}: Failed to store: {db_err}")
                db_session.rollback()
        else:
            logger.error(f"[SEMANTIC_INDEX] Analysis {analysis_id}: Build returned None")
    except ImportError as ie:
        logger.error(f"[SEMANTIC_INDEX] Analysis {analysis_id}: chromadb unavailable: {ie}")
    except Exception as bg_err:
        logger.error(f"[SEMANTIC_INDEX] Analysis {analysis_id}: Error: {bg_err}", exc_info=True)
    finally:
        if db_session:
            try:
                db_session.close()
            except Exception:
                pass
