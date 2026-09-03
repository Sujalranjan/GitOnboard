"""
Indexing health tracking and status management.

Tracks the status of each retrieval index (exact/BM25/semantic) and
provides structured failure classification for observability.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Literal
from enum import Enum
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class IndexStatus(str, Enum):
    """Status of an individual index."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"  # E.g., optional dependency not installed
    STALE = "STALE"  # Index exists but doesn't match current FactStore


class FreshnessStatus(str, Enum):
    """Freshness status of an index relative to FactStore."""
    FRESH = "FRESH"  # Index corresponds to current FactStore
    STALE = "STALE"  # Index doesn't correspond to current FactStore
    UNKNOWN = "UNKNOWN"  # Cannot determine freshness


class OverallIndexingStatus(str, Enum):
    """Overall indexing status for an analysis."""
    PENDING = "PENDING"  # Indexing not yet attempted
    SUCCESS = "SUCCESS"  # All indexes succeeded
    PARTIAL = "PARTIAL"  # Some indexes succeeded, some failed
    FAILED = "FAILED"  # Core indexes failed, retrieval unusable


class IndexFailureCode(str, Enum):
    """Structured failure classification."""
    # BM25 failures
    BM25_BUILD_FAILED = "BM25_BUILD_FAILED"
    BM25_ARTIFACT_MISSING = "BM25_ARTIFACT_MISSING"
    BM25_ARTIFACT_CORRUPT = "BM25_ARTIFACT_CORRUPT"
    BM25_EMPTY_FACTSTORE = "BM25_EMPTY_FACTSTORE"

    # Semantic/Chroma failures
    CHROMA_UNAVAILABLE = "CHROMA_UNAVAILABLE"  # chromadb import failed
    CHROMA_BUILD_FAILED = "CHROMA_BUILD_FAILED"
    CHROMA_ARTIFACT_MISSING = "CHROMA_ARTIFACT_MISSING"
    CHROMA_ARTIFACT_CORRUPT = "CHROMA_ARTIFACT_CORRUPT"
    CHROMA_LOAD_FAILED = "CHROMA_LOAD_FAILED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    CHROMA_ENTITY_SKIP = "CHROMA_ENTITY_SKIP"  # No entities to embed

    # General failures
    UNKNOWN = "UNKNOWN"


@dataclass
class IndexHealthSnapshot:
    """Health status of a single index."""
    status: IndexStatus
    document_count: Optional[int] = None
    error_code: Optional[IndexFailureCode] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    freshness: Optional[FreshnessStatus] = None  # For indexes with staleness detection

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "status": self.status.value,
            "document_count": self.document_count,
            "error_code": self.error_code.value if self.error_code else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "freshness": self.freshness.value if self.freshness else None,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "IndexHealthSnapshot":
        """Load from dict."""
        return IndexHealthSnapshot(
            status=IndexStatus(data.get("status", "FAILED")),
            document_count=data.get("document_count"),
            error_code=IndexFailureCode(data.get("error_code")) if data.get("error_code") else None,
            error_message=data.get("error_message"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            freshness=FreshnessStatus(data.get("freshness")) if data.get("freshness") else None,
        )


@dataclass
class IndexingHealthReport:
    """Complete indexing health status for an analysis."""
    overall_status: OverallIndexingStatus
    exact: IndexHealthSnapshot
    bm25: IndexHealthSnapshot
    semantic: IndexHealthSnapshot

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "overall_status": self.overall_status.value,
            "exact": self.exact.to_dict(),
            "bm25": self.bm25.to_dict(),
            "semantic": self.semantic.to_dict(),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "IndexingHealthReport":
        """Load from dict."""
        return IndexingHealthReport(
            overall_status=OverallIndexingStatus(data.get("overall_status", "PENDING")),
            exact=IndexHealthSnapshot.from_dict(data.get("exact", {})),
            bm25=IndexHealthSnapshot.from_dict(data.get("bm25", {})),
            semantic=IndexHealthSnapshot.from_dict(data.get("semantic", {})),
        )


def compute_overall_status(
    exact_ok: bool,
    bm25_ok: bool,
    semantic_ok: bool,
) -> OverallIndexingStatus:
    """
    Compute overall indexing status based on individual index results.

    - SUCCESS: all indexes succeeded
    - PARTIAL: exact + BM25 succeeded, but semantic unavailable/failed
    - FAILED: exact or BM25 failed (core retrieval broken)
    """
    if not exact_ok and not bm25_ok:
        return OverallIndexingStatus.FAILED
    if exact_ok and bm25_ok:
        if semantic_ok:
            return OverallIndexingStatus.SUCCESS
        else:
            return OverallIndexingStatus.PARTIAL
    return OverallIndexingStatus.FAILED


def record_indexing_failure(
    analysis_id: int,
    index_type: str,
    error_code: IndexFailureCode,
    error_message: str,
) -> None:
    """Log indexing failure with structured classification."""
    logger.error(
        f"[INDEX_BUILD_FAILED] analysis_id={analysis_id} index={index_type} "
        f"reason={error_code.value} message={error_message[:100]}"
    )
