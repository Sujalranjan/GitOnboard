"""
BM25 artifact persistence for rebuilt indexes.

Handles safe, atomic replacement of BM25 artifacts when fresh indexes
are built to replace stale ones.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.models.repository import Analysis, AnalysisArtifact

logger = logging.getLogger(__name__)


def persist_rebuilt_bm25(
    db: Session,
    analysis_id: int,
    bm25_data: Dict[str, Any],
    current_fact_store_version: str,
) -> bool:
    """
    Persist a freshly-rebuilt BM25 artifact to replace stale one.

    Args:
        db: Database session
        analysis_id: Analysis ID
        bm25_data: Serialized BM25 index data (documents, idf, doc_len, etc.)
        current_fact_store_version: Current FactStore version UUID

    Returns:
        bool: True if persistence succeeded, False otherwise

    Behavior:
    - Finds existing BM25 artifact for analysis_id
    - If exists: updates data + fact_store_version (atomic within transaction)
    - If not exists: creates new artifact
    - Always sets fact_store_version to current
    - Returns True only if database commit succeeds
    """
    try:
        # Verify BM25 data contains required version field
        if "fact_store_version" not in bm25_data:
            logger.error(
                f"[BM25_PERSIST_INVALID] Cannot persist BM25 without fact_store_version "
                f"for analysis {analysis_id}"
            )
            return False

        # Verify version consistency before persistence
        if bm25_data["fact_store_version"] != current_fact_store_version:
            logger.error(
                f"[BM25_PERSIST_VERSION_MISMATCH] BM25 version {bm25_data['fact_store_version'][:8]}... "
                f"does not match current FactStore version {current_fact_store_version[:8]}... "
                f"for analysis {analysis_id}"
            )
            return False

        # Try to find existing BM25 artifact
        existing_artifact = db.query(AnalysisArtifact).filter(
            AnalysisArtifact.analysis_id == analysis_id,
            AnalysisArtifact.type == "bm25_index"
        ).first()

        if existing_artifact:
            # Update existing artifact with fresh data
            logger.info(
                f"[BM25_PERSIST_UPDATE] Updating existing BM25 artifact for analysis {analysis_id} "
                f"to version {current_fact_store_version[:8]}..."
            )
            existing_artifact.data = bm25_data
            db.flush()  # Ensure update is staged
        else:
            # Create new artifact
            logger.info(
                f"[BM25_PERSIST_CREATE] Creating new BM25 artifact for analysis {analysis_id} "
                f"version {current_fact_store_version[:8]}..."
            )
            new_artifact = AnalysisArtifact(
                analysis_id=analysis_id,
                type="bm25_index",
                data=bm25_data,
                blob_data=None
            )
            db.add(new_artifact)
            db.flush()

        # Commit the transaction (atomic)
        db.commit()

        logger.info(
            f"[BM25_PERSIST_SUCCESS] BM25 artifact persisted successfully for analysis {analysis_id} "
            f"version {current_fact_store_version[:8]}..."
        )
        return True

    except Exception as e:
        db.rollback()
        logger.error(
            f"[BM25_PERSIST_FAILED] Failed to persist BM25 artifact for analysis {analysis_id}: "
            f"{type(e).__name__}: {str(e)[:100]}"
        )
        return False


def get_bm25_artifact(
    db: Session,
    analysis_id: int,
) -> Optional[AnalysisArtifact]:
    """
    Retrieve BM25 artifact for an analysis.

    Returns:
        AnalysisArtifact if found, None otherwise
    """
    try:
        return db.query(AnalysisArtifact).filter(
            AnalysisArtifact.analysis_id == analysis_id,
            AnalysisArtifact.type == "bm25_index"
        ).first()
    except Exception as e:
        logger.debug(f"Failed to retrieve BM25 artifact for analysis {analysis_id}: {e}")
        return None
