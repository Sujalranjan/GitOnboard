"""
Context lifecycle management for Phase 2L.

Provides:
- ContextItem: Extended evidence with lifecycle metadata
- ContextManager: Active context lifecycle management
- PriorityPolicy: Deterministic priority assignment
- Token accounting: Estimation and budget tracking
"""

from .manager import ContextManager
from .models import (
    ContextItem,
    ContextItemPriority,
    ContextItemState,
    CompressedContext,
)
from .priority_policy import PriorityPolicy
from .token_accounting import (
    estimate_tokens,
    estimate_tokens_from_text,
    BudgetCheckpoint,
    evaluate_budget_status,
)

__all__ = [
    "ContextManager",
    "ContextItem",
    "ContextItemPriority",
    "ContextItemState",
    "CompressedContext",
    "PriorityPolicy",
    "estimate_tokens",
    "estimate_tokens_from_text",
    "BudgetCheckpoint",
    "evaluate_budget_status",
]
