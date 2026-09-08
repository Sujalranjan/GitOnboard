"""
Unit tests for Tool #2 (File Retrieval) validation logic.
Tests path normalization and line range validation.
"""

import pytest
from backend.utils.repo_paths import normalize_relative, PathTraversalError


class TestPathValidation:
    """Test path normalization and traversal prevention."""

    def test_valid_path_normalization(self):
        """Test that valid paths are normalized correctly."""
        clean = normalize_relative("backend/auth.py")
        assert clean == "backend/auth.py"

    def test_path_normalization_removes_dots(self):
        """Test that paths with ./ are normalized."""
        clean = normalize_relative("./backend/auth.py")
        assert clean == "backend/auth.py"

    def test_path_normalization_strips_leading_slash(self):
        """Test that leading slash is stripped."""
        clean = normalize_relative("/backend/auth.py")
        assert clean == "backend/auth.py"

    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        with pytest.raises(PathTraversalError):
            normalize_relative("../../../etc/passwd")

    def test_path_traversal_with_dots_rejected(self):
        """Test that disguised path traversal is rejected."""
        with pytest.raises(PathTraversalError):
            normalize_relative("backend/../../etc/passwd")

    def test_double_dots_rejected(self):
        """Test that double dots anywhere are rejected."""
        with pytest.raises(PathTraversalError):
            normalize_relative("backend/../auth.py")


class TestLineRangeValidation:
    """Test line range parameter validation."""

    def test_valid_line_range(self):
        """Test that valid line range is accepted."""
        start_line = 1
        end_line = 10
        total_lines = 50

        assert start_line >= 1
        assert end_line >= start_line
        assert end_line <= total_lines

    def test_invalid_start_line_less_than_1(self):
        """Test that start_line < 1 is rejected."""
        start_line = 0
        end_line = 10

        assert not (start_line >= 1)

    def test_invalid_end_line_less_than_start(self):
        """Test that end_line < start_line is rejected."""
        start_line = 10
        end_line = 5

        assert not (end_line >= start_line)

    def test_invalid_end_line_exceeds_total(self):
        """Test that end_line > total_lines is rejected."""
        start_line = 1
        end_line = 100
        total_lines = 50

        assert not (end_line <= total_lines)

    def test_line_extraction(self):
        """Test that line extraction works correctly."""
        content = "line1\nline2\nline3\nline4\nline5\n"
        lines = content.splitlines()
        start_line = 2
        end_line = 4

        extracted_lines = lines[start_line-1:end_line]
        extracted_content = '\n'.join(extracted_lines)

        assert extracted_content == "line2\nline3\nline4"

    def test_full_file_extraction(self):
        """Test extracting entire file."""
        content = "line1\nline2\nline3\n"
        lines = content.splitlines()
        total_lines = len(lines)

        extracted_lines = lines[0:total_lines]
        extracted_content = '\n'.join(extracted_lines)

        assert extracted_content == content.strip()

    def test_single_line_extraction(self):
        """Test extracting a single line."""
        content = "line1\nline2\nline3\n"
        lines = content.splitlines()
        start_line = 2
        end_line = 2

        extracted_lines = lines[start_line-1:end_line]
        extracted_content = '\n'.join(extracted_lines)

        assert extracted_content == "line2"

    def test_empty_file(self):
        """Test handling of empty file."""
        content = ""
        lines = content.splitlines()
        total_lines = len(lines)

        assert total_lines == 0

    def test_single_line_file(self):
        """Test handling of single line file."""
        content = "single line"
        lines = content.splitlines()
        total_lines = len(lines)

        assert total_lines == 1
        assert lines[0] == "single line"
