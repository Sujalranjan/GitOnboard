"""
Token accounting and estimation for context lifecycle management.

Provides token estimation for evidence items and budget checkpoint calculation.
"""

import json
from typing import Any, Dict, Optional


def estimate_tokens(data: Dict[str, Any]) -> int:
    """
    Estimate tokens in evidence data.

    Uses a simple heuristic: serialize to JSON and estimate 1 token per 4 characters.
    This is a rough approximation and should be refined with actual tokenizer if available.

    Args:
        data: Dictionary of evidence data to estimate

    Returns:
        Estimated token count
    """
    try:
        # Serialize to JSON to get character count
        json_str = json.dumps(data)
        # Rough estimation: 1 token ≈ 4 characters
        # This is a conservative estimate
        estimated = len(json_str) // 4
        # Minimum 1 token per item
        return max(1, estimated)
    except (TypeError, ValueError):
        # Fallback if data is not JSON-serializable
        return 100


def estimate_tokens_from_text(text: str) -> int:
    """
    Estimate tokens in text content.

    Uses simple heuristic: 1 token ≈ 4 characters.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    return max(1, len(text) // 4)


class BudgetCheckpoint:
    """Represents budget status at a point in time."""

    def __init__(self, current_tokens: int, configured_budget: int):
        self.current_tokens = current_tokens
        self.configured_budget = configured_budget
        self.utilization = current_tokens / configured_budget if configured_budget > 0 else 0.0

    @property
    def status(self) -> str:
        """
        Get budget status label.

        Returns:
            "normal", "moderate", "caution", "high", or "critical"
        """
        if self.utilization < 0.5:
            return "normal"
        elif self.utilization < 0.7:
            return "moderate"
        elif self.utilization < 0.85:
            return "caution"
        elif self.utilization < 0.95:
            return "high"
        else:
            return "critical"

    @property
    def percentage(self) -> float:
        """Get utilization percentage (0-100)."""
        return self.utilization * 100

    def __str__(self) -> str:
        return f"BudgetCheckpoint(status={self.status}, utilization={self.percentage:.1f}%, tokens={self.current_tokens}/{self.configured_budget})"


def evaluate_budget_status(current_tokens: int, budget: int) -> str:
    """
    Evaluate budget status.

    Status thresholds:
    - < 50%: "normal"
    - 50-70%: "moderate"
    - 70-85%: "caution"
    - 85-95%: "high"
    - > 95%: "critical"

    Args:
        current_tokens: Current token usage
        budget: Configured token budget

    Returns:
        Status string
    """
    checkpoint = BudgetCheckpoint(current_tokens, budget)
    return checkpoint.status
