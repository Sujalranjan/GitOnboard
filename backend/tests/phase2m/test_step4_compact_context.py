"""
STEP 4 - Verify Compact Initial Context

Assertions:
1. Initial context (compact) has no source_excerpt items
2. Source_excerpt appears ONLY after tool call adds it
"""
import pytest
from backend.agent.context.contracts import RepositoryContext, ContextEvidence
from backend.intelligence.engine.orchestration.stage8_grounding import LLMGrounder
from backend.intelligence.context_management.manager import ContextManager
from backend.agent.context.contracts import ContextBudget


class TestCompactContextAssertion:
    """Verify compact context excludes source_excerpt (ASSERTION 1)."""

    def test_compact_context_has_zero_source_excerpt(
        self,
        gitboard_login_query_context: RepositoryContext,
    ):
        """
        ASSERTION 1: Compact context has NO source_excerpt items.

        Initial context may have source_excerpt (actual code).
        Compact context should strip all source_excerpt items,
        leaving only metadata for the LLM to explore via tools.
        """
        grounder = LLMGrounder()

        # Count source_excerpt in initial context
        initial_source_excerpt = sum(
            1 for e in (gitboard_login_query_context.evidence or [])
            if _get_source_type(e) == "source_excerpt"
        )

        print(f"\n[STEP 4] Initial context: {initial_source_excerpt} source_excerpt items")

        # Create compact context
        compact = grounder._create_compact_context(gitboard_login_query_context)

        # Count source_excerpt in compact context
        compact_source_excerpt = sum(
            1 for e in (compact.evidence or [])
            if _get_source_type(e) == "source_excerpt"
        )

        print(f"[STEP 4] Compact context: {compact_source_excerpt} source_excerpt items")

        # ASSERTION 1: Must be zero
        assert compact_source_excerpt == 0, \
            f"Compact context should have NO source_excerpt items, but has {compact_source_excerpt}"

        print("✅ ASSERTION 1 PASSED: Compact context strips all source_excerpt")


class TestSourceExcerptLifecycle:
    """Verify source_excerpt appears only after tools add it (ASSERTION 2)."""

    def test_source_excerpt_appears_only_after_tool_call(self):
        """
        ASSERTION 2: source_excerpt appears ONLY after tool call adds it.

        Context manager starts empty. Tools call add_item() with source_excerpt.
        This validates the mechanism for evidence collection.
        """
        # Create empty context manager
        budget = ContextBudget(max_files=15, max_symbols=30)
        manager = ContextManager(budget=budget)

        # Initially empty
        initial_items = manager.list_context()
        assert len(initial_items) == 0, "Manager should start empty"

        print("\n[STEP 4] Initial context manager state: 0 items")
        print("✅ ASSERTION 2a: No source_excerpt before tools run")

        # Simulate tool adding source_excerpt evidence
        tool_evidence = ContextEvidence(
            source_type="source_excerpt",
            source_id="backend/routers/auth.py:15-30",
            relevance=0.95,
            confidence=1.0,
            summary="Login route implementation",
            data={"content": "def login_route(): pass"},
            metadata={"lines": "15-30"}
        )

        manager.add_item(tool_evidence, retrieval_source="tool_call")

        # After tool call, evidence appears
        after_tool_items = manager.list_context()
        assert len(after_tool_items) == 1, "Should have 1 item after tool call"

        added_item = after_tool_items[0]
        assert added_item.source_type == "source_excerpt", \
            f"Tool should add source_excerpt, got {added_item.source_type}"
        assert added_item.retrieval_source == "tool_call", \
            "Evidence should be marked as from tool call"

        print("[STEP 4] After tool call: 1 source_excerpt item added")
        print("✅ ASSERTION 2b: source_excerpt added by tools")
        print("✅ ASSERTION 2c: Evidence tracked with retrieval_source=tool_call")
        print("✅ ASSERTION 2 PASSED: source_excerpt lifecycle correct")


def _get_source_type(evidence) -> str:
    """Helper to extract source_type from dict or object."""
    if isinstance(evidence, dict):
        return evidence.get("source_type", "")
    return getattr(evidence, "source_type", "")
