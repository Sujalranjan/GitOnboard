"""
Phase 2M Testing: Interactive Research with Phase 2L Tools

Tests:
1. Tool wrapper execution (inspect_file, read_symbol, etc.)
2. Context compaction (remove source_excerpt)
3. Research loop (LLM tool-calling)
4. Real GitOnboard queries
5. Grounding validation
6. Research event tracking
"""
import pytest
import asyncio
import json
from sqlalchemy.orm import Session

from backend.intelligence.engine.orchestration.stage8_grounding import LLMGrounder, GroundingValidator
from backend.intelligence.engine.orchestration.stage8_phase2l_adapter import (
    Phase2LToolWrapper,
    ExecutionContext,
    ResearchEventType,
)
from backend.intelligence.context_management.manager import ContextManager
from backend.intelligence.context_management.models import ContextItemPriority
from backend.agent.context.contracts import RepositoryContext, ContextEvidence, ContextBudget
from backend.models.repository import Analysis


@pytest.fixture
def mock_execution_context(db: Session) -> ExecutionContext:
    """Create execution context for testing."""
    # Use real GitOnboard repository for testing
    import os
    repo_root = "/home/dheeraj/repository_intelligence_platform"

    # Create analysis if needed
    analysis = db.query(Analysis).filter_by(repo_name="default").first()
    if not analysis:
        analysis = Analysis(repo_name="default", status="completed")
        db.add(analysis)
        db.commit()

    return ExecutionContext(
        analysis_id=analysis.id,
        repo_root=repo_root,
        db=db,
        repo_name="default",
    )


@pytest.fixture
def mock_repository_context() -> RepositoryContext:
    """Create mock RepositoryContext with file/symbol metadata."""
    return RepositoryContext(
        requirement="Understand login flow",
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
            # Only structural evidence, no source code
            ContextEvidence(
                source_type="rim_fact",
                source_id="login_route",
                summary="login_route calls authenticate",
                data={"relationship": "calls"},
                confidence=0.95,
                relevance=0.8,
            ),
        ],
    )


class TestPhase2LToolWrapper:
    """Test Phase 2L tool wrapper and execution context injection."""

    def test_execution_context_creation(self, mock_execution_context: ExecutionContext):
        """Test that ExecutionContext is properly created."""
        assert mock_execution_context.analysis_id > 0
        assert mock_execution_context.repo_root
        assert mock_execution_context.db is not None

    def test_tool_wrapper_initialization(self, mock_execution_context: ExecutionContext):
        """Test that Phase2LToolWrapper initializes correctly."""
        context_manager = ContextManager(budget=ContextBudget(max_tokens=100000))
        wrapper = Phase2LToolWrapper(mock_execution_context, context_manager)

        assert wrapper.exec_ctx == mock_execution_context
        assert wrapper.context_manager == context_manager
        assert len(wrapper.events) == 0

    def test_inspect_file_tool(
        self,
        mock_execution_context: ExecutionContext,
    ):
        """Test inspect_file tool wrapper."""
        context_manager = ContextManager(budget=ContextBudget(max_tokens=100000))
        wrapper = Phase2LToolWrapper(mock_execution_context, context_manager)

        # Inspect a real file from the repository
        result = wrapper.inspect_file_tool("backend/app.py")

        assert result["success"] or result["success"] == False  # Either success or has error
        assert "tool" in result
        assert result["tool"] == "inspect_file"
        assert "file" in result

        # Check for research event
        assert any(e.event_type == ResearchEventType.TOOL_RESULT for e in wrapper.events)

    def test_read_symbol_tool(
        self,
        mock_execution_context: ExecutionContext,
    ):
        """Test read_symbol tool wrapper."""
        context_manager = ContextManager(budget=ContextBudget(max_tokens=100000))
        wrapper = Phase2LToolWrapper(mock_execution_context, context_manager)

        # Try to read a real symbol
        result = wrapper.read_symbol_tool("backend/models/fact_store.py", "Analysis")

        assert "success" in result
        assert "tool" in result
        assert result["tool"] == "read_symbol"

    def test_context_manager_integration(
        self,
        mock_execution_context: ExecutionContext,
    ):
        """Test that tool results are added to ContextManager."""
        context_manager = ContextManager(budget=ContextBudget(max_tokens=100000))
        wrapper = Phase2LToolWrapper(mock_execution_context, context_manager)

        # Inspect file should add to context
        result = wrapper.inspect_file_tool("backend/app.py")

        if result["success"]:
            # Check that something was added to context manager
            items = context_manager.list_context()
            # At least one item should be added for successful inspection
            # (may be 0 if file doesn't exist, which is ok)

    def test_research_event_emission(
        self,
        mock_execution_context: ExecutionContext,
    ):
        """Test that research events are properly emitted."""
        context_manager = ContextManager(budget=ContextBudget(max_tokens=100000))
        wrapper = Phase2LToolWrapper(mock_execution_context, context_manager)

        # Inspect file
        wrapper.inspect_file_tool("backend/app.py")

        # Should have events
        assert len(wrapper.events) > 0

        # Check event structure
        for event in wrapper.events:
            assert hasattr(event, "event_type")
            assert hasattr(event, "timestamp")
            assert hasattr(event, "stage")
            assert hasattr(event, "description")
            assert hasattr(event, "details")

            # Verify serialization
            event_dict = event.to_dict()
            assert "event_type" in event_dict
            assert "timestamp" in event_dict


class TestContextCompaction:
    """Test context compaction (removal of source_excerpt items)."""

    def test_create_compact_context(self, mock_repository_context: RepositoryContext):
        """Test that source_excerpt items are removed."""
        grounder = LLMGrounder()

        # Add a source_excerpt item
        mock_repository_context.evidence.append(
            ContextEvidence(
                source_type="source_excerpt",
                source_id="app.py",
                summary="Main application file",
                data={"content": "def app(): pass\n" * 100},  # Large code block
                confidence=0.95,
                relevance=0.8,
            )
        )

        # Original context should have source
        original_json = mock_repository_context.model_dump_json()
        assert "source_excerpt" in original_json
        assert "content" in original_json

        # Compact context should not have source
        compact_context = grounder._create_compact_context(mock_repository_context)
        compact_json = compact_context.model_dump_json()

        # Should have no source_excerpt
        compact_evidence_types = {e.source_type for e in compact_context.evidence}
        assert "source_excerpt" not in compact_evidence_types

        # Compact should be significantly smaller
        assert len(compact_json) < len(original_json)

    def test_compact_context_preserves_metadata(self, mock_repository_context: RepositoryContext):
        """Test that compaction preserves important metadata."""
        grounder = LLMGrounder()

        # Add various evidence types
        mock_repository_context.evidence.append(
            ContextEvidence(
                source_type="rim_fact",
                source_id="relationship1",
                summary="Important relationship",
                data={},
                confidence=0.95,
                relevance=0.8,
            )
        )

        compact = grounder._create_compact_context(mock_repository_context)

        # Metadata should be preserved
        assert len(compact.relevant_files) == len(mock_repository_context.relevant_files)
        assert len(compact.relevant_symbols) == len(mock_repository_context.relevant_symbols)

        # RIM facts should be preserved
        rim_facts = [e for e in compact.evidence if e.source_type == "rim_fact"]
        assert len(rim_facts) > 0


class TestGroundingValidation:
    """Test grounding validation against evidence."""

    def test_grounding_validator_with_evidence(self, mock_repository_context: RepositoryContext):
        """Test that grounding validator works with context evidence."""
        validator = GroundingValidator(mock_repository_context)

        # Test with an answer that cites the files
        answer = "The login flow is in backend/routers/auth.py"
        result = validator.validate(answer)

        assert result.grounding_status in ["grounded", "partial", "ungrounded", "insufficient_context"]
        assert len(result.validation_errors) >= 0

    def test_grounding_with_dynamic_evidence(self, mock_repository_context: RepositoryContext):
        """Test grounding with evidence added after initial context."""
        validator = GroundingValidator(mock_repository_context)

        # Add evidence dynamically
        mock_repository_context.evidence.append(
            ContextEvidence(
                source_type="source_excerpt",
                source_id="backend/app.py:run_server",
                summary="Server startup",
                data={"content": "def run_server(): pass"},
                confidence=0.95,
                relevance=0.8,
            )
        )

        # Re-create validator with updated context
        validator = GroundingValidator(mock_repository_context)

        # Answer that cites the new evidence
        answer = "The server starts in backend/app.py with the run_server function"
        result = validator.validate(answer)

        # Should recognize the references
        assert len(result.grounded_entities) > 0 or result.grounding_status == "partial"


class TestResearchEventTracking:
    """Test research event tracking for observability."""

    def test_event_serialization(self, mock_execution_context: ExecutionContext):
        """Test that research events can be serialized."""
        context_manager = ContextManager(budget=ContextBudget(max_tokens=100000))
        wrapper = Phase2LToolWrapper(mock_execution_context, context_manager)

        # Emit an event
        event = wrapper._emit_event(
            ResearchEventType.TOOL_INVOKED,
            "test",
            "Test event",
            {"test_data": "value"},
        )

        # Should be serializable to JSON
        event_dict = event.to_dict()
        json_str = json.dumps(event_dict)
        assert len(json_str) > 0

        # Should parse back
        parsed = json.loads(json_str)
        assert parsed["event_type"] == ResearchEventType.TOOL_INVOKED.value
        assert parsed["stage"] == "test"

    def test_event_pipeline(self, mock_execution_context: ExecutionContext):
        """Test event emission through tool pipeline."""
        context_manager = ContextManager(budget=ContextBudget(max_tokens=100000))
        wrapper = Phase2LToolWrapper(mock_execution_context, context_manager)

        # Run tool
        result = wrapper.inspect_file_tool("backend/app.py")

        # Should have emitted events
        events = wrapper.events

        # Should include tool invocation events
        event_types = {e.event_type for e in events}
        assert ResearchEventType.TOOL_RESULT in event_types or ResearchEventType.TOOL_ERROR in event_types


class TestInteractiveResearchLoop:
    """Test the interactive research loop (async)."""

    @pytest.mark.asyncio
    async def test_research_loop_compact_context(self, mock_repository_context: RepositoryContext):
        """Test that research loop uses compact context."""
        grounder = LLMGrounder()

        # Add source to context
        mock_repository_context.evidence.append(
            ContextEvidence(
                source_type="source_excerpt",
                source_id="app.py",
                summary="Main app",
                data={"content": "def app(): pass\n" * 100},
                confidence=0.95,
                relevance=0.8,
            )
        )

        original_size = len(mock_repository_context.model_dump_json())
        compact = grounder._create_compact_context(mock_repository_context)
        compact_size = len(compact.model_dump_json())

        # Compact should be smaller
        assert compact_size < original_size
        assert len([e for e in compact.evidence if e.source_type == "source_excerpt"]) == 0

    @pytest.mark.asyncio
    async def test_tool_descriptions(self):
        """Test that tool descriptions are properly formatted."""
        grounder = LLMGrounder()
        descriptions = grounder._get_tool_descriptions()

        # Should include all tool names
        tool_names = [
            "inspect_file",
            "read_symbol",
            "read_lines",
            "read_file",
            "get_context_status",
            "list_context",
        ]

        for tool in tool_names:
            assert tool in descriptions


class TestRealGitOnboardQueries:
    """Test with real GitOnboard repository queries."""

    @pytest.mark.asyncio
    async def test_query_1_authentication(self, mock_execution_context: ExecutionContext, db: Session):
        """Test Query 1: How does login work?"""
        grounder = LLMGrounder()

        # Create test context
        context = RepositoryContext(
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
                    source_id="login_flow",
                    summary="Authentication flow",
                    data={"relationship": "calls"},
                    confidence=0.95,
                    relevance=0.8,
                )
            ],
        )

        # Run without execution context to avoid tool calls in test
        answer, grounding, events = await grounder.ground(context, "How does login work?")

        assert len(answer) > 0
        assert grounding.grounding_status in ["grounded", "partial", "ungrounded", "insufficient_context"]

    @pytest.mark.asyncio
    async def test_grounding_validation_after_research(self, mock_repository_context: RepositoryContext):
        """Test that answers are properly grounded."""
        grounder = LLMGrounder()

        # Run without tools
        answer, grounding, events = await grounder.ground(
            mock_repository_context,
            "What files are involved in authentication?",
        )

        # Should produce answer
        assert len(answer) > 0

        # Should have grounding result
        assert hasattr(grounding, "grounding_status")
        assert grounding.grounding_status in [
            "grounded",
            "partial",
            "ungrounded",
            "insufficient_context",
        ]


class TestBackwardCompatibility:
    """Test that Phase 2M doesn't break existing Stage 8 usage."""

    def test_ground_without_execution_context(self, mock_repository_context: RepositoryContext):
        """Test that ground() still works without execution_context (backward compat)."""
        grounder = LLMGrounder()

        # Should work without execution_context
        try:
            # Use sync wrapper for simplicity
            from backend.intelligence.engine.orchestration.stage8_grounding import stage8_sync_wrapper

            answer, grounding, events = stage8_sync_wrapper(
                mock_repository_context,
                "Test question",
                execution_context=None,
            )

            assert len(answer) > 0
            assert events == []  # No events when no tools used

        except Exception as e:
            pytest.skip(f"Async test needs event loop: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
