"""
Unit tests for Phase 2L inspection tools.
Tests symbol boundary validation, language detection, token estimation.
"""
import pytest
from pathlib import Path
from sqlalchemy.orm import Session

from backend.intelligence.inspection import (
    inspect_file,
    inspect_symbol,
    read_symbol,
    read_lines,
    read_file,
)
from backend.intelligence.inspection.utils import (
    detect_language,
    estimate_tokens,
    calculate_file_size_kb,
    number_source_lines,
)


class TestLanguageDetection:
    """Test language detection from file extensions."""

    def test_python_detection(self):
        """Python files should detect as 'python'."""
        assert detect_language("main.py") == "python"
        assert detect_language("backend/app.py") == "python"

    def test_javascript_detection(self):
        """JavaScript files should detect as 'javascript'."""
        assert detect_language("index.js") == "javascript"
        assert detect_language("frontend/utils.js") == "javascript"

    def test_typescript_detection(self):
        """TypeScript files should detect as 'typescript'."""
        assert detect_language("main.ts") == "typescript"
        assert detect_language("app/component.ts") == "typescript"

    def test_jsx_detection(self):
        """JSX files should detect as 'jsx'."""
        assert detect_language("Component.jsx") == "jsx"
        assert detect_language("src/components.jsx") == "jsx"

    def test_tsx_detection(self):
        """TSX files should detect as 'tsx'."""
        assert detect_language("Component.tsx") == "tsx"
        assert detect_language("src/components.tsx") == "tsx"

    def test_unknown_detection(self):
        """Unknown extensions should return 'unknown'."""
        assert detect_language("README.md") == "unknown"
        assert detect_language("config.yaml") == "unknown"


class TestTokenEstimation:
    """Test token counting and estimation."""

    def test_empty_text(self):
        """Empty text should return 1 token minimum."""
        assert estimate_tokens("") >= 1

    def test_approximate_tokens(self):
        """Rough approximation: ~4 chars per token."""
        text = "a" * 100
        tokens = estimate_tokens(text)
        # Should be approximately 100/4 = 25
        assert 20 <= tokens <= 30

    def test_code_tokens(self):
        """Estimate tokens for real code."""
        code = """
def hello():
    print("hello world")
"""
        tokens = estimate_tokens(code)
        assert tokens > 0


class TestFileSizeCalculation:
    """Test file size conversion."""

    def test_bytes_to_kb(self):
        """1024 bytes should be 1.0 KB."""
        assert calculate_file_size_kb(1024) == 1.0

    def test_large_file_size(self):
        """50000 bytes should be 48.8 KB."""
        result = calculate_file_size_kb(50000)
        assert 48.0 <= result <= 49.0

    def test_zero_bytes(self):
        """0 bytes should be 0.0 KB."""
        assert calculate_file_size_kb(0) == 0.0


class TestLineNumbering:
    """Test source line numbering."""

    def test_single_line(self):
        """Single line should format correctly."""
        result = number_source_lines("hello", start_line=1)
        assert "1 | hello" in result

    def test_multiple_lines(self):
        """Multiple lines should format with correct padding."""
        result = number_source_lines("line1\nline2\nline3", start_line=1)
        assert "1 | line1" in result
        assert "2 | line2" in result
        assert "3 | line3" in result

    def test_padding_width(self):
        """Line numbers should be right-aligned."""
        text = "\n".join([f"line {i}" for i in range(1, 101)])
        result = number_source_lines(text, start_line=1)
        lines = result.split("\n")
        # With 100 lines, each line number should be 3 chars wide
        # E.g. "  1 | line 1", " 99 | line 99", "100 | line 100"
        assert any("100 |" in line for line in lines)

    def test_offset_start_line(self):
        """Should use correct starting line number."""
        result = number_source_lines("hello\nworld", start_line=42)
        lines = result.strip().split("\n")
        assert "42 |" in lines[0]
        assert "43 |" in lines[1]


class TestInspectFileBasic:
    """Basic tests for inspect_file() with filesystem fallback."""

    def test_inspect_file_no_db(self, tmp_path):
        """inspect_file should work without database."""
        # Create a test Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        result = inspect_file(
            file_path="test.py",
            repo_root=str(tmp_path),
        )

        assert result.success is True
        assert result.file_path == "test.py"
        assert result.language == "python"
        assert result.total_lines == 2


class TestReadLinesValidation:
    """Test read_lines() validation."""

    def test_invalid_line_numbers(self, tmp_path):
        """Should reject invalid line numbers."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        # start_line < 1 should fail
        result = read_lines(
            file_path="test.py",
            start_line=0,
            end_line=2,
            repo_root=str(tmp_path),
        )
        assert result.success is False
        assert "Invalid line numbers" in result.error

        # start_line > end_line should fail
        result = read_lines(
            file_path="test.py",
            start_line=2,
            end_line=1,
            repo_root=str(tmp_path),
        )
        assert result.success is False
        assert "Invalid line range" in result.error


class TestReadFileWarning:
    """Test read_file() warns on large files."""

    def test_small_file_no_warning(self, tmp_path):
        """Small files should read without warning."""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n" * 10)

        result = read_file(
            file_path="test.py",
            repo_root=str(tmp_path),
        )

        assert result.success is True
        assert result.warning is None


class TestLanguageSupport:
    """Test all supported languages."""

    @pytest.mark.parametrize("ext,expected_lang", [
        (".py", "python"),
        (".js", "javascript"),
        (".ts", "typescript"),
        (".jsx", "jsx"),
        (".tsx", "tsx"),
    ])
    def test_supported_language(self, ext, expected_lang):
        """All supported languages should detect correctly."""
        filename = f"test{ext}"
        assert detect_language(filename) == expected_lang


class TestSymbolBoundaryValidation:
    """
    Tests for symbol boundary validation.
    Agent 4 will use these patterns for comprehensive validation.
    """

    def test_symbol_boundary_format(self):
        """Symbol boundaries should be integers."""
        # This is a contract test - symbol boundaries must be ints
        from backend.intelligence.inspection.contracts import FileSymbol

        sym = FileSymbol(
            name="test_func",
            qualified_name="module.test_func",
            symbol_type="function",
            line_start=10,
            line_end=20,
            symbol_id="test_123",
        )

        assert isinstance(sym.line_start, int)
        assert isinstance(sym.line_end, int)
        assert sym.line_start <= sym.line_end

    def test_ambiguous_symbol_candidates(self):
        """Error response should list all candidates when symbols are ambiguous."""
        from backend.intelligence.inspection.contracts import InspectSymbolResult

        error_response = InspectSymbolResult(
            symbol_id="",
            name="ambiguous",
            qualified_name="ambiguous",
            symbol_type="unknown",
            file_path="test.py",
            line_start=0,
            line_end=0,
            language="python",
            success=False,
            error="Multiple symbols found",
            candidates=[
                {
                    "symbol_id": "sym_1",
                    "qualified_name": "module.ambiguous",
                    "line_start": 10,
                    "line_end": 20,
                },
                {
                    "symbol_id": "sym_2",
                    "qualified_name": "module.ambiguous.inner",
                    "line_start": 15,
                    "line_end": 18,
                },
            ],
        )

        assert error_response.success is False
        assert error_response.candidates is not None
        assert len(error_response.candidates) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
