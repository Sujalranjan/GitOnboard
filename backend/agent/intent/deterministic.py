"""
Deterministic rule-based intent classifier (Stage 1 of Intent Router).

Provides fast, explainable, and conservative classification for obvious patterns.
Returns None if a pattern is nuanced or ambiguous, deferring to the LLM stage.
"""
from __future__ import annotations

import re
from typing import Optional

from backend.agent.intent.contracts import Intent, IntentResult

# Canonical pattern sets
GREETING_PATTERNS = [
    r"^hi\b",
    r"^hello\b",
    r"^hey\b",
    r"^greetings\b",
    r"^good\s+(morning|afternoon|evening)\b",
    r"^thanks\b",
    r"^thank\s+you\b",
    r"^what\s+can\s+you\s+do\??$",
    r"^who\s+are\s+you\??$",
    r"^help\??$",
]

EXPLORE_PATTERNS = [
    r"^show\s+(me\s+)?(the\s+)?(repo(sitory)?\s+)?tree\b",
    r"^find\s+([A-Za-z0-9_]+)\b",
    r"^where\s+is\s+([A-Za-z0-9_\s]+)\s+implemented\??",
    r"^where\s+is\s+([A-Za-z0-9_\s]+)\s+defined\??",
    r"^find\s+references\s+to\s+([A-Za-z0-9_]+)\b",
    r"^list\s+(all\s+)?files\b",
    r"^search\s+for\s+([A-Za-z0-9_\s]+)\b",
    r"^show\s+(me\s+)?(the\s+)?([A-Za-z0-9_\s]+)\s+files\b",
]

EXPLAIN_PATTERNS = [
    r"^how\s+does\s+([a-z0-9_\s]+)\s+work\??",
    r"^why\s+is\s+([a-z0-9_\s]+)\s+(used|configured|designed)\??",
    r"^explain\s+([a-z0-9_\s]+)\b",
    r"^what\s+does\s+([a-z0-9_\s]+)\s+do\??",
    r"^why\s+would\s+i\s+(change|modify)\s+([a-z0-9_\.\s]+)\??",
    r"^tell\s+me\s+about\s+([a-z0-9_\s]+)\b",
    r"^how\s+do\s+i\s+fix\s+([a-z0-9_\s]+)\??",  # Asking "how" is explanatory
    r"^tell\s+me\s+how\s+to\s+([a-z0-9_\s]+)\b",
]

PLAN_PATTERNS = [
    r"^what\s+would\s+it\s+take\s+to\s+([A-Za-z0-9_\s]+)\??",
    r"^what\s+would\s+([A-Za-z0-9_\.\s]+)\s+require\??",
    r"^how\s+should\s+we\s+implement\s+([A-Za-z0-9_\s]+)\??",
    r"^what\s+files\s+would\s+(need\s+to\s+)?change\??",
    r"^could\s+we\s+add\s+([A-Za-z0-9_\s]+)\??",
    r"^what\s+is\s+the\s+plan\s+for\s+([A-Za-z0-9_\s]+)\??",
    r"^estimate\s+(the\s+)?changes\s+for\s+([A-Za-z0-9_\s]+)\b",
]

CLARIFY_UNDERSPECIFIED_PATTERNS = [
    r"^make\s+([A-Za-z0-9_\s]+)\s+better$",
    r"^improve\s+this$",
    r"^clean\s+this\s+up$",
    r"^make\s+it\s+faster$",
    r"^fix\s+the\s+project$",
    r"^fix\s+it$",
    r"^make\s+it\s+work$",
    r"^optimize\s+everything$",
]

IMPLEMENT_PATTERNS = [
    r"^add\s+(new\s+)?([A-Za-z0-9_\s\.\-]+)$",
    r"^implement\s+([A-Za-z0-9_\s\.\-]+)$",
    r"^fix\s+(the\s+)?([A-Za-z0-9_\s\.\-]+)\s+bug$",
    r"^modify\s+([A-Za-z0-9_\.\/\\\-]+)$",
    r"^refactor\s+([A-Za-z0-9_\.\/\\\-]+)$",
    r"^delete\s+([A-Za-z0-9_\.\/\\\-]+)$",
    r"^create\s+(new\s+)?([A-Za-z0-9_\s\.\-]+)$",
    r"^build\s+([A-Za-z0-9_\s\.\-]+)$",
    r"^update\s+([A-Za-z0-9_\.\/\\\-]+)\s+to\s+([A-Za-z0-9_\s]+)$",
]


def classify_deterministic(requirement: str) -> Optional[IntentResult]:
    """
    Evaluates rule-based patterns against the user requirement.
    Returns an IntentResult if matched with high confidence, or None to defer.
    """
    if not requirement or not requirement.strip():
        return IntentResult(
            intent=Intent.CLARIFY,
            confidence=1.0,
            reason="Empty or whitespace-only requirement",
            classification_method="deterministic",
        )

    norm = requirement.strip().lower()

    # Invariant: Negative constraint ("do not change/modify anything, just explain...")
    if re.search(r"\b(do\s+not|don't|without)\s+(change|modify|edit|alter|touch)\b", norm):
        return IntentResult(
            intent=Intent.EXPLAIN,
            confidence=0.98,
            reason="Explicit negative constraint against mutation",
            classification_method="deterministic",
        )

    # 1. Check CHAT
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.CHAT,
                confidence=1.0,
                reason=f"Matched conversational greeting pattern '{pattern}'",
                classification_method="deterministic",
            )

    # 2. Check CLARIFY (Vague / underspecified requests)
    for pattern in CLARIFY_UNDERSPECIFIED_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.CLARIFY,
                confidence=0.95,
                reason=f"Matched underspecified pattern '{pattern}'",
                classification_method="deterministic",
            )

    # 3. Check EXPLORE
    for pattern in EXPLORE_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.EXPLORE,
                confidence=0.95,
                reason=f"Matched repository exploration pattern '{pattern}'",
                classification_method="deterministic",
            )

    # 4. Check EXPLAIN
    for pattern in EXPLAIN_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.EXPLAIN,
                confidence=0.95,
                reason=f"Matched conceptual explanation pattern '{pattern}'",
                classification_method="deterministic",
            )

    # 5. Check PLAN
    for pattern in PLAN_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.PLAN,
                confidence=0.90,
                reason=f"Matched planning query pattern '{pattern}'",
                classification_method="deterministic",
            )

    # 6. Check IMPLEMENT
    for pattern in IMPLEMENT_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.IMPLEMENT,
                confidence=0.90,
                reason=f"Matched direct mutation command '{pattern}'",
                classification_method="deterministic",
            )

    return None
