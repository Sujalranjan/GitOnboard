"""
Phase 4-B: Indexing Status & Observability Tests

Test that indexing health is properly tracked and reported,
allowing the system to distinguish repository analysis completion
from retrieval index readiness.
"""

import pytest
from datetime import datetime, timezone
from backend.intelligence.retrieval.indexing_health import (
    IndexStatus, OverallIndexingStatus, IndexFailureCode,
    IndexingHealthReport, IndexHealthSnapshot, compute_overall_status,
)


def test_compute_overall_status():
    """Test status computation logic."""
    # All succeed
    assert compute_overall_status(True, True, True) == OverallIndexingStatus.SUCCESS

    # Semantic failed but core retrieval works
    assert compute_overall_status(True, True, False) == OverallIndexingStatus.PARTIAL

    # Core retrieval broken
    assert compute_overall_status(False, True, True) == OverallIndexingStatus.FAILED
    assert compute_overall_status(True, False, True) == OverallIndexingStatus.FAILED
    assert compute_overall_status(False, False, True) == OverallIndexingStatus.FAILED


def test_indexing_health_snapshot_serialization():
    """Test serialization/deserialization of health snapshots."""
    now = datetime.now(timezone.utc)
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.FAILED,
        document_count=100,
        error_code=IndexFailureCode.CHROMA_BUILD_FAILED,
        error_message="Test error",
        created_at=now,
    )

    # Serialize
    data = snapshot.to_dict()
    assert data["status"] == "FAILED"
    assert data["error_code"] == "CHROMA_BUILD_FAILED"
    assert data["document_count"] == 100

    # Deserialize
    loaded = IndexHealthSnapshot.from_dict(data)
    assert loaded.status == IndexStatus.FAILED
    assert loaded.error_code == IndexFailureCode.CHROMA_BUILD_FAILED
    assert loaded.error_message == "Test error"
    assert loaded.document_count == 100


def test_indexing_health_report_serialization():
    """Test serialization/deserialization of full health reports."""
    now = datetime.now(timezone.utc)
    report = IndexingHealthReport(
        overall_status=OverallIndexingStatus.PARTIAL,
        exact=IndexHealthSnapshot(status=IndexStatus.SUCCESS, document_count=612),
        bm25=IndexHealthSnapshot(status=IndexStatus.SUCCESS, document_count=612),
        semantic=IndexHealthSnapshot(
            status=IndexStatus.FAILED,
            error_code=IndexFailureCode.CHROMA_BUILD_FAILED,
            created_at=now,
        ),
    )

    # Serialize
    data = report.to_dict()
    assert data["overall_status"] == "PARTIAL"
    assert data["bm25"]["document_count"] == 612
    assert data["semantic"]["error_code"] == "CHROMA_BUILD_FAILED"

    # Deserialize
    loaded = IndexingHealthReport.from_dict(data)
    assert loaded.overall_status == OverallIndexingStatus.PARTIAL
    assert loaded.bm25.document_count == 612
    assert loaded.semantic.error_code == IndexFailureCode.CHROMA_BUILD_FAILED


def test_success_health_report():
    """Test 1: All indexes succeed → overall_status = SUCCESS."""
    health = IndexingHealthReport(
        overall_status=OverallIndexingStatus.SUCCESS,
        exact=IndexHealthSnapshot(
            status=IndexStatus.SUCCESS,
            document_count=612,
        ),
        bm25=IndexHealthSnapshot(
            status=IndexStatus.SUCCESS,
            document_count=612,
        ),
        semantic=IndexHealthSnapshot(
            status=IndexStatus.SUCCESS,
            document_count=612,
        ),
    )

    assert health.overall_status == OverallIndexingStatus.SUCCESS
    assert health.exact.status == IndexStatus.SUCCESS
    assert health.bm25.status == IndexStatus.SUCCESS
    assert health.semantic.status == IndexStatus.SUCCESS
    assert health.bm25.document_count == 612


def test_partial_health_chroma_unavailable():
    """Test 2: Chroma unavailable → overall_status = PARTIAL."""
    health = IndexingHealthReport(
        overall_status=OverallIndexingStatus.PARTIAL,
        exact=IndexHealthSnapshot(
            status=IndexStatus.SUCCESS,
            document_count=612,
        ),
        bm25=IndexHealthSnapshot(
            status=IndexStatus.SUCCESS,
            document_count=612,
        ),
        semantic=IndexHealthSnapshot(
            status=IndexStatus.UNAVAILABLE,
            document_count=0,
            error_code=IndexFailureCode.CHROMA_UNAVAILABLE,
            error_message="chromadb not installed",
        ),
    )

    assert health.overall_status == OverallIndexingStatus.PARTIAL
    assert health.semantic.status == IndexStatus.UNAVAILABLE
    assert health.semantic.error_code == IndexFailureCode.CHROMA_UNAVAILABLE


def test_failed_health_bm25():
    """Test 3: BM25 failure → overall_status = FAILED (core retrieval broken)."""
    health = IndexingHealthReport(
        overall_status=OverallIndexingStatus.FAILED,
        exact=IndexHealthSnapshot(
            status=IndexStatus.SUCCESS,
            document_count=612,
        ),
        bm25=IndexHealthSnapshot(
            status=IndexStatus.FAILED,
            document_count=0,
            error_code=IndexFailureCode.BM25_BUILD_FAILED,
            error_message="BM25 index creation returned None",
        ),
        semantic=IndexHealthSnapshot(
            status=IndexStatus.SUCCESS,
            document_count=612,
        ),
    )

    assert health.overall_status == OverallIndexingStatus.FAILED
    assert health.bm25.status == IndexStatus.FAILED
    assert health.bm25.error_code == IndexFailureCode.BM25_BUILD_FAILED


def test_failure_codes_are_machine_queryable():
    """Test that failure codes are structured enums, not free-form strings."""
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.FAILED,
        error_code=IndexFailureCode.CHROMA_BUILD_FAILED,
    )

    # Should be queryable programmatically
    assert snapshot.error_code == IndexFailureCode.CHROMA_BUILD_FAILED
    # Should have value
    assert snapshot.error_code.value == "CHROMA_BUILD_FAILED"

    # Verify it's an enum, not a string
    assert isinstance(snapshot.error_code, IndexFailureCode)


def test_all_failure_codes_defined():
    """Verify important failure codes are defined."""
    required_codes = [
        IndexFailureCode.BM25_BUILD_FAILED,
        IndexFailureCode.CHROMA_UNAVAILABLE,
        IndexFailureCode.CHROMA_BUILD_FAILED,
        IndexFailureCode.CHROMA_ARTIFACT_CORRUPT,
    ]

    for code in required_codes:
        assert isinstance(code, IndexFailureCode)
        assert code.value


def test_health_snapshot_empty_document_count():
    """Test that snapshot can have None document count."""
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.FAILED,
        document_count=None,
        error_code=IndexFailureCode.CHROMA_BUILD_FAILED,
    )

    assert snapshot.document_count is None
    data = snapshot.to_dict()
    assert data["document_count"] is None

    loaded = IndexHealthSnapshot.from_dict(data)
    assert loaded.document_count is None


def test_overall_status_values():
    """Test that overall status has expected values."""
    assert OverallIndexingStatus.PENDING.value == "PENDING"
    assert OverallIndexingStatus.SUCCESS.value == "SUCCESS"
    assert OverallIndexingStatus.PARTIAL.value == "PARTIAL"
    assert OverallIndexingStatus.FAILED.value == "FAILED"


def test_index_status_values():
    """Test that index status has expected values."""
    assert IndexStatus.SUCCESS.value == "SUCCESS"
    assert IndexStatus.FAILED.value == "FAILED"
    assert IndexStatus.UNAVAILABLE.value == "UNAVAILABLE"


def test_document_counts_preserved():
    """Test that document counts are preserved through serialization."""
    health = IndexingHealthReport(
        overall_status=OverallIndexingStatus.SUCCESS,
        exact=IndexHealthSnapshot(status=IndexStatus.SUCCESS, document_count=87),
        bm25=IndexHealthSnapshot(status=IndexStatus.SUCCESS, document_count=612),
        semantic=IndexHealthSnapshot(status=IndexStatus.SUCCESS, document_count=612),
    )

    # Serialize and deserialize
    data = health.to_dict()
    loaded = IndexingHealthReport.from_dict(data)

    # Verify counts preserved
    assert loaded.exact.document_count == 87
    assert loaded.bm25.document_count == 612
    assert loaded.semantic.document_count == 612
