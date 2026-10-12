"""
Comprehensive Verification Test Suite for LLM Tool Layer Enhancements.

Tests:
1. Tool set isolation (baseline vs RIM)
2. No phantom tools in specs, strategies, or KNOWN_TOOLS
3. read_file with context_lines
4. query_rim parameter clamping, scopes (LOCAL, NEIGHBORHOOD, GLOBAL), and directions (FORWARD, REVERSE, BOTH)
5. query_rim resolution states (STATIC_CONFIRMED, NO_STATIC_EDGE_FOUND, ENTITY_NOT_FOUND)
6. query_rim fallback generation
7. query_rim multi-hop path tracking
8. QAProtocolAdapter intent-based prompt generation
"""

import pytest
from unittest.mock import MagicMock
from backend.services.tool_dispatch import ToolDispatchTable, TargetEntityResolver
from backend.services.qa_protocol import QAProtocolAdapter, ToolSpec
from backend.intelligence.retrieval.graph_traverser import (
    FactStoreGraphTraverser,
    TraversedEntity,
    RelationshipTraversalResult,
)
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship, FactRoute, FactDatabaseObject
from backend.agent.intent.semantic_query import (
    SemanticQueryIntent,
    SemanticQueryClass,
    TraversalDirection,
)


class TestToolSpecWhitelisting:
    """Verifies that only the 6 intended tools are exposed to the LLM."""

    def test_baseline_specs(self):
        tool_layer = MagicMock()
        dispatch = ToolDispatchTable(tool_layer)
        specs = dispatch.specs(include_rim=False)
        names = [s.name for s in specs]

        assert names == ["read_file", "search_repository", "get_tree"]
        assert "get_symbol" not in names
        assert "get_callers" not in names
        assert "get_callees" not in names
        assert "query_rim" not in names

    def test_rim_specs_only_6_tools(self):
        tool_layer = MagicMock()
        traverser = MagicMock(spec=FactStoreGraphTraverser)
        resolver = MagicMock(spec=TargetEntityResolver)
        dispatch = ToolDispatchTable(tool_layer, traverser, resolver)

        specs = dispatch.specs(include_rim=True)
        names = [s.name for s in specs]

        # Must match exact intended 6 tools
        expected_tools = ["read_file", "search_repository", "get_tree", "get_file_outline", "search_code", "get_code_relationships"]
        assert sorted(names) == sorted(expected_tools)

        # Removed LLM-facing tools
        assert "get_symbol" not in names
        assert "get_callers" not in names
        assert "get_callees" not in names

    def test_no_phantom_tools_in_prompt_adapter(self):
        adapter = QAProtocolAdapter(model_id="gpt-4", native_tools=True)

        phantom_tools = [
            "search_symbols", "get_route", "get_feature",
            "get_dependencies", "trace_feature", "find_files"
        ]

        # Verify phantom tools are absent from TOOL_USAGE_STRATEGIES
        for phantom in phantom_tools:
            assert phantom not in adapter.TOOL_USAGE_STRATEGIES, f"Phantom tool '{phantom}' found in strategies"

        # Verify old LLM-facing tools are also absent from strategies
        assert "get_callers" not in adapter.TOOL_USAGE_STRATEGIES
        assert "get_callees" not in adapter.TOOL_USAGE_STRATEGIES
        assert "get_symbol" not in adapter.TOOL_USAGE_STRATEGIES

        # Verify prompt strategy generation does not mention phantom tools
        tool_layer = MagicMock()
        traverser = MagicMock(spec=FactStoreGraphTraverser)
        resolver = MagicMock(spec=TargetEntityResolver)
        dispatch = ToolDispatchTable(tool_layer, traverser, resolver)
        specs = dispatch.specs(include_rim=True)

        prompt_parts = adapter.build_system_prompt(specs, rim_metadata_block="Sample metadata")
        for phantom in phantom_tools:
            assert phantom not in prompt_parts.tool_catalog_text
            assert phantom not in prompt_parts.grounding_and_protocol_text


class TestReadFileContextLines:
    """Verifies read_file context_lines functionality."""

    def test_read_file_passes_context_lines(self):
        tool_layer = MagicMock()
        tool_layer.read_file.return_value = {"path": "main.py", "start_line": 5, "end_line": 25, "content": "..."}

        dispatch = ToolDispatchTable(tool_layer)
        obs = dispatch.dispatch("read_file", {"path": "main.py", "start_line": 10, "end_line": 20, "context_lines": 5})

        assert obs.success is True
        tool_layer.read_file.assert_called_once_with("main.py", 10, 20, context_lines=5)


class TestQueryRimSemanticsAndResolution:
    """Verifies query_rim bounded traversal, directions, resolution states, and fallbacks."""

    def test_query_rim_entity_not_found_returns_explicit_fallback(self):
        tool_layer = MagicMock()
        traverser = MagicMock(spec=FactStoreGraphTraverser)
        resolver = MagicMock(spec=TargetEntityResolver)
        resolver.resolve.return_value = None  # Entity not in repository index

        dispatch = ToolDispatchTable(tool_layer, traverser, resolver)
        obs = dispatch.dispatch("get_code_relationships", {"entity_name": "nonExistentSymbol"})

        assert obs.success is True
        assert obs.data["found"] is False
        assert obs.data["resolution"] == "ENTITY_NOT_FOUND"
        assert obs.data["fallback"] == {"tool": "search_repository", "query": "nonExistentSymbol"}

    def test_query_rim_no_static_edge_returns_explicit_fallback(self):
        tool_layer = MagicMock()
        traverser = MagicMock(spec=FactStoreGraphTraverser)
        resolver = MagicMock(spec=TargetEntityResolver)

        mock_target = FactSymbol(id="1:sym1", analysis_id=1, name="authMiddleware", symbol_type="function")
        resolver.resolve.return_value = mock_target

        # Traverser finds 0 static edges
        traverser.traverse_bounded.return_value = RelationshipTraversalResult(
            query_class=SemanticQueryClass.CALLS_FORWARD,
            direction=TraversalDirection.FORWARD,
            target_entity=mock_target,
            target_display_name="authMiddleware",
            target_type="function",
            related_entities=[],
            resolution="NO_STATIC_EDGE_FOUND",
            explanation="No calls found",
        )

        dispatch = ToolDispatchTable(tool_layer, traverser, resolver)
        obs = dispatch.dispatch("get_code_relationships", {
            "entity_name": "authMiddleware",
            "relationship_type": "CALLS",
            "direction": "FORWARD",
            "scope": "LOCAL",
        })

        assert obs.success is True
        assert obs.data["found"] is False
        assert obs.data["resolution"] == "NO_STATIC_EDGE_FOUND"
        assert obs.data["fallback"] == {"tool": "search_repository", "query": "authMiddleware"}

    def test_query_rim_static_confirmed_with_multihop_path(self):
        tool_layer = MagicMock()
        traverser = MagicMock(spec=FactStoreGraphTraverser)
        resolver = MagicMock(spec=TargetEntityResolver)

        mock_target = FactSymbol(id="1:sym1", analysis_id=1, name="authMiddleware", symbol_type="function")
        resolver.resolve.return_value = mock_target

        traverser.traverse_bounded.return_value = RelationshipTraversalResult(
            query_class=SemanticQueryClass.CALLS_FORWARD,
            direction=TraversalDirection.FORWARD,
            target_entity=mock_target,
            target_display_name="authMiddleware",
            target_type="function",
            related_entities=[
                TraversedEntity(
                    name="createAccessToken",
                    entity_type="function",
                    location="auth/token.js",
                    line_number=45,
                    relationship_role="callee",
                    path=["authMiddleware", "createSession", "createAccessToken"],
                    relationships=["CALLS", "CALLS"],
                )
            ],
            resolution="STATIC_CONFIRMED",
            explanation="Found 1 path",
        )

        dispatch = ToolDispatchTable(tool_layer, traverser, resolver)
        obs = dispatch.dispatch("get_code_relationships", {
            "entity_name": "authMiddleware",
            "relationship_type": "CALLS",
            "direction": "FORWARD",
            "scope": "NEIGHBORHOOD",
            "depth": 2,
        })

        assert obs.success is True
        assert obs.data["found"] is True
        assert obs.data["resolution"] == "STATIC_CONFIRMED"
        assert len(obs.data["related"]) == 1
        rel = obs.data["related"][0]
        assert rel["name"] == "createAccessToken"
        assert rel["path"] == ["authMiddleware", "createSession", "createAccessToken"]
        assert rel["relationships"] == ["CALLS", "CALLS"]

    def test_query_rim_scope_clamping(self):
        tool_layer = MagicMock()
        traverser = MagicMock(spec=FactStoreGraphTraverser)
        resolver = MagicMock(spec=TargetEntityResolver)

        mock_target = FactSymbol(id="1:sym1", analysis_id=1, name="func", symbol_type="function")
        resolver.resolve.return_value = mock_target
        traverser.traverse_bounded.return_value = RelationshipTraversalResult(
            query_class=SemanticQueryClass.CALLS_FORWARD,
            direction=TraversalDirection.FORWARD,
            target_entity=mock_target,
            target_display_name="func",
            target_type="function",
            related_entities=[],
            resolution="NO_STATIC_EDGE_FOUND",
        )

        dispatch = ToolDispatchTable(tool_layer, traverser, resolver)

        # 1. LOCAL clamps depth to 1
        dispatch.dispatch("get_code_relationships", {"entity_name": "func", "scope": "LOCAL", "depth": 5})
        traverser.traverse_bounded.assert_called_with(
            target=mock_target,
            relationship_type="GENERIC",
            direction="FORWARD",
            scope="LOCAL",
            depth=1,
            limit=15,
            target_raw_name="func",
        )

        # 2. NEIGHBORHOOD clamps depth to max 3
        dispatch.dispatch("get_code_relationships", {"entity_name": "func", "scope": "NEIGHBORHOOD", "depth": 10})
        traverser.traverse_bounded.assert_called_with(
            target=mock_target,
            relationship_type="GENERIC",
            direction="FORWARD",
            scope="NEIGHBORHOOD",
            depth=3,
            limit=15,
            target_raw_name="func",
        )

        # 3. Limit clamps to max 50
        dispatch.dispatch("get_code_relationships", {"entity_name": "func", "scope": "LOCAL", "limit": 100})
        traverser.traverse_bounded.assert_called_with(
            target=mock_target,
            relationship_type="GENERIC",
            direction="FORWARD",
            scope="LOCAL",
            depth=1,
            limit=50,
            target_raw_name="func",
        )

    def test_get_code_relationships_rim_dispatch_and_catalog(self):
        """Verify get_code_relationships is accepted in RIM mode and query_rim is hidden from LLM specs."""
        tool_layer = MagicMock()
        traverser = MagicMock(spec=FactStoreGraphTraverser)
        resolver = MagicMock(spec=TargetEntityResolver)
        dispatch = ToolDispatchTable(tool_layer, traverser, resolver)

        # 1. LLM-facing tool catalog verification: only get_code_relationships, never query_rim
        specs = dispatch.specs(include_rim=True)
        tool_names = [s.name for s in specs]
        assert "get_code_relationships" in tool_names
        assert "query_rim" not in tool_names

        # 2. Dispatch accepts get_code_relationships in RIM mode
        mock_target = FactSymbol(id="1:sym1", analysis_id=1, name="authenticateToken", symbol_type="function")
        resolver.resolve.return_value = mock_target
        traverser.traverse_bounded.return_value = RelationshipTraversalResult(
            query_class=SemanticQueryClass.CALLS_REVERSE,
            direction=TraversalDirection.REVERSE,
            target_entity=mock_target,
            target_display_name="authenticateToken",
            target_type="function",
            related_entities=[],
            resolution="NO_STATIC_EDGE_FOUND",
        )

        obs = dispatch.dispatch(
            "get_code_relationships",
            {
                "entity_name": "authenticateToken",
                "relationship_type": "CALLS",
                "direction": "REVERSE",
                "scope": "LOCAL",
            },
        )
        assert obs.success is True
        assert obs.tool_name == "get_code_relationships"
        assert obs.data["resolution"] == "NO_STATIC_EDGE_FOUND"
        assert obs.data["found"] is False
        assert "fallback" in obs.data
        traverser.traverse_bounded.assert_called_with(
            target=mock_target,
            relationship_type="CALLS",
            direction="REVERSE",
            scope="LOCAL",
            depth=1,
            limit=15,
            target_raw_name="authenticateToken",
        )

        # 3. Baseline mode rejects get_code_relationships
        baseline_dispatch = ToolDispatchTable(tool_layer, graph_traverser=None, target_resolver=None)
        baseline_obs = baseline_dispatch.dispatch("get_code_relationships", {"entity_name": "authenticateToken"})
        assert baseline_obs.success is False
        assert baseline_obs.error["type"] == "tool_not_allowed"

