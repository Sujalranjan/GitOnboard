"""
Shared utilities for inspection tools: language detection, token estimation.
"""
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def detect_language(file_path: str) -> str:
    """
    Detect language from file extension.
    Returns: python, javascript, typescript, jsx, tsx, or "unknown"
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    extension_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
    }

    return extension_map.get(suffix, "unknown")


def estimate_tokens(text: str, method: str = "approximate") -> int:
    """
    Estimate token count for text.
    Uses approximation: ~4 characters per token for English text.

    Args:
        text: Source code or text to estimate
        method: "approximate" (default) or "precise"

    Returns:
        Estimated token count
    """
    if method == "approximate":
        # Rough approximation: ~4 chars per token
        # This is more accurate for code than for prose
        return max(1, len(text) // 4)

    # If precise tokenization is needed later, can integrate with tiktoken or transformers
    return max(1, len(text) // 4)


def calculate_file_size_kb(file_size_bytes: int) -> float:
    """Convert bytes to KB, rounded to 1 decimal place."""
    return round(file_size_bytes / 1024, 1)


def format_line_number(line_num: int, total_lines: int) -> str:
    """Format line number with appropriate width based on total lines."""
    width = len(str(total_lines))
    return f"{line_num:>{width}d}"


def number_source_lines(raw_text: str, start_line: int = 1) -> str:
    """
    Add line numbers to source code.

    Args:
        raw_text: Source code without line numbers
        start_line: Starting line number (default 1)

    Returns:
        Source with numbered lines (e.g. "   42 | code")
    """
    lines = raw_text.splitlines(keepends=True)
    total = start_line + len(lines) - 1
    width = len(str(total))

    numbered = []
    for idx, line in enumerate(lines, start=start_line):
        # Format: "   42 | code line"
        numbered.append(f"{idx:>{width}d} | {line}")

    return "".join(numbered)
