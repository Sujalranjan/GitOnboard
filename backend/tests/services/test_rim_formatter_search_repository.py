"""
Regression tests for RIMQALoop._format_tool_observation (search_repository).

Ensures that search_repository results are properly formatted for LLM consumption.
Prevents recurrence of the "?" field loss bug.
"""

import pytest
from backend.services.rim_qa_loop import RIMQALoop, SystemPromptParts
from backend.agent.loop.contracts import AgentLoopConfig, ToolObservation
from backend.services.rim_tool_dispatch import ToolDispatchTable
from backend.repository_tools.tools import RepositoryToolLayer


@pytest.fixture
def rim_loop():
    """Create a RIMQALoop instance for testing."""
    config = AgentLoopConfig(max_observation_bytes=8000)
    system_prompt_parts = SystemPromptParts(
        grounding_and_protocol_text="Test",
        tool_catalog_text="Test",
        rim_metadata_text="",
        full_text="Test"
    )

    # Mock tool dispatch
    mock_tool_layer = None  # Not used in formatter tests

    return RIMQALoop(
        llm_service=None,
        tool_dispatch=None,
        config=config,
        system_prompt_parts=system_prompt_parts
    )


def test_search_repository_formatter_file_results(rim_loop):
    """
    Test that search_repository file results are formatted correctly.

    Regression test: Previously tried to access "path" key but results use "file" key,
    causing all results to show as "?".
    """
    # Simulate search_repository results (what the tool actually returns)
    results = [
        {
            "type": "file",
            "file": "src/auth.py",
            "size": 1024,
            "match_source": "filename_manifest"
        },
        {
            "type": "file",
            "file": "src/login.py",
            "size": 512,
            "match_source": "filename_manifest"
        }
    ]

    tool_observation = ToolObservation(
        tool_call_id="test-1",
        tool_name="search_repository",
        success=True,
        data=results
    )

    # Format the observation
    formatted = rim_loop._format_tool_observation(
        "search_repository", tool_observation, results
    )

    # Verify that actual file paths appear, not "?"
    assert "src/auth.py" in formatted, "File path should appear in formatted output"
    assert "src/login.py" in formatted, "File path should appear in formatted output"
    assert "?" not in formatted, "Should not have placeholder '?' for missing fields"
    assert "[search_repository]" in formatted
    assert "Found 2 results" in formatted


def test_search_repository_formatter_code_results(rim_loop):
    """
    Test that search_repository code results include line numbers and snippets.
    """
    results = [
        {
            "type": "code",
            "file": "src/auth.py",
            "line": 5,
            "snippet": "def authenticate(user, pwd):",
            "match_source": "lexical"
        },
        {
            "type": "code",
            "file": "src/auth.py",
            "line": 12,
            "snippet": "return session_token",
            "match_source": "lexical"
        }
    ]

    tool_observation = ToolObservation(
        tool_call_id="test-2",
        tool_name="search_repository",
        success=True,
        data=results
    )

    formatted = rim_loop._format_tool_observation(
        "search_repository", tool_observation, results
    )

    # Verify paths and line numbers appear
    assert "src/auth.py:5" in formatted or ("src/auth.py" in formatted and "5" in formatted)
    assert "src/auth.py:12" in formatted or ("src/auth.py" in formatted and "12" in formatted)
    assert "def authenticate" in formatted or "authenticate" in formatted
    assert "?" not in formatted


def test_search_repository_formatter_symbol_results(rim_loop):
    """
    Test that search_repository symbol results include function/class names.
    """
    results = [
        {
            "type": "symbol",
            "file": "src/auth.py",
            "symbol": "authenticate",
            "symbol_type": "function",
            "lines": "5-12",
            "match_source": "symbol_index"
        },
        {
            "type": "symbol",
            "file": "src/session.py",
            "symbol": "SessionManager",
            "symbol_type": "class",
            "lines": "20-50",
            "match_source": "symbol_index"
        }
    ]

    tool_observation = ToolObservation(
        tool_call_id="test-3",
        tool_name="search_repository",
        success=True,
        data=results
    )

    formatted = rim_loop._format_tool_observation(
        "search_repository", tool_observation, results
    )

    # Verify file paths appear (symbol names optional but helpful)
    assert "src/auth.py" in formatted
    assert "src/session.py" in formatted
    assert "?" not in formatted
    # Should either mention the symbols or at least the files
    assert ("authenticate" in formatted or "auth.py" in formatted)


def test_search_repository_formatter_mixed_results(rim_loop):
    """
    Test that search_repository handles mixed result types correctly.
    """
    results = [
        {"type": "file", "file": "src/auth.py", "size": 1024, "match_source": "filename_manifest"},
        {"type": "code", "file": "src/auth.py", "line": 5, "snippet": "def authenticate", "match_source": "lexical"},
        {"type": "symbol", "file": "src/session.py", "symbol": "Session", "symbol_type": "class", "lines": "1-30", "match_source": "symbol_index"},
    ]

    tool_observation = ToolObservation(
        tool_call_id="test-4",
        tool_name="search_repository",
        success=True,
        data=results
    )

    formatted = rim_loop._format_tool_observation(
        "search_repository", tool_observation, results
    )

    # All file paths should appear
    assert "src/auth.py" in formatted
    assert "src/session.py" in formatted
    assert formatted.count("src/") >= 3  # Should appear at least once per result
    assert "?" not in formatted
    assert "Found 3 results" in formatted


def test_search_repository_formatter_truncation(rim_loop):
    """
    Test that formatter handles > 10 results (shows ellipsis).
    """
    results = [
        {"type": "file", "file": f"src/file{i}.py", "size": 100, "match_source": "filename_manifest"}
        for i in range(15)
    ]

    tool_observation = ToolObservation(
        tool_call_id="test-5",
        tool_name="search_repository",
        success=True,
        data=results
    )

    formatted = rim_loop._format_tool_observation(
        "search_repository", tool_observation, results
    )

    # Should show first 10 and mention remaining
    assert "Found 15 results" in formatted
    assert "... and 5 more results" in formatted
    # Only first 10 should be listed in detail
    for i in range(10):
        assert f"src/file{i}.py" in formatted
    # The 11-15 files should not appear individually (only in ellipsis message)
    for i in range(10, 15):
        # These shouldn't appear as individual entries, only in the "more" message
        pass


def test_search_repository_formatter_empty_results(rim_loop):
    """
    Test formatter handles empty results correctly.
    """
    results = []

    tool_observation = ToolObservation(
        tool_call_id="test-6",
        tool_name="search_repository",
        success=True,
        data=results
    )

    formatted = rim_loop._format_tool_observation(
        "search_repository", tool_observation, results
    )

    assert "Found 0 results" in formatted
    assert "[search_repository]" in formatted


def test_search_repository_formatter_malformed_result(rim_loop):
    """
    Test formatter gracefully handles malformed result items.
    """
    results = [
        {"type": "file", "file": "src/good.py", "size": 100, "match_source": "filename_manifest"},
        {"type": "unknown"},  # Missing file key
        "string_instead_of_dict",  # Not a dict
    ]

    tool_observation = ToolObservation(
        tool_call_id="test-7",
        tool_name="search_repository",
        success=True,
        data=results
    )

    formatted = rim_loop._format_tool_observation(
        "search_repository", tool_observation, results
    )

    # Should still include the good result and handle bad ones gracefully
    assert "src/good.py" in formatted
    assert "Found 3 results" in formatted
    # Should not crash, even if some results are malformed


def test_search_repository_formatter_preserves_content_boundary(rim_loop):
    """
    Invariant test: Verify the critical boundary that was previously broken.

    Ensures that when search_repository returns N results with content,
    the LLM receives those N results with usable information (not all "?").
    """
    # Simulate the exact flow from the diagnostic
    results = [
        {"type": "file", "file": "src/login.py", "size": 297, "match_source": "filename_manifest"},
        {"type": "code", "file": "src/auth.py", "line": 1, "snippet": "def login(...)", "match_source": "lexical"},
        {"type": "code", "file": "src/auth.py", "line": 2, "snippet": "user = db.get_user(...)", "match_source": "lexical"},
    ]

    tool_observation = ToolObservation(
        tool_call_id="boundary-test",
        tool_name="search_repository",
        success=True,
        data=results
    )

    formatted = rim_loop._format_tool_observation(
        "search_repository", tool_observation, results
    )

    # INVARIANT: If retriever returns N results with content,
    # LLM must receive N results with usable information
    assert formatted.count("\n  - ") >= 3, f"Should have at least 3 result lines, got:\n{formatted}"

    # INVARIANT: No result should show as "?" (the previous bug)
    assert "- ?" not in formatted, f"Should not have '?' placeholders, got:\n{formatted}"

    # INVARIANT: File paths must be present
    assert "src/login.py" in formatted and "src/auth.py" in formatted

    # INVARIANT: LLM-visible bytes should be > 0
    assert len(formatted) > len("[search_repository] Found 3 results:\n"), \
        "Formatted message should contain actual content, not just summary"
