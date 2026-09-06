"""
Unit tests for token accounting and budget management (Phase 2L).

Tests token estimation, budget enforcement, and checkpoint calculation.
"""

import pytest

from backend.intelligence.context_management.token_accounting import (
    estimate_tokens,
    estimate_tokens_from_text,
    BudgetCheckpoint,
    evaluate_budget_status,
)


class TestTokenEstimation:
    """Tests for token estimation functions."""

    def test_estimate_tokens_empty_dict(self):
        """Verify empty dict estimates to minimum 1 token."""
        count = estimate_tokens({})
        assert count >= 1

    def test_estimate_tokens_small_data(self):
        """Verify reasonable estimates for small data."""
        data = {"key": "value"}
        count = estimate_tokens(data)
        assert count >= 1

    def test_estimate_tokens_large_data(self):
        """Verify estimates scale with data size."""
        small_data = {"key": "v"}
        large_data = {"key": "v" * 1000}

        small_count = estimate_tokens(small_data)
        large_count = estimate_tokens(large_data)

        assert large_count > small_count

    def test_estimate_tokens_complex_structure(self):
        """Verify nested structures are estimated."""
        data = {
            "symbols": [
                {"name": "func1", "line": 1},
                {"name": "func2", "line": 10},
            ],
            "relationships": [
                {"from": "func1", "to": "func2"}
            ]
        }
        count = estimate_tokens(data)
        assert count > 0

    def test_estimate_tokens_non_serializable_fallback(self):
        """Verify fallback for non-JSON-serializable data."""
        class CustomObject:
            pass

        data = {"obj": CustomObject()}
        count = estimate_tokens(data)
        # Should fall back to default
        assert count == 100


class TestTokenEstimationFromText:
    """Tests for text-based token estimation."""

    def test_estimate_tokens_from_text_empty(self):
        """Verify empty text estimates to minimum 1 token."""
        count = estimate_tokens_from_text("")
        assert count >= 1

    def test_estimate_tokens_from_text_small(self):
        """Verify reasonable estimates for small text."""
        count = estimate_tokens_from_text("hello")
        assert count >= 1

    def test_estimate_tokens_from_text_large(self):
        """Verify estimates scale with text length."""
        small_text = "hello"
        large_text = "hello" * 100

        small_count = estimate_tokens_from_text(small_text)
        large_count = estimate_tokens_from_text(large_text)

        assert large_count > small_count

    def test_estimate_tokens_from_text_multiline(self):
        """Verify multiline text is estimated."""
        text = """def function():
    x = 1
    y = 2
    return x + y
"""
        count = estimate_tokens_from_text(text)
        assert count > 0


class TestBudgetCheckpoint:
    """Tests for BudgetCheckpoint status tracking."""

    def test_checkpoint_initialization(self):
        """Verify checkpoint initializes correctly."""
        cp = BudgetCheckpoint(50000, 100000)
        assert cp.current_tokens == 50000
        assert cp.configured_budget == 100000

    def test_checkpoint_utilization_calculation(self):
        """Verify utilization is calculated as fraction."""
        cp = BudgetCheckpoint(50000, 100000)
        assert abs(cp.utilization - 0.5) < 0.001

    def test_checkpoint_percentage(self):
        """Verify percentage is calculated correctly."""
        cp = BudgetCheckpoint(50000, 100000)
        assert abs(cp.percentage - 50.0) < 0.01

    def test_checkpoint_status_normal(self):
        """Verify status < 50% is 'normal'."""
        cp = BudgetCheckpoint(30000, 100000)
        assert cp.status == "normal"

    def test_checkpoint_status_moderate(self):
        """Verify status 50-70% is 'moderate'."""
        cp = BudgetCheckpoint(60000, 100000)
        assert cp.status == "moderate"

    def test_checkpoint_status_caution(self):
        """Verify status 70-85% is 'caution'."""
        cp = BudgetCheckpoint(80000, 100000)
        assert cp.status == "caution"

    def test_checkpoint_status_high(self):
        """Verify status 85-95% is 'high'."""
        cp = BudgetCheckpoint(90000, 100000)
        assert cp.status == "high"

    def test_checkpoint_status_critical(self):
        """Verify status > 95% is 'critical'."""
        cp = BudgetCheckpoint(96000, 100000)
        assert cp.status == "critical"

    def test_checkpoint_boundary_50_percent(self):
        """Verify boundary at 50% transitions from normal to moderate."""
        cp_just_below = BudgetCheckpoint(49999, 100000)
        cp_just_above = BudgetCheckpoint(50000, 100000)

        assert cp_just_below.status == "normal"
        assert cp_just_above.status == "moderate"

    def test_checkpoint_boundary_70_percent(self):
        """Verify boundary at 70% transitions from moderate to caution."""
        cp_just_below = BudgetCheckpoint(69999, 100000)
        cp_just_above = BudgetCheckpoint(70000, 100000)

        assert cp_just_below.status == "moderate"
        assert cp_just_above.status == "caution"

    def test_checkpoint_boundary_85_percent(self):
        """Verify boundary at 85% transitions from caution to high."""
        cp_just_below = BudgetCheckpoint(84999, 100000)
        cp_just_above = BudgetCheckpoint(85000, 100000)

        assert cp_just_below.status == "caution"
        assert cp_just_above.status == "high"

    def test_checkpoint_boundary_95_percent(self):
        """Verify boundary at 95% transitions from high to critical."""
        cp_just_below = BudgetCheckpoint(94999, 100000)
        cp_just_above = BudgetCheckpoint(95000, 100000)

        assert cp_just_below.status == "high"
        assert cp_just_above.status == "critical"

    def test_checkpoint_zero_budget(self):
        """Verify handling of zero budget."""
        cp = BudgetCheckpoint(0, 0)
        assert cp.utilization == 0.0
        assert cp.status == "normal"

    def test_checkpoint_str_representation(self):
        """Verify checkpoint has meaningful string representation."""
        cp = BudgetCheckpoint(50000, 100000)
        str_rep = str(cp)
        assert "moderate" in str_rep
        assert "50.0" in str_rep


class TestEvaluateBudgetStatus:
    """Tests for budget status evaluation function."""

    def test_evaluate_budget_status_normal(self):
        """Verify function returns 'normal' for < 50%."""
        status = evaluate_budget_status(30000, 100000)
        assert status == "normal"

    def test_evaluate_budget_status_moderate(self):
        """Verify function returns 'moderate' for 50-70%."""
        status = evaluate_budget_status(60000, 100000)
        assert status == "moderate"

    def test_evaluate_budget_status_caution(self):
        """Verify function returns 'caution' for 70-85%."""
        status = evaluate_budget_status(80000, 100000)
        assert status == "caution"

    def test_evaluate_budget_status_high(self):
        """Verify function returns 'high' for 85-95%."""
        status = evaluate_budget_status(90000, 100000)
        assert status == "high"

    def test_evaluate_budget_status_critical(self):
        """Verify function returns 'critical' for > 95%."""
        status = evaluate_budget_status(96000, 100000)
        assert status == "critical"

    def test_evaluate_budget_status_zero_budget(self):
        """Verify function handles zero budget."""
        status = evaluate_budget_status(0, 0)
        assert status == "normal"

    def test_evaluate_budget_status_exceeds_budget(self):
        """Verify function handles exceeding budget."""
        status = evaluate_budget_status(110000, 100000)
        assert status == "critical"


class TestTokenBudgetEnforcement:
    """Tests for token budget enforcement logic."""

    def test_cannot_exceed_budget_at_critical(self):
        """Verify system should reject expensive additions when critical."""
        cp = BudgetCheckpoint(96000, 100000)
        assert cp.status == "critical"

        # Attempting to add 10000 tokens would exceed budget
        would_exceed = (cp.current_tokens + 10000) > cp.configured_budget
        assert would_exceed

    def test_can_add_tokens_at_caution(self):
        """Verify system can add tokens when at caution level."""
        cp = BudgetCheckpoint(80000, 100000)
        assert cp.status == "caution"

        # Can still add small amounts
        remaining = cp.configured_budget - cp.current_tokens
        assert remaining > 0

    def test_budget_enforcement_guards(self):
        """Verify budget enforcement decision logic."""
        # At 95%+: reject expensive additions
        cp_critical = BudgetCheckpoint(96000, 100000)
        expensive_request = 10000  # Would exceed budget
        should_reject = (cp_critical.current_tokens + expensive_request) > cp_critical.configured_budget
        assert should_reject

        # At 85-95%: warn but allow small additions
        cp_high = BudgetCheckpoint(90000, 100000)
        small_request = 5000
        can_fit = (cp_high.current_tokens + small_request) <= cp_high.configured_budget
        assert can_fit


class TestTokenAccountingIntegration:
    """Integration tests for token accounting."""

    def test_token_estimation_and_budget_workflow(self):
        """Verify token estimation works with budget checkpoint."""
        # Simulate adding evidence items
        data1 = {"content": "This is some evidence data"}
        data2 = {"content": "More evidence here"}

        tokens1 = estimate_tokens(data1)
        tokens2 = estimate_tokens(data2)

        # Verify tokens accumulate
        total = tokens1 + tokens2
        assert total > tokens1
        assert total > tokens2

        # Check budget status
        cp = BudgetCheckpoint(total, 100000)
        assert cp.status in ("normal", "moderate")

    def test_text_vs_dict_estimation_consistency(self):
        """Verify text and dict estimation are consistent."""
        text = "hello world this is a test"
        data = {"content": text}

        tokens_from_text = estimate_tokens_from_text(text)
        tokens_from_dict = estimate_tokens(data)

        # Both should estimate tokens, dict will be slightly higher due to JSON overhead
        assert tokens_from_dict >= tokens_from_text
        assert tokens_from_text >= 1
