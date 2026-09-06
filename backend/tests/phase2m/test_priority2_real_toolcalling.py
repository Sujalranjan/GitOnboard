"""
Priority 2: Verify Real LLM Tool-Calling

Tests that LLM actually causes Phase 2L tool invocation (not simulated).
Uses real GitOnboard repository and actual LLMService/model.

CANONICAL TEST: "How does login work?"
Expected: inspect_file(auth.py) → read_symbol() → final answer
"""
import pytest
import asyncio
import json
from datetime import datetime
from sqlalchemy.orm import Session

from backend.intelligence.engine.orchestration.stage8_grounding import LLMGrounder
from backend.intelligence.engine.orchestration.stage8_phase2l_adapter import (
    ExecutionContext,
    ResearchEventType,
)
from backend.agent.context.contracts import RepositoryContext, ContextEvidence
from backend.models.repository import Analysis


@pytest.fixture
def gitboard_execution_context(db: Session) -> ExecutionContext:
    """Create execution context using real GitOnboard repository."""
    # Get or create a test analysis
    analysis = db.query(Analysis).first()
    if not analysis:
        # Create a test repository and analysis
        from backend.models.repository import Repository
        repo = Repository(
            name="test-gitonboard",
            url="file:///home/dheeraj/repository_intelligence_platform",
            platform="local",
        )
        db.add(repo)
        db.flush()

        analysis = Analysis(
            repository_id=repo.id,
            status="completed",
        )
        db.add(analysis)
        db.commit()

    return ExecutionContext(
        analysis_id=analysis.id,
        repo_root="/home/dheeraj/repository_intelligence_platform",
        db=db,
        repo_name="default",
    )


@pytest.fixture
def gitboard_login_query_context() -> RepositoryContext:
    """Create RepositoryContext for login query using real retrieval."""
    # These would normally come from Stage 5/6 retrieval
    return RepositoryContext(
        repository_id="gitonboard",
        requirement="How does login work? Explain the authentication flow.",
        relevant_files=[
            "backend/routers/auth.py",
            "backend/services/auth_service.py",
            "backend/models/user.py",
        ],
        relevant_symbols=[
            {"name": "login_route", "file": "backend/routers/auth.py"},
            {"name": "authenticate", "file": "backend/services/auth_service.py"},
        ],
        evidence=[
            ContextEvidence(
                source_type="rim_fact",
                source_id="auth_flow",
                summary="Authentication route and service",
                data={"relationship": "login_route calls authenticate"},
                confidence=0.95,
                relevance=0.9,
            )
        ],
    )


class TestRealToolCalling:
    """Test that Phase 2M actually calls Phase 2L tools end-to-end."""

    @pytest.mark.asyncio
    async def test_login_query_with_actual_tools(
        self,
        gitboard_execution_context: ExecutionContext,
        gitboard_login_query_context: RepositoryContext,
    ):
        """
        Test: "How does login work?"

        Expected behavior:
        1. LLM receives compact initial context (metadata only)
        2. LLM decides to inspect auth files
        3. LLM calls inspect_file tool
        4. Tool executes and returns symbols
        5. LLM requests to read specific symbols
        6. Tool executes and returns source
        7. LLM provides final answer
        8. Answer is grounded in inspected evidence

        DO NOT accept:
        - Mocked LLM responses
        - Simulated tool calls
        - Hardcoded answers
        - Tool calls that don't actually run
        """
        grounder = LLMGrounder()

        try:
            answer, grounding, events = await grounder.ground_interactive(
                gitboard_login_query_context,
                "How does login work?",
                gitboard_execution_context,
            )

            # Verify answer exists
            assert len(answer) > 0, "Answer should not be empty"
            assert isinstance(answer, str), "Answer should be a string"

            # Verify grounding result
            assert grounding.grounding_status in [
                "grounded",
                "partial",
                "ungrounded",
                "insufficient_context",
            ]

            # Most important: Verify that tools were actually invoked
            tool_events = [
                e for e in events
                if e.event_type in [
                    ResearchEventType.TOOL_INVOKED,
                    ResearchEventType.TOOL_RESULT,
                ]
            ]

            # Log the actual research trace
            print("\n=== ACTUAL RESEARCH TRACE ===")
            print(f"Total events: {len(events)}")
            print(f"Tool invocations: {len(tool_events)}")
            for event in events:
                print(f"  [{event.event_type.value}] {event.description}")
                if event.details:
                    for k, v in list(event.details.items())[:3]:  # First 3 details
                        print(f"    - {k}: {v}")

            # CRITICAL VALIDATION: Tools must have been invoked
            if len(tool_events) == 0:
                pytest.fail(
                    "CRITICAL: No tool invocations detected! LLM did not use Phase 2L tools. "
                    "This indicates tool-calling loop is not working end-to-end."
                )

            # Verify answer quality (it should mention authentication concepts)
            answer_lower = answer.lower()
            auth_concepts = ["login", "authenticate", "password", "token", "route", "request"]
            found_concepts = [c for c in auth_concepts if c in answer_lower]

            assert (
                len(found_concepts) > 0
            ), f"Answer should contain authentication concepts, got: {answer[:200]}"

        except ValueError as e:
            if "REPOSITORY_CONTEXT_ERROR" in str(e):
                pytest.fail(f"Execution context error (should have been validated): {e}")
            raise

    @pytest.mark.asyncio
    async def test_tool_calling_requires_actual_invocation(
        self,
        gitboard_execution_context: ExecutionContext,
        gitboard_login_query_context: RepositoryContext,
    ):
        """
        Verify that tool-calling is not just JSON parsing in the test.

        Tool invocation means:
        - Actual Phase 2L tool executed (not mocked)
        - Actual repository symbols retrieved
        - Actual source code read (if applicable)
        - Results added to ContextManager
        """
        grounder = LLMGrounder()

        answer, grounding, events = await grounder.ground_interactive(
            gitboard_login_query_context,
            "How does login work?",
            gitboard_execution_context,
        )

        # Extract tool result events
        tool_results = [
            e for e in events if e.event_type == ResearchEventType.TOOL_RESULT
        ]

        print("\n=== TOOL RESULTS ===")
        for result in tool_results:
            print(f"Tool: {result.details.get('tool', 'unknown')}")
            print(f"  File: {result.details.get('file_path', 'N/A')}")
            print(f"  Symbol: {result.details.get('symbol', 'N/A')}")
            print(f"  Success: {result.details.get('success', False)}")
            print(f"  Lines: {result.details.get('lines', 'N/A')}")
            print(f"  Tokens: {result.details.get('tokens', 0)}")

        # At minimum, file inspection should have occurred
        file_inspection_results = [
            r
            for r in tool_results
            if r.details.get("tool") == "inspect_file" and r.details.get("success")
        ]

        if len(file_inspection_results) == 0:
            # If no successful file inspection, check if model tried but failed
            tool_invocations = [
                e
                for e in events
                if e.event_type == ResearchEventType.TOOL_INVOKED
            ]
            if len(tool_invocations) == 0:
                pytest.fail(
                    "No tool invocations at all. LLM tool-calling loop is not working."
                )
            else:
                pytest.fail(
                    f"Tools were invoked ({len(tool_invocations)}) but none succeeded. "
                    "Check tool implementation and error handling."
                )


class TestCompactInitialContext:
    """Verify that initial context does NOT contain bulk source."""

    @pytest.mark.asyncio
    async def test_no_source_excerpt_in_initial_context(
        self,
        gitboard_execution_context: ExecutionContext,
        gitboard_login_query_context: RepositoryContext,
    ):
        """Verify that source_excerpt items are stripped from initial context."""
        grounder = LLMGrounder()

        # Add a source_excerpt to the initial context
        gitboard_login_query_context.evidence.append(
            ContextEvidence(
                source_type="source_excerpt",
                source_id="auth.py",
                summary="Auth file",
                data={"content": "def login():\n    pass\n" * 50},  # Large code
                confidence=0.95,
                relevance=0.8,
            )
        )

        # Verify it's in the original
        assert any(
            e.source_type == "source_excerpt"
            for e in gitboard_login_query_context.evidence
        )

        # Now verify compaction removes it
        compact = grounder._create_compact_context(gitboard_login_query_context)

        # source_excerpt should be removed
        source_excerpts = [e for e in compact.evidence if e.source_type == "source_excerpt"]
        assert (
            len(source_excerpts) == 0
        ), f"Compact context should have no source_excerpt, found {len(source_excerpts)}"

        # But other evidence should remain
        rim_facts = [e for e in compact.evidence if e.source_type == "rim_fact"]
        assert len(rim_facts) > 0, "Should preserve non-source evidence"


class TestResearchEventTracing:
    """Verify that research events are properly emitted and traceable."""

    @pytest.mark.asyncio
    async def test_event_sequence_structure(
        self,
        gitboard_execution_context: ExecutionContext,
        gitboard_login_query_context: RepositoryContext,
    ):
        """Verify event sequence has proper structure."""
        grounder = LLMGrounder()

        answer, grounding, events = await grounder.ground_interactive(
            gitboard_login_query_context,
            "How does login work?",
            gitboard_execution_context,
        )

        # Events must include at least:
        event_types = {e.event_type for e in events}

        required_events = {
            ResearchEventType.RESEARCH_STARTED,
            ResearchEventType.RESEARCH_COMPLETED,
        }

        for required in required_events:
            assert (
                required in event_types
            ), f"Missing required event: {required.value}"

        # Events must be chronologically ordered
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(
            timestamps
        ), "Events should be in chronological order"

        # Each event must be properly structured
        for event in events:
            assert event.event_type is not None
            assert event.timestamp is not None
            assert isinstance(event.timestamp, datetime)
            assert event.stage is not None
            assert event.description is not None
            assert isinstance(event.details, dict)

            # Serialize to JSON (for frontend)
            event_dict = event.to_dict()
            assert "event_type" in event_dict
            assert "timestamp" in event_dict
            assert "stage" in event_dict
            assert "description" in event_dict
            assert "details" in event_dict

            # Must be JSON-serializable
            json_str = json.dumps(event_dict)
            assert len(json_str) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
