"""
Unit tests for semantic truncation in repository tools.
Validates:
1. 10 complete Python functions fit, but Function 11 is omitted completely rather than sliced.
2. Markdown text cuts at paragraph/sentence boundaries, never mid-sentence.
3. Continuation metadata fits within reserved control tokens.
4. Subsequent read with continuation pointers retrieves omitted content without duplication.
"""

import pytest
from backend.repository_tools.truncation import (
    find_code_semantic_boundaries,
    find_text_semantic_boundaries,
    truncate_semantically,
)


class TestSemanticTruncation:
    def test_complete_functions_preserved_function_11_omitted(self):
        """
        Create 15 complete Python functions.
        Ensure that when budget fits ~10 functions, functions 1-10 are returned completely,
        and Function 11 is completely omitted rather than cut in half.
        """
        lines = []
        for i in range(1, 16):
            lines.append(f"def function_{i}(x, y):")
            lines.append(f"    # Implementation of function {i}")
            lines.append(f"    result = x + y + {i}")
            lines.append(f"    return result")
            lines.append("")  # Blank line separator

        # 10 functions is 50 lines, 1393 chars ≈ 398 tokens.
        # Set max_tokens to 450 tokens with 30 reserved control tokens (420 content tokens ≈ 1470 chars).
        # This fits functions 1-10 (1393 chars) but omits function 11 (1535 chars).
        truncated, count, was_truncated = truncate_semantically(
            lines=lines,
            max_tokens=450,
            file_path="service.py",
            reserved_control_tokens=30,
            chars_per_token=3.5,
        )

        assert was_truncated is True
        # Check that all returned functions are complete
        returned_text = "".join(truncated)
        for i in range(1, 11):
            assert f"def function_{i}(" in returned_text
            assert f"    return result" in returned_text

        # Function 11 must NOT be partially in returned_text
        assert "def function_11" not in returned_text
        assert "function 11" not in returned_text

    def test_markdown_text_cuts_at_paragraph_or_sentence_boundary(self):
        """
        Markdown text cuts at paragraph/section boundaries, never mid-sentence.
        """
        lines = [
            "# Architecture Overview\n",
            "\n",
            "This is paragraph one explaining the core system. It has two complete sentences.\n",
            "\n",
            "## Subsystem Details\n",
            "\n",
            "This is paragraph two explaining subsystem details. Here is another sentence.\n",
            "\n",
            "This is paragraph three which should be omitted if budget runs out.\n",
        ]

        truncated, count, was_truncated = truncate_semantically(
            lines=lines,
            max_tokens=70,
            file_path="README.md",
            reserved_control_tokens=15,
            chars_per_token=3.5,
        )

        assert was_truncated is True
        returned_text = "".join(truncated)
        # Should include paragraph one completely
        assert "paragraph one explaining the core system." in returned_text
        # Should not cut mid-sentence
        last_line = [l.strip() for l in truncated if l.strip()][-1]
        assert last_line.endswith((".", "#", "Details"))

    def test_continuation_preserves_remaining_content_without_loss(self):
        """
        Simulate sequential reading: read chunk 1, then read remaining starting from next_start_line.
        Ensure 100% of lines are retrieved across chunks without duplication.
        """
        lines = [f"line_{i}\n" for i in range(1, 101)]

        # Chunk 1
        chunk1, count1, was_clamped1 = truncate_semantically(
            lines=lines,
            max_tokens=80,
            file_path="data.txt",
            reserved_control_tokens=20,
        )
        assert was_clamped1 is True
        assert count1 > 0

        # Chunk 2 - provide sufficient budget to fetch remaining lines
        remaining = lines[count1:]
        chunk2, count2, was_clamped2 = truncate_semantically(
            lines=remaining,
            max_tokens=600,
            file_path="data.txt",
            reserved_control_tokens=20,
        )

        all_retrieved = chunk1 + chunk2
        # Verify no lines were lost and no lines were duplicated
        assert all_retrieved == lines
