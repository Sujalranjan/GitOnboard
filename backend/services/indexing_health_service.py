"""Service to query and report indexing health for analyses."""

import logging
from typing import Optional
from sqlalchemy.orm import Session
from backend.models.repository import Analysis
from backend.intelligence.retrieval.indexing_health import (
    IndexingHealthReport, IndexHealthSnapshot, IndexStatus
)

logger = logging.getLogger(__name__)


def get_indexing_health(db: Session, analysis_id: int) -> Optional[IndexingHealthReport]:
    """
    Get indexing health report for an analysis.

    Returns None if analysis not found or no health data.
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        return None

    if not analysis.indexing_details:
        return None

    try:
        return IndexingHealthReport.from_dict(analysis.indexing_details)
    except Exception as e:
        logger.error(f"Failed to parse indexing_details for analysis {analysis_id}: {e}")
        return None


def is_retrieval_healthy(db: Session, analysis_id: int) -> bool:
    """
    Check if retrieval is usable for an analysis.

    Returns True if at least BM25 and exact search are available.
    Semantic being unavailable is not considered a health failure.
    """
    health = get_indexing_health(db, analysis_id)
    if not health:
        return False

    # Retrieval is usable if exact and BM25 both succeeded
    return (
        health.exact.status == IndexStatus.SUCCESS and
        health.bm25.status == IndexStatus.SUCCESS
    )


def is_semantic_available(db: Session, analysis_id: int) -> bool:
    """Check if semantic retrieval is available for an analysis."""
    health = get_indexing_health(db, analysis_id)
    if not health:
        return False

    return health.semantic.status == IndexStatus.SUCCESS
