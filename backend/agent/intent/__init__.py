"""
Intent classification package for GitOnboard.
"""
from backend.agent.intent.contracts import Intent, IntentResult
from backend.agent.intent.deterministic import classify_deterministic
from backend.agent.intent.llm_classifier import classify_with_llm, classify_with_llm_async
from backend.agent.intent.router import IntentRouter

__all__ = [
    "Intent",
    "IntentResult",
    "classify_deterministic",
    "classify_with_llm",
    "classify_with_llm_async",
    "IntentRouter",
]
