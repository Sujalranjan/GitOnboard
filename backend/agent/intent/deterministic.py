"""
Deterministic rule-based intent fast-path (Stage 1 of Intent Router).

Provides instant (<1ms) classification ONLY for unambiguous conversational greetings
and empty inputs, deferring all codebase and implementation queries to the LLM classifier.
"""
from __future__ import annotations

import re
from typing import Optional

from backend.agent.intent.contracts import Intent, IntentResult

# Pure greetings & pleasantries only
GREETING_PATTERNS = [
    r"^hi(|\s|$)",
    r"^hello(|\s|$)",
    r"^hey(|\s|$)",
    r"^greetings(|\s|$)",
    r"^good\s+(morning|afternoon|evening)(|\s|$)",
    r"^thanks(|\s|$)",
    r"^thank\s+you(|\s|$)",
    r"^what\s+can\s+you\s+do\??$",
    r"^who\s+are\s+you\??$",
    r"^help\??$",
]


def classify_deterministic(requirement: str) -> Optional[IntentResult]:
    """
    Evaluates fast-path greeting patterns. Returns IntentResult only for obvious greetings,
    deferring everything else to the primary LLM classifier.
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

    return None
