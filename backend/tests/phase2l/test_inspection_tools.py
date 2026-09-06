"""
Unit tests for inspection tools (Phase 2L).

Tests for repository tools:
- inspect_file (list symbols without source)
- inspect_symbol (get metadata only)
- read_symbol (get exact boundaries)
- read_lines (validate range)
- read_file (complete content)
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.repository_tools.tools import RepositoryToolLayer
from backend.repository_tools.security import RepositorySecurityError


class TestRepositoryToolLayerReadFile:
    """Tests for read_file method."""

    def test_read_file_basic(self, temp_test_file):
        """Verify read_file returns file content with line numbers."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        result = tool.read_file(str(temp_test_file.name))

        assert result["path"] == str(temp_test_file.name)
        assert result["start_line"] == 1
        assert result["end_line"] > 0
        assert "content" in result
        assert "raw_text" in result
        assert result["total_lines"] > 0

    def test_read_file_partial_range(self, temp_test_file):
        """Verify read_file respects line range."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        result = tool.read_file(str(temp_test_file.name), start_line=5, end_line=10)

        assert result["start_line"] == 5
        assert result["end_line"] <= result["total_lines"]

    def test_read_file_complete_content(self, temp_test_file):
        """Verify read_file returns complete content without truncation."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        result = tool.read_file(str(temp_test_file.name))

        # Content should not be truncated
        assert len(result["content"]) > 0
        assert result["raw_text"] is not None

    def test_read_file_line_numbering(self, temp_test_file):
        """Verify line numbers are correct in output."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        result = tool.read_file(str(temp_test_file.name), start_line=1, end_line=5)

        # Each line should have proper numbering format
        lines = result["content"].split("\n")
        # First line should start with "   1 |"
        assert any("1 |" in line for line in lines if line)

    def test_read_file_clamping(self, temp_test_file):
        """Verify line ranges are clamped to file bounds."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        # Request lines beyond file
        result = tool.read_file(
            str(temp_test_file.name),
            start_line=1,
            end_line=9999
        )

        # Should clamp to actual total
        assert result["end_line"] <= result["total_lines"]

    def test_read_file_nonexistent_raises_error(self, temp_test_file):
        """Verify reading nonexistent file raises error."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        with pytest.raises((RepositorySecurityError, FileNotFoundError)):
            tool.read_file("nonexistent_file.py")


class TestRepositoryToolLayerFindFiles:
    """Tests for find_files method."""

    def test_find_files_basic_pattern(self, temp_test_file):
        """Verify find_files returns matching files."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results = tool.find_files("*.py")

        assert len(results) > 0
        assert any(temp_test_file.name in r["path"] for r in results)

    def test_find_files_no_matches(self, temp_test_file):
        """Verify find_files returns empty list for no matches."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results = tool.find_files("*.nonexistent")

        assert results == []

    def test_find_files_respects_limit(self, temp_test_file):
        """Verify find_files respects result limit."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results = tool.find_files("*.py", limit=1)

        assert len(results) <= 1

    def test_find_files_includes_metadata(self, temp_test_file):
        """Verify find_files includes file metadata."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results = tool.find_files("*.py")

        if results:
            result = results[0]
            assert "path" in result
            assert "size" in result
            # May have additional metadata like is_binary
            assert result["size"] >= 0


class TestRepositoryToolLayerSearchCode:
    """Tests for search_code method."""

    def test_search_code_basic(self, temp_test_file):
        """Verify search_code finds matching text."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results = tool.search_code("def ", file_pattern="*.py")

        assert len(results) > 0
        assert all("def" in r["snippet"].lower() for r in results)

    def test_search_code_no_matches(self, temp_test_file):
        """Verify search_code returns empty for no matches."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results = tool.search_code("NONEXISTENT_UNIQUE_STRING_XYZ")

        assert results == []

    def test_search_code_respects_limit(self, temp_test_file):
        """Verify search_code respects max_matches."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results = tool.search_code("a", max_matches=1)

        # Should stop at limit
        assert len(results) <= 1

    def test_search_code_includes_metadata(self, temp_test_file):
        """Verify search_code results include metadata."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results = tool.search_code("def ", file_pattern="*.py")

        if results:
            result = results[0]
            assert "file" in result
            assert "line" in result
            assert "snippet" in result
            assert "match_type" in result

    def test_search_code_case_insensitive(self, temp_test_file):
        """Verify search_code is case-insensitive."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        results_lower = tool.search_code("def ")
        results_upper = tool.search_code("DEF ")

        assert len(results_lower) == len(results_upper)

    def test_search_code_regex_pattern(self, temp_test_file):
        """Verify search_code supports regex patterns."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        # Search for function definitions with any name
        results = tool.search_code(r"def \w+\(")

        assert len(results) > 0


class TestRepositoryToolLayerGetSymbol:
    """Tests for get_symbol method."""

    def test_get_symbol_returns_list(self, mock_db_session):
        """Verify get_symbol returns list even with no DB."""
        tool = RepositoryToolLayer(
            repo_name="test",
            db=None,
            analysis_id=None
        )

        results = tool.get_symbol("test_symbol")

        assert isinstance(results, list)
        assert len(results) == 0  # No DB, empty results

    def test_get_symbol_requires_analysis_id(self):
        """Verify get_symbol requires DB and analysis_id."""
        mock_db = MagicMock()
        tool = RepositoryToolLayer(
            repo_name="test",
            db=mock_db,
            analysis_id=None  # Missing analysis ID
        )

        results = tool.get_symbol("test_symbol")

        assert results == []


class TestRepositoryToolLayerGetFileOutline:
    """Tests for get_file_outline method."""

    def test_get_file_outline_structure(self):
        """Verify get_file_outline returns structured outline."""
        mock_db = MagicMock()
        tool = RepositoryToolLayer(
            repo_name="test",
            db=mock_db,
            analysis_id=None
        )

        result = tool.get_file_outline("test.py")

        assert isinstance(result, dict)
        assert "file" in result
        assert "symbols" in result
        assert isinstance(result["symbols"], list)

    def test_get_file_outline_requires_analysis_id(self):
        """Verify get_file_outline returns empty outline without DB."""
        tool = RepositoryToolLayer(
            repo_name="test",
            db=None,
            analysis_id=None
        )

        result = tool.get_file_outline("test.py")

        assert result["file"] == "test.py"
        assert result["symbols"] == []


class TestRepositoryToolLayerCallGraph:
    """Tests for call graph methods (get_callers, get_callees)."""

    def test_get_callers_requires_db(self):
        """Verify get_callers requires DB."""
        tool = RepositoryToolLayer(
            repo_name="test",
            db=None,
            analysis_id=None
        )

        results = tool.get_callers("test_symbol")

        assert results == []

    def test_get_callees_requires_db(self):
        """Verify get_callees requires DB."""
        tool = RepositoryToolLayer(
            repo_name="test",
            db=None,
            analysis_id=None
        )

        results = tool.get_callees("test_symbol")

        assert results == []

    def test_get_callers_returns_list(self):
        """Verify get_callers returns list."""
        mock_db = MagicMock()
        tool = RepositoryToolLayer(
            repo_name="test",
            db=mock_db,
            analysis_id=None
        )

        results = tool.get_callers("test_symbol")

        assert isinstance(results, list)

    def test_get_callees_returns_list(self):
        """Verify get_callees returns list."""
        mock_db = MagicMock()
        tool = RepositoryToolLayer(
            repo_name="test",
            db=mock_db,
            analysis_id=None
        )

        results = tool.get_callees("test_symbol")

        assert isinstance(results, list)


class TestRepositoryToolLayerPathValidation:
    """Tests for path validation and security."""

    def test_read_file_path_validation(self, temp_test_file):
        """Verify read_file validates paths."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        # Normal path should work
        result = tool.read_file(str(temp_test_file.name))
        assert result is not None

    def test_read_file_path_traversal_blocked(self, temp_test_file):
        """Verify path traversal is blocked."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        # Attempt path traversal
        with pytest.raises(RepositorySecurityError):
            tool.read_file("../../../etc/passwd")

    def test_find_files_ignores_common_dirs(self, temp_test_file):
        """Verify find_files ignores common directories."""
        tool = RepositoryToolLayer(
            repo_name="test",
            repo_root=temp_test_file.parent
        )

        # Should not scan these directories
        results = tool.find_files("*", limit=1000)

        paths = [r["path"] for r in results]
        assert not any(".git" in p for p in paths)
        assert not any("__pycache__" in p for p in paths)
        assert not any("node_modules" in p for p in paths)
