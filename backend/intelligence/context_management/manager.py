"""
Context lifecycle management.

ContextManager handles active context lifecycle:
- Adding items with ID assignment
- Priority assignment
- Token accounting
- Utilization tracking
- Compression and dropping operations
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.agent.context.contracts import ContextBudget, ContextEvidence

from .models import ContextItem, ContextItemPriority, ContextItemState, CompressedContext
from .priority_policy import PriorityPolicy
from .token_accounting import BudgetCheckpoint, estimate_tokens


class ContextManager:
    """
    Manages active context lifecycle.

    Responsibilities:
    - Track context items with immutable IDs
    - Assign and enforce priorities
    - Account for token usage
    - Support compression and dropping
    - Provide utilization statistics
    """

    def __init__(
        self,
        budget: ContextBudget,
        configured_context_budget_tokens: int = 100000,
    ):
        """
        Initialize ContextManager.

        Args:
            budget: ContextBudget with capacity limits
            configured_context_budget_tokens: Maximum tokens for active context (default 100K)
        """
        self.items: List[ContextItem] = []
        self.budget = budget
        self.configured_budget_tokens = configured_context_budget_tokens
        self.peak_tokens_used = 0
        self._item_counter = 0

    def add_item(
        self,
        evidence: ContextEvidence,
        priority: Optional[ContextItemPriority] = None,
        retrieval_source: str = "unknown",
    ) -> ContextItem:
        """
        Create ContextItem from evidence and add to manager.

        Args:
            evidence: ContextEvidence to add
            priority: Optional priority override. If None, assigned by policy.
            retrieval_source: How item was retrieved

        Returns:
            Created ContextItem with assigned ID
        """
        # Estimate tokens
        estimated_tokens = estimate_tokens(evidence.data)

        # Assign priority if not provided
        if priority is None:
            priority, reason = PriorityPolicy.assign_priority(evidence)
        else:
            reason = None

        # Create context item with assigned ID
        item = ContextItem(
            context_item_id=f"ctx_{self._item_counter:04d}_{hex(self._item_counter)[2:]:>8}",
            priority=priority,
            estimated_tokens=estimated_tokens,
            state=ContextItemState.ACTIVE,
            is_compressed=False,
            created_timestamp=datetime.now(),
            retrieval_source=retrieval_source,
            reason_for_priority=reason,
            # ContextEvidence fields
            source_type=evidence.source_type,
            source_id=evidence.source_id,
            relevance=evidence.relevance,
            confidence=evidence.confidence,
            summary=evidence.summary,
            data=evidence.data,
            metadata=evidence.metadata,
        )

        self.items.append(item)
        self._item_counter += 1
        self._update_peak()

        return item

    def list_context(self) -> List[ContextItem]:
        """
        Return all active context items.

        Returns:
            List of items in ACTIVE or REFERENCE states
        """
        return [
            item for item in self.items
            if item.state in (ContextItemState.ACTIVE, ContextItemState.REFERENCE)
        ]

    def get_context_statistics(self) -> Dict[str, Any]:
        """
        Return comprehensive context statistics.

        Returns:
            Dictionary with:
            - total_items: Total items tracked
            - active_items: Items in active/reference state
            - active_tokens: Tokens used by active items
            - peak_tokens: Peak tokens ever used
            - utilization_percent: 0-100 utilization
            - items_by_priority: Count by priority level
            - items_by_state: Count by state
            - budget_status: Current budget status
        """
        active_items = self.list_context()
        active_tokens = sum(item.estimated_tokens for item in active_items)
        utilization = (active_tokens / self.configured_budget_tokens * 100
                      if self.configured_budget_tokens > 0 else 0.0)

        checkpoint = BudgetCheckpoint(active_tokens, self.configured_budget_tokens)

        priority_counts = {}
        for priority in ContextItemPriority:
            priority_counts[priority.value] = len(
                [item for item in self.items if item.priority == priority]
            )

        state_counts = {}
        for state in ContextItemState:
            state_counts[state.value] = len(
                [item for item in self.items if item.state == state]
            )

        return {
            "total_items": len(self.items),
            "active_items": len(active_items),
            "active_tokens": active_tokens,
            "peak_tokens": self.peak_tokens_used,
            "utilization_percent": utilization,
            "budget_status": checkpoint.status,
            "items_by_priority": priority_counts,
            "items_by_state": state_counts,
        }

    def calculate_utilization(self) -> float:
        """
        Calculate current token utilization as fraction.

        Returns:
            Float in range [0.0, 1.0]
        """
        active_items = self.list_context()
        active_tokens = sum(item.estimated_tokens for item in active_items)
        if self.configured_budget_tokens == 0:
            return 0.0
        return active_tokens / self.configured_budget_tokens

    def get_budget_checkpoint(self) -> Optional[str]:
        """
        Get budget checkpoint status.

        Returns:
            "moderate" (70%), "high" (85%), or None
        """
        checkpoint = BudgetCheckpoint(
            sum(item.estimated_tokens for item in self.list_context()),
            self.configured_budget_tokens
        )
        if checkpoint.status in ("high", "caution"):
            return checkpoint.status
        return None

    def drop_context(self, context_item_id: str) -> bool:
        """
        Mark context item as DROPPED.

        Content is preserved but hidden from active context.

        Args:
            context_item_id: ID of item to drop

        Returns:
            True if item was found and dropped, False otherwise
        """
        for item in self.items:
            if item.context_item_id == context_item_id:
                if PriorityPolicy.can_drop(item.priority):
                    item.state = ContextItemState.DROPPED
                    return True
                return False
        return False

    def summarize_context(
        self,
        context_item_id: str,
        summary: str,
        summary_tokens: int,
    ) -> Optional[CompressedContext]:
        """
        Replace large source item with compact summary.

        Args:
            context_item_id: ID of item to summarize
            summary: Summary text
            summary_tokens: Token count of summary

        Returns:
            CompressedContext record or None if item not found
        """
        for item in self.items:
            if item.context_item_id == context_item_id:
                if not PriorityPolicy.can_compress(item.priority):
                    return None

                original_tokens = item.estimated_tokens
                token_savings = max(0, original_tokens - summary_tokens)

                # Create new item for summary
                summary_item = ContextItem(
                    context_item_id=f"ctx_sum_{self._item_counter:04d}_{hex(self._item_counter)[2:]:>8}",
                    priority=item.priority,
                    estimated_tokens=summary_tokens,
                    state=ContextItemState.ACTIVE,
                    is_compressed=True,
                    compression_summary=summary,
                    original_context_item_id=context_item_id,
                    compression_timestamp=datetime.now(),
                    created_timestamp=datetime.now(),
                    retrieval_source=item.retrieval_source,
                    reason_for_priority=f"Compressed from {context_item_id}",
                    # ContextEvidence fields
                    source_type=item.source_type,
                    source_id=item.source_id,
                    relevance=item.relevance,
                    confidence=item.confidence,
                    summary=summary,
                    data={"compressed": True, "original_id": context_item_id},
                    metadata=item.metadata,
                )

                self.items.append(summary_item)
                self._item_counter += 1

                # Mark original as reference (hidden from active context)
                item.state = ContextItemState.REFERENCE

                self._update_peak()

                return CompressedContext(
                    original_item_id=context_item_id,
                    summary_item_id=summary_item.context_item_id,
                    compression_summary=summary,
                    original_tokens=original_tokens,
                    summary_tokens=summary_tokens,
                    token_savings=token_savings,
                    original_still_retrievable=True,
                )

        return None

    def re_request_dropped_context(self, context_item_id: str) -> Optional[ContextItem]:
        """
        Retrieve dropped context if still available.

        Reactivates dropped item and returns it.

        Args:
            context_item_id: ID of dropped item to reactivate

        Returns:
            Reactivated ContextItem or None if not found
        """
        for item in self.items:
            if item.context_item_id == context_item_id and item.state == ContextItemState.DROPPED:
                item.state = ContextItemState.ACTIVE
                self._update_peak()
                return item
        return None

    def _update_peak(self) -> None:
        """Update peak tokens used if current usage exceeds it."""
        active_items = self.list_context()
        active_tokens = sum(item.estimated_tokens for item in active_items)
        if active_tokens > self.peak_tokens_used:
            self.peak_tokens_used = active_tokens
