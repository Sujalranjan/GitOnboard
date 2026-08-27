"""
Deterministic rule-based intent fast-path (Stage 1 of Intent Router).

Provides instant (<1ms) classification ONLY for unambiguous conversational greetings,
explicit explanation, and exploration queries, deferring all implementation queries to the LLM classifier.
"""
from __future__ import annotations

import re
from typing import Optional

from backend.agent.intent.contracts import Intent, IntentResult

# Pure greetings & pleasantries only
GREETING_PATTERNS = [
    r"^hi( |\s|$)",
    r"^hello( |\s|$)",
    r"^hey( |\s|$)",
    r"^greetings( |\s|$)",
    r"^good\s+(morning|afternoon|evening)( |\s|$)",
    r"^thanks( |\s|$)",
    r"^thank\s+you( |\s|$)",
    r"^what\s+can\s+you\s+do\??$",
    r"^who\s+are\s+you\??$",
    r"^help\??$",
]

EXPLAIN_PATTERNS = [
    r"^(explain|describe|tell me about)\b",
    r"^(what does|what do|what is the purpose of)\b",
    r"^what (is|are) .* (doing|for|used for)\b",
    r"^how (does|do) .* work\b",
]

EXPLORE_PATTERNS = [
    r"^(what|which) (functions|symbols|classes|methods|imports|files) (are|does|do|depend)\b",
    r"^(what|which) (functions|symbols|classes|methods) (call|use|extend|inherit)\b",
    r"^(what|which) (handler|endpoint|route) serves\b",
    r"^(what|which) code uses\b",
    r"^list (files|symbols|functions|classes|routes)\b",
    r"^where is\b",
    r"^find (file|symbol|function|class)\b",
]


def classify_deterministic(requirement: str) -> Optional[IntentResult]:
    """
    Evaluates fast-path greeting, explanation, and code exploration patterns.
    Returns IntentResult for obvious cases, deferring everything else to the LLM classifier.
    """
    if not requirement or not requirement.strip():
        return IntentResult(
            intent=Intent.CLARIFY,
            confidence=1.0,
            reason="Empty or whitespace-only requirement",
            classification_method="deterministic",
        )

    norm = requirement.strip().lower().replace("’", "'").replace("`", "'")

    # Fast-path for conversational greetings
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.CHAT,
                confidence=1.0,
                reason=f"Matched conversational greeting pattern '{pattern}'",
                classification_method="deterministic",
            )

    # Fast-path for exploration / symbol / relationship queries
    for pattern in EXPLORE_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.EXPLORE,
                confidence=0.95,
                reason=f"Matched exploration query pattern '{pattern}'",
                classification_method="deterministic",
            )

    # Fast-path for explicit explanation questions
    for pattern in EXPLAIN_PATTERNS:
        if re.search(pattern, norm):
            return IntentResult(
                intent=Intent.EXPLAIN,
                confidence=0.95,
                reason=f"Matched explicit explanation pattern '{pattern}'",
                classification_method="deterministic",
            )

    return None
