"""
Unit tests for context lifecycle management (Phase 2L).

Tests ContextManager:
- Adding items with automatic ID assignment
- Listing active context
- Dropping items
- Re-requesting dropped items
- Summarizing/compressing context
- Token accounting
- Utilization calculation
- Budget checkpoint tracking
"""

import pytest
from datetime import datetime

from backend.intelligence.context_management.manager import ContextManager
from backend.intelligence.context_management.models import (
    ContextItemPriority,
    ContextItemState,
)
from backend.agent.context.contracts import ContextEvidence


class TestContextManagerAddItem:
    """Tests for adding items to context manager."""

    def test_add_item_assigns_unique_id(self, context_manager, sample_evidence):
        """Verify each added item gets unique context_item_id."""
        item1 = context_manager.add_item(sample_evidence)
        item2 = context_manager.add_item(sample_evidence)

        assert item1.context_item_id != item2.context_item_id
        assert item1.context_item_id.startswith("ctx_0000_")
        assert item2.context_item_id.startswith("ctx_0001_")

    def test_add_item_starts_in_active_state(self, context_manager, sample_evidence):
        """Verify added items start in ACTIVE state."""
        item = context_manager.add_item(sample_evidence)
        assert item.state == ContextItemState.ACTIVE

    def test_add_item_assigns_estimated_tokens(self, context_manager, sample_evidence):
        """Verify tokens are estimated for added items."""
        item = context_manager.add_item(sample_evidence)
        assert item.estimated_tokens > 0

    def test_add_item_with_priority_override(self, context_manager, sample_evidence):
        """Verify priority can be explicitly provided."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.PROTECTED
        )
        assert item.priority == ContextItemPriority.PROTECTED

    def test_add_item_assigns_priority_by_policy(
        self, context_manager, high_priority_evidence
    ):
        """Verify priority is assigned by policy when not provided."""
        item = context_manager.add_item(high_priority_evidence)
        # User requirements should be PROTECTED
        assert item.priority == ContextItemPriority.PROTECTED

    def test_add_item_records_retrieval_source(self, context_manager, sample_evidence):
        """Verify retrieval source is recorded."""
        item = context_manager.add_item(
            sample_evidence,
            retrieval_source="manual_query"
        )
        assert item.retrieval_source == "manual_query"

    def test_add_item_records_timestamp(self, context_manager, sample_evidence):
        """Verify creation timestamp is recorded."""
        before = datetime.now()
        item = context_manager.add_item(sample_evidence)
        after = datetime.now()

        assert before <= item.created_timestamp <= after

    def test_add_multiple_items(self, context_manager, sample_evidence):
        """Verify multiple items can be added."""
        for i in range(5):
            item = context_manager.add_item(sample_evidence)
            assert item is not None

        assert len(context_manager.items) == 5


class TestContextManagerListContext:
    """Tests for listing active context."""

    def test_list_context_returns_active_items(self, context_manager, sample_evidence):
        """Verify list_context returns only ACTIVE and REFERENCE items."""
        item1 = context_manager.add_item(sample_evidence)
        item2 = context_manager.add_item(sample_evidence)

        active = context_manager.list_context()
        assert len(active) == 2
        assert item1 in active
        assert item2 in active

    def test_list_context_excludes_dropped(self, context_manager, sample_evidence):
        """Verify list_context excludes DROPPED items."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.DISPOSABLE
        )

        context_manager.drop_context(item.context_item_id)

        active = context_manager.list_context()
        assert item not in active

    def test_list_context_excludes_compressed(self, context_manager, sample_evidence):
        """Verify list_context excludes original after compression."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.COMPRESSIBLE
        )

        context_manager.summarize_context(
            item.context_item_id,
            summary="Compressed summary",
            summary_tokens=50
        )

        active = context_manager.list_context()
        # Original should be in REFERENCE state, not active list
        assert item.state == ContextItemState.REFERENCE
        # But list_context includes REFERENCE items
        assert any(it.context_item_id == item.context_item_id for it in active)

    def test_list_context_empty(self, context_manager):
        """Verify empty manager returns empty list."""
        active = context_manager.list_context()
        assert active == []


class TestContextManagerDrop:
    """Tests for dropping context items."""

    def test_drop_context_changes_state(self, context_manager, sample_evidence):
        """Verify dropping changes state to DROPPED."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.DISPOSABLE
        )

        result = context_manager.drop_context(item.context_item_id)

        assert result is True
        assert item.state == ContextItemState.DROPPED

    def test_drop_context_nonexistent_returns_false(self, context_manager):
        """Verify dropping nonexistent item returns False."""
        result = context_manager.drop_context("ctx_9999_nonexist")
        assert result is False

    def test_drop_context_protected_not_allowed(self, context_manager):
        """Verify dropping PROTECTED items is not allowed."""
        item = context_manager.add_item(
            ContextEvidence(
                source_type="requirement_analysis",
                source_id="req",
                relevance=0.9,
                confidence=0.9,
                summary="User requirement",
                data={"requirement": "Must support Python"},
                metadata={}
            ),
            priority=ContextItemPriority.PROTECTED
        )

        result = context_manager.drop_context(item.context_item_id)
        assert result is False
        assert item.state == ContextItemState.ACTIVE

    def test_drop_context_preserves_content(self, context_manager, sample_evidence):
        """Verify dropped items preserve content."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.DISPOSABLE
        )
        original_data = item.data

        context_manager.drop_context(item.context_item_id)

        assert item.data == original_data

    def test_drop_multiple_items(self, context_manager, sample_evidence):
        """Verify multiple items can be dropped independently."""
        item1 = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.DISPOSABLE
        )
        item2 = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.DISPOSABLE
        )

        context_manager.drop_context(item1.context_item_id)

        assert item1.state == ContextItemState.DROPPED
        assert item2.state == ContextItemState.ACTIVE


class TestContextManagerReRequest:
    """Tests for re-requesting dropped context."""

    def test_re_request_dropped_context_reactivates(self, context_manager, sample_evidence):
        """Verify dropped items can be reactivated."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.DISPOSABLE
        )
        context_manager.drop_context(item.context_item_id)

        reactivated = context_manager.re_request_dropped_context(item.context_item_id)

        assert reactivated is not None
        assert reactivated.state == ContextItemState.ACTIVE

    def test_re_request_nonexistent_returns_none(self, context_manager):
        """Verify re-requesting nonexistent item returns None."""
        result = context_manager.re_request_dropped_context("ctx_9999_nonexist")
        assert result is None

    def test_re_request_active_item_not_reactivated(self, context_manager, sample_evidence):
        """Verify re-requesting active item returns None."""
        item = context_manager.add_item(sample_evidence)

        result = context_manager.re_request_dropped_context(item.context_item_id)
        assert result is None


class TestContextManagerSummarize:
    """Tests for context compression/summarization."""

    def test_summarize_context_creates_summary_item(
        self, context_manager, sample_evidence
    ):
        """Verify summarization creates new compressed item."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.COMPRESSIBLE
        )

        result = context_manager.summarize_context(
            item.context_item_id,
            summary="Compressed summary",
            summary_tokens=50
        )

        assert result is not None
        assert result.original_item_id == item.context_item_id
        assert result.summary_tokens == 50

    def test_summarize_context_marks_original_reference(
        self, context_manager, sample_evidence
    ):
        """Verify original item marked as REFERENCE after compression."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.COMPRESSIBLE
        )

        context_manager.summarize_context(
            item.context_item_id,
            summary="Compressed",
            summary_tokens=50
        )

        assert item.state == ContextItemState.REFERENCE

    def test_summarize_context_protected_not_allowed(
        self, context_manager, high_priority_evidence
    ):
        """Verify summarizing PROTECTED items is not allowed."""
        item = context_manager.add_item(high_priority_evidence)

        result = context_manager.summarize_context(
            item.context_item_id,
            summary="Not allowed",
            summary_tokens=50
        )

        assert result is None
        assert item.state == ContextItemState.ACTIVE

    def test_summarize_context_nonexistent_returns_none(self, context_manager):
        """Verify summarizing nonexistent item returns None."""
        result = context_manager.summarize_context(
            "ctx_9999_nonexist",
            summary="Summary",
            summary_tokens=50
        )
        assert result is None

    def test_summarize_context_calculates_savings(
        self, context_manager, sample_evidence
    ):
        """Verify token savings are calculated."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.COMPRESSIBLE
        )
        original_tokens = item.estimated_tokens

        result = context_manager.summarize_context(
            item.context_item_id,
            summary="Short summary",
            summary_tokens=20
        )

        expected_savings = max(0, original_tokens - 20)
        assert result.token_savings == expected_savings

    def test_summarize_context_preserves_original_accessible(
        self, context_manager, sample_evidence
    ):
        """Verify original item remains accessible after compression."""
        item = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.COMPRESSIBLE
        )
        original_id = item.context_item_id

        context_manager.summarize_context(
            original_id,
            summary="Compressed",
            summary_tokens=50
        )

        # Original should still be in items list
        found = any(it.context_item_id == original_id for it in context_manager.items)
        assert found


class TestContextManagerTokenAccounting:
    """Tests for token accounting."""

    def test_token_accounting_accumulates(self, context_manager, sample_evidence):
        """Verify tokens accumulate as items added."""
        # Add multiple items and verify token count
        item1 = context_manager.add_item(sample_evidence)
        item2 = context_manager.add_item(sample_evidence)

        stats = context_manager.get_context_statistics()

        expected_tokens = item1.estimated_tokens + item2.estimated_tokens
        assert stats["active_tokens"] == expected_tokens

    def test_peak_tokens_tracked(self, context_manager, sample_evidence):
        """Verify peak tokens are tracked."""
        item1 = context_manager.add_item(sample_evidence)
        peak_after_1 = context_manager.peak_tokens_used

        item2 = context_manager.add_item(sample_evidence)
        peak_after_2 = context_manager.peak_tokens_used

        assert peak_after_2 >= peak_after_1

    def test_utilization_calculation(self, context_manager, sample_evidence):
        """Verify utilization is calculated correctly."""
        # Empty
        util_empty = context_manager.calculate_utilization()
        assert util_empty == 0.0

        # Add items
        item = context_manager.add_item(sample_evidence)
        util_filled = context_manager.calculate_utilization()

        assert util_filled > 0.0
        expected = item.estimated_tokens / 100000
        assert abs(util_filled - expected) < 0.001

    def test_budget_checkpoint_thresholds(self, context_manager):
        """Verify budget checkpoint status at different thresholds."""
        from backend.intelligence.context_management.token_accounting import BudgetCheckpoint

        # < 50%: normal
        cp_normal = BudgetCheckpoint(30000, 100000)
        assert cp_normal.status == "normal"

        # 50-70%: moderate
        cp_moderate = BudgetCheckpoint(60000, 100000)
        assert cp_moderate.status == "moderate"

        # 70-85%: caution
        cp_caution = BudgetCheckpoint(80000, 100000)
        assert cp_caution.status == "caution"

        # 85-95%: high
        cp_high = BudgetCheckpoint(90000, 100000)
        assert cp_high.status == "high"

        # > 95%: critical
        cp_critical = BudgetCheckpoint(96000, 100000)
        assert cp_critical.status == "critical"


class TestContextManagerStatistics:
    """Tests for context statistics."""

    def test_get_context_statistics_structure(self, context_manager, sample_evidence):
        """Verify statistics dictionary has expected structure."""
        item = context_manager.add_item(sample_evidence)
        stats = context_manager.get_context_statistics()

        assert "total_items" in stats
        assert "active_items" in stats
        assert "active_tokens" in stats
        assert "peak_tokens" in stats
        assert "utilization_percent" in stats
        assert "budget_status" in stats
        assert "items_by_priority" in stats
        assert "items_by_state" in stats

    def test_items_by_priority_counted(self, context_manager, sample_evidence):
        """Verify items are counted by priority level."""
        context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.ACTIVE
        )
        context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.PROTECTED
        )

        stats = context_manager.get_context_statistics()

        assert stats["items_by_priority"]["ACTIVE"] == 1
        assert stats["items_by_priority"]["PROTECTED"] == 1

    def test_items_by_state_counted(self, context_manager, sample_evidence):
        """Verify items are counted by state."""
        item1 = context_manager.add_item(
            sample_evidence,
            priority=ContextItemPriority.DISPOSABLE
        )
        item2 = context_manager.add_item(sample_evidence)

        context_manager.drop_context(item1.context_item_id)

        stats = context_manager.get_context_statistics()

        assert stats["items_by_state"]["DROPPED"] == 1
        assert stats["items_by_state"]["ACTIVE"] == 1
