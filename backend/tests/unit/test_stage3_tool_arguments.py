"""
Tests for Stage 3: Improve Tool Selection and Arguments.
Covers:
1. Oversized read_file line ranges (>250 lines) are clamped safely to 250 lines with transparent notice.
2. Invalid and boundary line-range arguments (inverted range start > end swapped, start_line > total_lines handled cleanly).
3. Large-file retrieval using get_file_outline and context_overflow_protection on unbounded reads (>150 lines).
4. Direct file reads when within safe limits (no false positive error).
5. Notebook code-cell search when searching with pattern="*.py" and pattern="*.ipynb".
6. Existing search behavior for ordinary source files.
7. Tool dispatch and error handling after argument validation.
8. Regression check: Stage 1 final-answer parsing.
9. Regression check: Stage 2 duplicate prevention and legitimate retries.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock

from backend.repository_tools.tools import RepositoryToolLayer
from backend.services.tool_dispatch import ToolDispatchTable, ToolSpec
from backend.services.qa_protocol import QAProtocolAdapter
from backend.agent.loop.guardrails import LoopGuardrails
from backend.agent.loop.contracts import AgentLoopConfig
from backend.storage.memory import InMemoryObjectStorage
from backend.storage import set_storage
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol


@pytest.fixture
def mock_storage_and_tool_layer():
    mem_storage = InMemoryObjectStorage()
    set_storage(mem_storage)

    # 400 lines content
    file_content = "\n".join([f"line_{i} = {i}" for i in range(1, 401)])
    mem_storage.put_object("repositories/mock-hash/snapshots/snap1/big_service.py", file_content)

    # Small file (50 lines)
    small_content = "\n".join([f"small_{i} = {i}" for i in range(1, 51)])
    mem_storage.put_object("repositories/mock-hash/snapshots/snap1/small_service.py", small_content)

    class MockAnalysis:
        id = 1
        repository_id = 1

    class MockRepo:
        id = 1
        repository_hash = "mock-hash"

    class MockDB:
        def query(self, model):
            class MockQuery:
                def filter(self, *args):
                    return self
                def first(self):
                    if model == MockAnalysis or getattr(model, "__name__", "") == "Analysis":
                        return MockAnalysis()
                    return MockRepo()
                def join(self, *args):
                    return self
                def order_by(self, *args):
                    return self
                def all(self):
                    return []
            return MockQuery()

    tool_layer = RepositoryToolLayer("mock-repo", analysis_id=1, db=MockDB(), user_id=1)
    return tool_layer


def test_oversized_read_file_clamped(mock_storage_and_tool_layer):
    """Test 1: Requests spanning >250 lines are clamped to 250 lines with transparent notice."""
    tool_layer = mock_storage_and_tool_layer
    # Provide sufficient token budget (e.g. 5000 tokens) so truncation doesn't clamp before the 250 safe line limit
    res = tool_layer.read_file("big_service.py", start_line=1, end_line=350, max_content_tokens=5000)

    assert "error" not in res
    assert res["start_line"] == 1
    assert res["end_line"] == 250
    assert res["requested_start_line"] == 1
    assert res["requested_end_line"] == 350
    assert res["total_lines"] == 400
    assert res["is_truncated"] is True
    assert res["next_start_line"] == 251
    assert res["remaining_lines"] == 100
    assert "[Notice: Requested range 1-350 exceeds safe limit of 250 lines; clamped to lines 1-250." in res["content"]
    assert "start_line=251, end_line=350" in res["content"]


def test_inverted_and_boundary_line_ranges(mock_storage_and_tool_layer):
    """Test 2: Inverted line range is safely swapped, and start_line > total_lines returns clean error."""
    tool_layer = mock_storage_and_tool_layer

    # Inverted range: start=50, end=10 -> swapped to 10-50
    res_swapped = tool_layer.read_file("big_service.py", start_line=50, end_line=10)
    assert "error" not in res_swapped
    assert res_swapped["start_line"] == 10
    assert res_swapped["end_line"] == 50

    # Start line exceeding total lines: clean error dict without crash
    res_out = tool_layer.read_file("big_service.py", start_line=999, end_line=1050)
    assert res_out["error"] == "invalid_range"
    assert "exceeds total file lines" in res_out["message"]


def test_unbounded_read_protection_on_large_file(mock_storage_and_tool_layer):
    """Test 3: Unbounded read on large file (>150 lines) is intercepted with context_overflow_protection."""
    tool_layer = mock_storage_and_tool_layer
    res = tool_layer.read_file("big_service.py")
    assert res["error"] == "context_overflow_protection"
    assert "Refusing full file read" in res["message"]
    assert "get_file_outline" in res["message"]


def test_direct_read_on_small_file_allowed(mock_storage_and_tool_layer):
    """Test 4: Small file (<150 lines) or bounded read works directly without error."""
    tool_layer = mock_storage_and_tool_layer
    res = tool_layer.read_file("small_service.py")
    assert "error" not in res
    assert res["total_lines"] == 50
    assert res["start_line"] == 1
    assert res["end_line"] == 50
    assert "small_1 = 1" in res["content"]


def test_notebook_search_with_python_filter(tmp_path):
    """Test 5 & 6: search_code with file_pattern='*.py' also searches .ipynb cells, and searches normal .py files."""
    from backend.repository_tools.tools import RepositoryToolLayer

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    # Create normal python file
    py_file = repo_root / "normal.py"
    py_file.write_text("def auth_handler():\n    return 'secret_token'\n", encoding="utf-8")

    # Create notebook file with Qdrant client in code cell
    nb_content = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from qdrant_client import QdrantClient\n",
                    "client = QdrantClient(host='localhost')\n",
                ],
            }
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 2,
    }
    nb_file = repo_root / "pipeline.ipynb"
    nb_file.write_text(json.dumps(nb_content), encoding="utf-8")

    tool_layer = RepositoryToolLayer(
        repo_name="test_nb_search",
        analysis_id=None,
        db=None,
        repo_root=str(repo_root),
    )

    # 1. Search normal python code with *.py pattern
    matches_normal = tool_layer.search_code("auth_handler", file_pattern="*.py")
    assert len(matches_normal) >= 1
    assert matches_normal[0]["file"] == "normal.py"

    # 2. Search notebook code when file_pattern is *.py (Crucial Stage 3 improvement!)
    matches_nb = tool_layer.search_code("QdrantClient", file_pattern="*.py")
    assert len(matches_nb) >= 1
    assert matches_nb[0]["file"] == "pipeline.ipynb"
    assert "QdrantClient" in matches_nb[0]["snippet"]

    # 3. Direct *.ipynb pattern also works
    matches_nb_direct = tool_layer.search_code("QdrantClient", file_pattern="*.ipynb")
    assert len(matches_nb_direct) >= 1
    assert matches_nb_direct[0]["file"] == "pipeline.ipynb"


def test_tool_dispatcher_error_handling(mock_storage_and_tool_layer):
    """Test 7: Tool dispatcher converts tool error dicts into ToolObservation with success=False."""
    tool_layer = mock_storage_and_tool_layer
    dispatcher = ToolDispatchTable(tool_layer)

    # Dispatch unbounded read on 400-line file
    obs = dispatcher.dispatch("read_file", {"path": "big_service.py"})
    assert obs.success is False
    assert obs.error["type"] == "context_overflow_protection"
    assert "Refusing full file read" in obs.error["message"]


def test_regression_stage1_and_stage2():
    """Test 8 & 9: Regression test ensuring Stage 1 final-answer parsing and Stage 2 duplicate detection remain intact."""
    # Stage 1: parse_final_synthesis with clean markdown and JSON envelope extraction
    adapter = QAProtocolAdapter(model_id="qwen2.5:7b-instruct", native_tools=False)
    raw_markdown = "### Authentication Flow\nAuthentication uses JWT."
    parsed = adapter.parse_final_synthesis(raw_markdown)
    assert parsed == "### Authentication Flow\nAuthentication uses JWT."

    raw_json = '{"action": "final_answer", "answer": "The database uses PostgreSQL."}'
    parsed_json = adapter.parse_final_synthesis(raw_json)
    assert parsed_json == "The database uses PostgreSQL."

    # Stage 2: duplicate detection
    guardrails = LoopGuardrails(AgentLoopConfig(max_duplicate_tool_calls=1))
    is_dup, _ = guardrails.is_duplicate_call("read_file", {"path": "app.py", "start_line": 1, "end_line": 50})
    assert is_dup is False

    guardrails.record_tool_result(
        "read_file",
        {"path": "app.py", "start_line": 1, "end_line": 50},
        success=True,
        data={"content": "import sys\nprint('hello')"},
    )
    is_dup2, feedback = guardrails.is_duplicate_call("read_file", {"end_line": 50, "path": "app.py", "start_line": 1})
    assert is_dup2 is True
    assert "[DUPLICATE TOOL CALL]" in feedback


def test_read_file_with_symbol_resolves_range_on_large_file(mock_storage_and_tool_layer):
    """
    Test P0: read_file(symbol=...) resolves symbol BEFORE context-overflow validation.
    Even on a 400-line file where unbounded read is refused,
    specifying a symbol (e.g. function defined in lines 120-140) resolves the line boundaries
    and returns only that symbol without triggering context_overflow_protection.
    """
    tool_layer = mock_storage_and_tool_layer

    # Add a function definition inside big_service.py content (lines 120-130)
    lines = [f"line_{i} = {i}" for i in range(1, 401)]
    lines[120] = "function getDeviceFingerprint() {"
    lines[125] = "    return 'fingerprint';"
    lines[129] = "}"
    from backend.storage import get_storage
    get_storage().put_object("repositories/mock-hash/snapshots/snap1/big_service.py", "\n".join(lines))

    # Call read_file on 400-line file with symbol="getDeviceFingerprint" and no start/end lines
    res = tool_layer.read_file("big_service.py", symbol="getDeviceFingerprint")

    assert "error" not in res
    assert res["start_line"] == 121
    assert res["end_line"] >= 130
    assert "getDeviceFingerprint" in res["content"]
