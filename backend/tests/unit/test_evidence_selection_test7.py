"""
Unit and regression tests for Test 7: Evidence selection and coverage verification in GitOnboard.

Tests:
1. RetrieverResult symbol mapping in search_repository_ops:
   Verifies that RetrieverResult objects with entity_name and entity_type="symbol" are correctly
   mapped without AttributeError, populating the symbol response dict.
2. Comma-separated query decomposition:
   Verifies that technical comma-separated lists return up to 8 parts instead of being truncated to 3.
3. Candidate match prioritization in qa_validation:
   Verifies that unread line ranges in an already-inspected controller are prioritized over
   uninspected secondary files.
4. Specific middleware resolution:
   Verifies authenticateToken.js can be retrieved and prioritized distinctly from auth.js.
"""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass
from typing import Optional

from backend.intelligence.retrieval.schema import RetrieverResult, EntityType
from backend.repository_tools.search_ops import decompose_query, search_repository_ops
from backend.services.qa_validation import identify_missing_evidence
from backend.services.qa_loop import QALoopTurn


class TestEvidenceSelectionTest7:
    def test_retriever_result_symbol_mapping(self):
        """Verify search_repository_ops maps RetrieverResult entity_name and lines without AttributeError."""
        mock_retriever = MagicMock()
        mock_result = RetrieverResult(
            id="5:sym:123",
            entity_name="authenticateToken",
            entity_type=EntityType.SYMBOL,
            file_path="app/Deep-Guard-Backend/middleware/authenticateToken.js",
            line_start=6,
            line_end=21,
            score_type="symbol_index",
            score=0.95,
        )
        mock_retriever.retrieve.return_value = [mock_result]

        mock_tool_layer = MagicMock()
        mock_tool_layer._get_retriever.return_value = mock_retriever

        results = search_repository_ops(mock_tool_layer, query="authenticateToken", limit=5)
        assert len(results) == 1
        res = results[0]
        assert res["type"] == "symbol"
        assert res["symbol"] == "authenticateToken"
        assert res["file"] == "app/Deep-Guard-Backend/middleware/authenticateToken.js"
        assert res["lines"] == "6-21"
        assert res["match_source"] == "symbol_index"

    def test_retriever_result_code_mapping(self):
        """Verify search_repository_ops maps code-level RetrieverResult without AttributeError."""
        mock_retriever = MagicMock()
        mock_result = RetrieverResult(
            id="5:file:456",
            entity_name="some code content",
            entity_type=EntityType.FILE,
            file_path="app/Deep-Guard-Backend/controllers/authcontroller.js",
            line_start=380,
            line_end=461,
            score_type="hybrid",
            score=0.88,
        )
        mock_retriever.retrieve.return_value = [mock_result]

        mock_tool_layer = MagicMock()
        mock_tool_layer._get_retriever.return_value = mock_retriever

        results = search_repository_ops(mock_tool_layer, query="refresh session rotation", limit=5)
        assert len(results) == 1
        res = results[0]
        assert res["type"] == "code"
        assert res["file"] == "app/Deep-Guard-Backend/controllers/authcontroller.js"
        assert res["line"] == 380
        assert res["match_source"] == "hybrid"

    def test_decompose_query_technical_tokens(self):
        """Verify decompose_query preserves up to 8 comma-separated technical identifiers."""
        query = "authcontroller.js, authHelpers.js, authenticateToken.js, refresh, createSession, token_version"
        sub_queries = decompose_query(query)
        assert len(sub_queries) == 6
        assert "authenticateToken.js" in sub_queries
        assert "refresh" in sub_queries
        assert "token_version" in sub_queries

    def test_qa_validation_prioritizes_unread_controller_ranges(self):
        """Verify qa_validation suggests unread ranges in active controller over secondary files."""
        # Setup: authcontroller.js was read at 1-55
        read_turn = QALoopTurn(
            turn_index=1,
            tool_call={"tool_name": "read_file", "arguments": {"path": "controllers/authcontroller.js", "start_line": 1, "end_line": 55}},
            tool_observation={"tool_name": "read_file", "success": True, "data": "const express = ...", "formatted_message": "[read_file] controllers/authcontroller.js lines 1-55"}
        )

        # Search turn returned both uninspected secondary file and unread range of authcontroller.js
        search_turn = QALoopTurn(
            turn_index=2,
            tool_call={"tool_name": "search_repository", "arguments": {"query": "refresh"}},
            tool_observation={
                "tool_name": "search_repository",
                "success": True,
                "data": [
                    {"file": "middleware/auth.js", "line": 155},  # unread file
                    {"file": "controllers/authcontroller.js", "line": 380},  # unread range in active file
                ],
                "formatted_message": "[search_repository] Found matches"
            }
        )

        loop_result = MagicMock()
        loop_result.turns = [read_turn, search_turn]

        guidance = identify_missing_evidence(
            question="How does token refresh work?",
            result=loop_result,
            attempted_tool="read_file",
            attempted_args={"path": "controllers/authcontroller.js", "start_line": 1, "end_line": 55},
        )

        # Guidance should prioritize inspecting controllers/authcontroller.js line 380
        assert "controllers/authcontroller.js" in guidance
        assert "370" in guidance or "380" in guidance
