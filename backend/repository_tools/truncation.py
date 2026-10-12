"""
Semantic truncation and boundary detection for repository code and text documents.

Ensures repository content is truncated at complete semantic units:
- Code: class, function/def, logical block, or complete line (never halfway through a function)
- Markdown/Text: section, paragraph, list item, or sentence (never halfway through a sentence)
"""

from __future__ import annotations
import re
from typing import List, Tuple, Optional


def find_code_semantic_boundaries(lines: List[str]) -> List[int]:
    """
    Find safe cutting indices (0-based line indices where a complete semantic unit ends).

    For indentation-based code (Python) and brace-based code (JS, TS, C, Java, Go):
    A line that is followed by a top-level or method definition (e.g. `def `, `class `, `async def `, `function `)
    or an unindented statement represents a boundary where previous units are complete.
    """
    boundaries = [0]
    total = len(lines)
    if total == 0:
        return boundaries

    # Pattern for new top-level or method definition
    def_pattern = re.compile(r"^(?:[ \t]*(?:async\s+)?def\s+|[ \t]*class\s+|[ \t]*(?:export\s+)?(?:default\s+)?function\b|[ \t]*(?:public|private|protected|static)?\s*(?:async\s+)?\w+\s*\([^)]*\)\s*[{:]?)")

    for i in range(1, total):
        line = lines[i]
        prev_line = lines[i - 1].strip()

        # If previous line is empty and current line starts a new definition or top-level block
        if def_pattern.match(line):
            boundaries.append(i)
        elif not prev_line and line.strip() and not line.startswith(" ") and not line.startswith("\t"):
            # Blank line followed by unindented line
            boundaries.append(i)

    # The end of the file is always a boundary
    boundaries.append(total)
    return sorted(list(set(boundaries)))


def find_text_semantic_boundaries(lines: List[str]) -> List[int]:
    """
    Find safe cutting indices in Markdown or plain text.
    Boundaries: blank lines (paragraph ends), markdown headers (`#`), list items, or sentence ends.
    """
    boundaries = [0]
    total = len(lines)
    if total == 0:
        return boundaries

    sentence_end = re.compile(r"[.!?][ \t]*$")

    for i in range(1, total):
        line = lines[i].strip()
        prev_line = lines[i - 1].strip()

        # Markdown header
        if line.startswith("#"):
            boundaries.append(i)
        # Blank line (paragraph break)
        elif not prev_line and line:
            boundaries.append(i)
        # Previous line ended with sentence punctuation
        elif sentence_end.search(prev_line):
            boundaries.append(i)

    boundaries.append(total)
    return sorted(list(set(boundaries)))


def truncate_semantically(
    lines: List[str],
    max_tokens: int,
    file_path: str = "",
    reserved_control_tokens: int = 60,
    chars_per_token: float = 3.5,
) -> Tuple[List[str], int, bool]:
    """
    Semantically truncate a list of lines so total content + formatting stays within max_tokens.

    Args:
        lines: Selected lines to truncate.
        max_tokens: Maximum token budget available for this content.
        file_path: Path to file (used to detect language).
        reserved_control_tokens: Tokens to reserve for continuation notice.
        chars_per_token: Estimated conversion factor for raw characters to tokens.

    Returns:
        (truncated_lines, actual_count, was_truncated)
    """
    total_lines = len(lines)
    if total_lines == 0:
        return [], 0, False

    # Effective content budget in characters
    effective_tokens = max(10, max_tokens - reserved_control_tokens)
    max_chars = int(effective_tokens * chars_per_token)

    # Quick check: does everything fit?
    total_chars = sum(len(line) + 8 for line in lines)  # 8 chars for line number prefix
    if total_chars <= max_chars:
        return lines, total_lines, False

    # Detect file type
    is_text = file_path.lower().endswith((".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml"))
    if is_text:
        boundaries = find_text_semantic_boundaries(lines)
    else:
        boundaries = find_code_semantic_boundaries(lines)

    # Find the largest boundary that fits within max_chars
    best_boundary = 0

    for b in boundaries:
        if b == 0:
            continue
        total_b_chars = sum(len(lines[j]) + 8 for j in range(b))
        if total_b_chars <= max_chars:
            best_boundary = b
        else:
            break

    # If no semantic boundary fit (e.g. first function is larger than whole budget),
    # fallback to line-by-line cutting at sentence/statement boundary
    if best_boundary == 0:
        accumulated_chars = 0
        for idx, line in enumerate(lines):
            line_len = len(line) + 8
            if accumulated_chars + line_len > max_chars and best_boundary > 0:
                break
            accumulated_chars += line_len
            best_boundary = idx + 1

    # Guarantee at least 1 line if budget allows anything
    best_boundary = max(1, min(best_boundary, total_lines))
    selected = lines[:best_boundary]
    was_truncated = best_boundary < total_lines

    return selected, best_boundary, was_truncated
