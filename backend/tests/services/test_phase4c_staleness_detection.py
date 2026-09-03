"""
Phase 4-C: BM25 Staleness Detection & Index Freshness Tests

Verify that BM25 stale indexes are detected and handled correctly
without automatic rebuilds (detection only, not automation).
"""

import pytest
from backend.intelligence.retrieval.indexing_health import (
    IndexStatus, IndexHealthSnapshot, FreshnessStatus
)


def test_freshness_status_enum():
    """Test that FreshnessStatus enum exists with correct values."""
    assert FreshnessStatus.FRESH.value == "FRESH"
    assert FreshnessStatus.STALE.value == "STALE"
    assert FreshnessStatus.UNKNOWN.value == "UNKNOWN"


def test_index_status_includes_stale():
    """Test that IndexStatus includes STALE state."""
    assert hasattr(IndexStatus, "STALE")
    assert IndexStatus.STALE.value == "STALE"


def test_health_snapshot_with_freshness():
    """Test that IndexHealthSnapshot can track freshness."""
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.FRESH,
    )

    assert snapshot.status == IndexStatus.SUCCESS
    assert snapshot.freshness == FreshnessStatus.FRESH
    assert snapshot.document_count == 612


def test_health_snapshot_stale_freshness():
    """Test that snapshot can report stale freshness."""
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.STALE,
    )

    assert snapshot.freshness == FreshnessStatus.STALE


def test_health_snapshot_unknown_freshness():
    """Test that snapshot can report unknown freshness."""
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.UNKNOWN,  # Old artifact without version info
    )

    assert snapshot.freshness == FreshnessStatus.UNKNOWN


def test_freshness_serialization():
    """Test that freshness status serializes and deserializes correctly."""
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.STALE,
    )

    # Serialize
    data = snapshot.to_dict()
    assert data["freshness"] == "STALE"

    # Deserialize
    loaded = IndexHealthSnapshot.from_dict(data)
    assert loaded.freshness == FreshnessStatus.STALE


def test_freshness_none_serialization():
    """Test that None freshness serializes correctly."""
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=None,  # No freshness tracking
    )

    # Serialize
    data = snapshot.to_dict()
    assert data["freshness"] is None

    # Deserialize
    loaded = IndexHealthSnapshot.from_dict(data)
    assert loaded.freshness is None


def test_bm25_freshness_tracking():
    """
    Test 1: BM25 freshness can be tracked.

    This is the fundamental capability for staleness detection.
    """
    # Fresh BM25
    fresh = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.FRESH,
    )
    assert fresh.freshness == FreshnessStatus.FRESH

    # Stale BM25
    stale = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.STALE,
    )
    assert stale.freshness == FreshnessStatus.STALE

    # These should be distinguishable
    assert fresh.freshness != stale.freshness


def test_bm25_successful_with_fresh_freshness():
    """
    Test 2: Successful BM25 with FRESH status.

    A successful BM25 that corresponds to current FactStore.
    """
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.FRESH,
    )

    assert snapshot.status == IndexStatus.SUCCESS
    assert snapshot.freshness == FreshnessStatus.FRESH
    # This BM25 can be used for retrieval


def test_bm25_successful_with_stale_freshness():
    """
    Test 3: Successful BM25 with STALE status.

    A successfully-built BM25 that doesn't match current FactStore.
    This should not be used without rebuilding.
    """
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.STALE,
    )

    assert snapshot.status == IndexStatus.SUCCESS
    assert snapshot.freshness == FreshnessStatus.STALE
    # This BM25 should NOT be used (requires rebuild)


def test_old_artifact_unknown_freshness():
    """
    Test 4: Old artifacts without version info have UNKNOWN freshness.

    Backward compatibility: artifacts from before Phase 4-C
    don't have fact_store_version, so freshness is unknown.
    """
    snapshot = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.UNKNOWN,  # No version info available
    )

    assert snapshot.freshness == FreshnessStatus.UNKNOWN


def test_multiple_snapshots_different_freshness():
    """Test that multiple snapshots can have different freshness states."""
    exact = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.FRESH,  # Exact is immutable
    )

    bm25 = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.STALE,  # BM25 became stale
    )

    semantic = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        freshness=FreshnessStatus.FRESH,  # Semantic is fresh
    )

    # All three can have different freshness states
    assert exact.freshness == FreshnessStatus.FRESH
    assert bm25.freshness == FreshnessStatus.STALE
    assert semantic.freshness == FreshnessStatus.FRESH


def test_index_status_stale_vs_failed():
    """Test distinction between STALE and FAILED."""
    stale = IndexHealthSnapshot(
        status=IndexStatus.STALE,  # Built successfully, but stale
        document_count=612,
        freshness=FreshnessStatus.STALE,
    )

    failed = IndexHealthSnapshot(
        status=IndexStatus.FAILED,  # Failed to build
        document_count=0,
        freshness=None,
    )

    # STALE: existed, was valid, no longer matches FactStore
    assert stale.status == IndexStatus.STALE
    assert stale.document_count == 612  # Had documents

    # FAILED: never succeeded
    assert failed.status == IndexStatus.FAILED
    assert failed.document_count == 0


def test_freshness_complete_round_trip():
    """Test complete serialization round-trip for freshness data."""
    original = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        document_count=612,
        error_code=None,
        error_message=None,
        freshness=FreshnessStatus.STALE,
    )

    # Serialize
    data = original.to_dict()

    # Verify data structure
    assert "freshness" in data
    assert data["freshness"] == "STALE"
    assert data["status"] == "SUCCESS"
    assert data["document_count"] == 612

    # Deserialize
    restored = IndexHealthSnapshot.from_dict(data)

    # Verify restoration
    assert restored.status == original.status
    assert restored.document_count == original.document_count
    assert restored.freshness == original.freshness


def test_freshness_independent_of_status():
    """Test that freshness is independent of status."""
    # SUCCESS + FRESH
    case1 = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        freshness=FreshnessStatus.FRESH,
    )
    assert case1.status == IndexStatus.SUCCESS
    assert case1.freshness == FreshnessStatus.FRESH

    # SUCCESS + STALE
    case2 = IndexHealthSnapshot(
        status=IndexStatus.SUCCESS,
        freshness=FreshnessStatus.STALE,
    )
    assert case2.status == IndexStatus.SUCCESS
    assert case2.freshness == FreshnessStatus.STALE

    # FAILED + UNKNOWN (no freshness possible)
    case3 = IndexHealthSnapshot(
        status=IndexStatus.FAILED,
        freshness=FreshnessStatus.UNKNOWN,
    )
    assert case3.status == IndexStatus.FAILED
    assert case3.freshness == FreshnessStatus.UNKNOWN

    # All are valid combinations
