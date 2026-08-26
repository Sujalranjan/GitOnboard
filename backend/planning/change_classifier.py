"""
ChangeTypeClassifier: Categorizes the type of change requested.

Distinguishes between:
- COMMENT_ONLY: Source code comment changes (no behavior change)
- DOC_ONLY: Documentation changes (README, docs, no app code)
- CODE_CHANGE: Implementation changes (actual code modifications)

This prevents keyword-based scope explosion for trivial changes.
"""
from enum import Enum
from typing import List
import re


class ChangeType(Enum):
    """Categorizes the type of change being requested."""
    COMMENT_ONLY = "comment_only"
    DOC_ONLY = "doc_only"
    CODE_CHANGE = "code_change"


class ChangeTypeClassifier:
    """
    Classifies change requests to avoid unnecessary scope expansion.

    For comment-only and doc-only changes, skips keyword-based file discovery
    and relies only on direct investigation results.
    """

    # Keywords indicating comment-only changes
    COMMENT_KEYWORDS = {
        "comment", "comments", "add comment", "explain", "clarify",
        "document function", "docstring", "docstrings", "add doc",
        "inline comment", "comments only",
    }

    # Keywords/patterns indicating documentation-only changes
    DOC_KEYWORDS = {
        "readme", "documentation", "docs", "guide", "instruction",
        "setup guide", "installation", "getting started", "tutorial",
        "update readme", "update docs", "update documentation",
    }

    # Keywords that indicate actual code changes (not trivial)
    CODE_CHANGE_KEYWORDS = {
        "function", "class", "method", "implement", "add", "fix",
        "refactor", "update", "modify", "change", "create", "build",
        "feature", "bug", "issue", "error", "handler", "route",
        "endpoint", "api", "test", "verification", "assertion",
    }

    @staticmethod
    def classify(requirement: str) -> ChangeType:
        """
        Classify the change type based on the requirement text.

        Args:
            requirement: User's natural language requirement

        Returns:
            ChangeType enum indicating the classification
        """
        req_lower = requirement.lower()

        # Check for comment-only patterns
        if ChangeTypeClassifier._is_comment_only(req_lower):
            return ChangeType.COMMENT_ONLY

        # Check for doc-only patterns
        if ChangeTypeClassifier._is_doc_only(req_lower):
            return ChangeType.DOC_ONLY

        # Default to code change
        return ChangeType.CODE_CHANGE

    @staticmethod
    def _is_comment_only(req_lower: str) -> bool:
        """Check if requirement is for comment-only changes."""
        # Direct keyword matching
        for keyword in ChangeTypeClassifier.COMMENT_KEYWORDS:
            if keyword in req_lower:
                # Make sure it's not something like "add comment feature" (code change)
                if not any(code_kw in req_lower for code_kw in ["add function", "add method", "add class", "add feature"]):
                    return True

        # Pattern: "add ... comment" or "add ... explanation"
        if re.search(r"add\s+[a-z\s]+\s+(comment|explanation|clarification|note|doc)", req_lower):
            return True

        # Pattern: "comment ... explain"
        if re.search(r"comment.*explain|explain.*comment", req_lower):
            return True

        return False

    @staticmethod
    def _is_doc_only(req_lower: str) -> bool:
        """Check if requirement is for documentation-only changes."""
        for keyword in ChangeTypeClassifier.DOC_KEYWORDS:
            if keyword in req_lower:
                # Make sure it's not something like "add readme feature" (code change)
                if not any(code_kw in req_lower for code_kw in ["add function", "add method", "add class", "implement"]):
                    return True

        # Pattern: "update ... readme" or "update ... documentation"
        if re.search(r"update\s+[a-z\s]*(readme|docs|documentation|guide)", req_lower):
            return True

        return False
