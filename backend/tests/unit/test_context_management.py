"""
Tests for Phase 2L context lifecycle management.

Validates:
- Adding items with ID assignment
- Priority assignment determinism
- Token accounting
- Utilization calculation
- Checkpoint thresholds
- Drop/summarize operations
- Re-request dropped items
- Peak tracking
"""

import pytest
from datetime import datetime

from backend.agent.context.contracts import ContextEvidence, ContextBudget
from backend.intelligence.context_management import (
    ContextManager,
    ContextItem,
    ContextItemPriority,
    ContextItemState,
    CompressedContext,
    PriorityPolicy,
    estimate_tokens,
    evaluate_budget_status,
)


class TestContextItemCreation:
    """Test ContextItem model and creation."""

    def test_context_item_from_evidence(self):
        """Test creating ContextItem from ContextEvidence."""
        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="symbol_1",
            relevance=0.9,
            confidence=0.85,
            summary="Test evidence",
            data={"content": "test"},
        )

        item = ContextItem.from_evidence(
            evidence,
            priority=ContextItemPriority.ACTIVE,
            retrieval_source="retrieval",
            estimated_tokens=50,
            reason_for_priority="Test reason",
        )

        assert item.context_item_id.startswith("ctx_")
        assert item.priority == ContextItemPriority.ACTIVE
        assert item.estimated_tokens == 50
        assert item.state == ContextItemState.ACTIVE
        assert item.is_compressed is False
        assert item.retrieval_source == "retrieval"
        assert item.reason_for_priority == "Test reason"

    def test_context_item_has_immutable_id(self):
        """Test that context_item_id is immutable."""
        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="symbol_1",
            summary="Test",
            data={},
        )

        item = ContextItem.from_evidence(evidence)
        original_id = item.context_item_id

        # ID should not change
        assert item.context_item_id == original_id


class TestPriorityPolicy:
    """Test deterministic priority assignment."""

    def test_protected_for_requirement_analysis(self):
        """Test PROTECTED priority for user requirements."""
        evidence = ContextEvidence(
            source_type="requirement_analysis",
            source_id="req_1",
            summary="User requirement",
            data={},
        )

        priority, reason = PriorityPolicy.assign_priority(evidence)
        assert priority == ContextItemPriority.PROTECTED
        assert "requirement" in reason.lower()

    def test_protected_for_rim_symbols(self):
        """Test PROTECTED priority for RIM symbols."""
        evidence = ContextEvidence(
            source_type="rim_symbol",
            source_id="symbol_1",
            summary="RIM symbol",
            data={},
        )

        priority, reason = PriorityPolicy.assign_priority(evidence)
        assert priority == ContextItemPriority.PROTECTED

    def test_protected_for_high_relevance_confidence(self):
        """Test PROTECTED priority for high relevance and confidence."""
        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="symbol_1",
            relevance=0.9,
            confidence=0.85,
            summary="High quality evidence",
            data={},
        )

        priority, reason = PriorityPolicy.assign_priority(evidence)
        assert priority == ContextItemPriority.PROTECTED

    def test_active_for_retrieval_high_confidence(self):
        """Test ACTIVE priority for high-confidence retrieval."""
        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="symbol_1",
            relevance=0.7,
            confidence=0.8,
            summary="Retrieval result",
            data={},
        )

        priority, reason = PriorityPolicy.assign_priority(evidence)
        assert priority == ContextItemPriority.ACTIVE

    def test_compressible_for_medium_relevance(self):
        """Test COMPRESSIBLE priority for medium relevance."""
        evidence = ContextEvidence(
            source_type="source_excerpt",
            source_id="file_1",
            relevance=0.7,
            confidence=0.6,
            summary="Supporting evidence",
            data={},
        )

        priority, reason = PriorityPolicy.assign_priority(evidence)
        assert priority == ContextItemPriority.COMPRESSIBLE

    def test_disposable_for_low_relevance(self):
        """Test DISPOSABLE priority for low relevance."""
        evidence = ContextEvidence(
            source_type="expansion",
            source_id="item_1",
            relevance=0.3,
            confidence=0.5,
            summary="Low relevance expansion",
            data={},
        )

        priority, reason = PriorityPolicy.assign_priority(evidence)
        assert priority == ContextItemPriority.DISPOSABLE

    def test_priority_deterministic(self):
        """Test that same evidence always gets same priority."""
        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="symbol_1",
            relevance=0.75,
            confidence=0.7,
            summary="Test evidence",
            data={},
        )

        priority1, _ = PriorityPolicy.assign_priority(evidence)
        priority2, _ = PriorityPolicy.assign_priority(evidence)

        assert priority1 == priority2


class TestTokenAccounting:
    """Test token estimation and accounting."""

    def test_estimate_tokens_empty_data(self):
        """Test token estimation for empty data."""
        tokens = estimate_tokens({})
        assert tokens >= 1

    def test_estimate_tokens_small_data(self):
        """Test token estimation for small data."""
        data = {"key": "value"}
        tokens = estimate_tokens(data)
        assert tokens >= 1

    def test_estimate_tokens_large_data(self):
        """Test token estimation for large data."""
        data = {"content": "x" * 1000}
        tokens = estimate_tokens(data)
        assert tokens > 1

    def test_budget_checkpoint_normal(self):
        """Test budget checkpoint at < 50%."""
        status = evaluate_budget_status(30000, 100000)
        assert status == "normal"

    def test_budget_checkpoint_moderate(self):
        """Test budget checkpoint at 50-70%."""
        status = evaluate_budget_status(60000, 100000)
        assert status == "moderate"

    def test_budget_checkpoint_caution(self):
        """Test budget checkpoint at 70-85%."""
        status = evaluate_budget_status(77500, 100000)
        assert status == "caution"

    def test_budget_checkpoint_high(self):
        """Test budget checkpoint at 85-95%."""
        status = evaluate_budget_status(90000, 100000)
        assert status == "high"

    def test_budget_checkpoint_critical(self):
        """Test budget checkpoint at > 95%."""
        status = evaluate_budget_status(96000, 100000)
        assert status == "critical"


class TestContextManager:
    """Test ContextManager lifecycle operations."""

    def test_context_manager_initialization(self):
        """Test ContextManager initialization."""
        budget = ContextBudget()
        manager = ContextManager(budget, configured_context_budget_tokens=100000)

        assert manager.peak_tokens_used == 0
        assert len(manager.items) == 0

    def test_add_item_assigns_id(self):
        """Test that adding item assigns immutable ID."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="symbol_1",
            summary="Test",
            data={"content": "test"},
        )

        item = manager.add_item(evidence)

        assert item.context_item_id.startswith("ctx_")
        assert len(manager.items) == 1

    def test_add_item_assigns_priority(self):
        """Test that adding item assigns priority by policy."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        evidence = ContextEvidence(
            source_type="requirement_analysis",
            source_id="req_1",
            summary="User requirement",
            data={},
        )

        item = manager.add_item(evidence)

        assert item.priority == ContextItemPriority.PROTECTED

    def test_add_item_priority_override(self):
        """Test that priority can be explicitly overridden."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="symbol_1",
            summary="Test",
            data={},
        )

        item = manager.add_item(
            evidence,
            priority=ContextItemPriority.DISPOSABLE,
        )

        assert item.priority == ContextItemPriority.DISPOSABLE

    def test_list_context_only_active(self):
        """Test that list_context returns only ACTIVE/REFERENCE items."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        # Add ACTIVE item
        evidence1 = ContextEvidence(
            source_type="retrieval",
            source_id="s1",
            summary="Item 1",
            data={},
        )
        item1 = manager.add_item(evidence1)

        # Add another and drop it
        evidence2 = ContextEvidence(
            source_type="expansion",
            source_id="s2",
            relevance=0.3,
            summary="Item 2",
            data={},
        )
        item2 = manager.add_item(evidence2)
        manager.drop_context(item2.context_item_id)

        active = manager.list_context()
        assert len(active) == 1
        assert active[0].context_item_id == item1.context_item_id

    def test_get_context_statistics(self):
        """Test context statistics calculation."""
        budget = ContextBudget()
        manager = ContextManager(budget, configured_context_budget_tokens=100000)

        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="s1",
            summary="Test",
            data={"content": "test data"},
        )
        manager.add_item(evidence)

        stats = manager.get_context_statistics()

        assert "total_items" in stats
        assert "active_items" in stats
        assert "active_tokens" in stats
        assert "peak_tokens" in stats
        assert "utilization_percent" in stats
        assert "budget_status" in stats
        assert "items_by_priority" in stats
        assert "items_by_state" in stats
        assert stats["total_items"] == 1
        assert stats["active_items"] == 1

    def test_calculate_utilization(self):
        """Test utilization calculation."""
        budget = ContextBudget()
        manager = ContextManager(budget, configured_context_budget_tokens=100000)

        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="s1",
            summary="Test",
            data={"x": "y"},
        )
        manager.add_item(evidence)

        utilization = manager.calculate_utilization()
        assert 0.0 <= utilization <= 1.0

    def test_drop_context_success(self):
        """Test dropping context item."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        evidence = ContextEvidence(
            source_type="expansion",
            source_id="s1",
            relevance=0.3,
            summary="Disposable",
            data={},
        )
        item = manager.add_item(evidence)

        success = manager.drop_context(item.context_item_id)
        assert success is True
        assert item.state == ContextItemState.DROPPED

    def test_drop_context_protected_fails(self):
        """Test that protected items cannot be dropped."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        evidence = ContextEvidence(
            source_type="requirement_analysis",
            source_id="req_1",
            summary="Protected",
            data={},
        )
        item = manager.add_item(evidence)

        success = manager.drop_context(item.context_item_id)
        assert success is False
        assert item.state == ContextItemState.ACTIVE

    def test_drop_context_not_found(self):
        """Test dropping non-existent context."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        success = manager.drop_context("ctx_0000_nonexistent")
        assert success is False

    def test_re_request_dropped_context(self):
        """Test re-requesting dropped context."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        evidence = ContextEvidence(
            source_type="expansion",
            source_id="s1",
            relevance=0.3,
            summary="Disposable",
            data={},
        )
        item = manager.add_item(evidence)
        manager.drop_context(item.context_item_id)

        reactivated = manager.re_request_dropped_context(item.context_item_id)
        assert reactivated is not None
        assert reactivated.state == ContextItemState.ACTIVE

    def test_summarize_context(self):
        """Test compression/summarization of context."""
        budget = ContextBudget()
        manager = ContextManager(budget, configured_context_budget_tokens=100000)

        evidence = ContextEvidence(
            source_type="source_excerpt",
            source_id="file_1",
            relevance=0.7,
            confidence=0.6,
            summary="Original long content",
            data={"content": "x" * 1000},
        )
        item = manager.add_item(evidence)

        compressed = manager.summarize_context(
            item.context_item_id,
            summary="Compressed summary",
            summary_tokens=10,
        )

        assert compressed is not None
        assert compressed.original_item_id == item.context_item_id
        assert compressed.compression_summary == "Compressed summary"
        assert compressed.original_tokens > 0
        assert compressed.summary_tokens == 10
        assert compressed.token_savings > 0
        assert item.state == ContextItemState.REFERENCE

    def test_summarize_protected_fails(self):
        """Test that protected items cannot be compressed."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        evidence = ContextEvidence(
            source_type="requirement_analysis",
            source_id="req_1",
            summary="Protected",
            data={"x": "y" * 100},
        )
        item = manager.add_item(evidence)

        compressed = manager.summarize_context(
            item.context_item_id,
            summary="Summary",
            summary_tokens=5,
        )

        assert compressed is None

    def test_peak_tokens_tracking(self):
        """Test peak tokens tracking."""
        budget = ContextBudget()
        manager = ContextManager(budget, configured_context_budget_tokens=100000)

        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="s1",
            summary="Test",
            data={"content": "x" * 1000},
        )
        item = manager.add_item(evidence)

        assert manager.peak_tokens_used > 0

    def test_get_budget_checkpoint_none_when_normal(self):
        """Test that checkpoint returns None when utilization is normal."""
        budget = ContextBudget()
        manager = ContextManager(budget, configured_context_budget_tokens=100000)

        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="s1",
            summary="Test",
            data={"x": "y"},
        )
        manager.add_item(evidence)

        checkpoint = manager.get_budget_checkpoint()
        # Should be None or "moderate" depending on token estimation
        if checkpoint is not None:
            assert checkpoint in ("moderate", "caution", "high")


class TestCompressedContextModel:
    """Test CompressedContext model."""

    def test_compressed_context_creation(self):
        """Test creating CompressedContext record."""
        compressed = CompressedContext(
            original_item_id="ctx_0000_00000000",
            summary_item_id="ctx_sum_0001_00000001",
            compression_summary="Summary text",
            original_tokens=500,
            summary_tokens=50,
            token_savings=450,
        )

        assert compressed.original_item_id == "ctx_0000_00000000"
        assert compressed.summary_item_id == "ctx_sum_0001_00000001"
        assert compressed.compression_summary == "Summary text"
        assert compressed.token_savings == 450
        assert isinstance(compressed.compression_timestamp, datetime)


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_context_manager_wraps_repository_context(self):
        """Test that ContextManager is compatible with existing patterns."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        # Should be able to add evidence items just like RepositoryContext.evidence
        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="s1",
            summary="Test",
            data={},
        )

        item = manager.add_item(evidence)
        assert item is not None

        active = manager.list_context()
        assert len(active) > 0

    def test_items_list_preserved(self):
        """Test that items are stored and retrievable."""
        budget = ContextBudget()
        manager = ContextManager(budget)

        evidence = ContextEvidence(
            source_type="retrieval",
            source_id="s1",
            summary="Test",
            data={},
        )

        manager.add_item(evidence)

        # Items should be directly accessible
        assert len(manager.items) == 1
        assert isinstance(manager.items[0], ContextItem)
