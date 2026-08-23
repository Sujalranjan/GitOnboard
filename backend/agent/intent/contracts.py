"""
Contracts and schema models for the Intent Router Subsystem (Phase 2).
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Intent(str, Enum):
    """
    Authoritative request intent categories.
    """
    CHAT = "chat"          # Greetings, pleasantries, non-task conversational dialogue
    EXPLORE = "explore"    # Symbol discovery, codebase navigation, directory tree inspection
    EXPLAIN = "explain"    # Conceptual, architectural, or logic explanation requests
    PLAN = "plan"          # Architecture/estimation queries without immediate mutation execution
    IMPLEMENT = "implement"# Concrete code modifications, bug fixes, refactoring
    CLARIFY = "clarify"    # Underspecified, ambiguous, or multi-faceted requests


class IntentResult(BaseModel):
    """
    Structured classification outcome produced by IntentRouter.
    """
    intent: Intent = Field(..., description="Classified intent category")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence score [0.0, 1.0]")
    reason: Optional[str] = Field(default=None, description="Explanation or rule trigger for classification")
    classification_method: str = Field(
        default="deterministic",
        description="Method used for classification ('deterministic', 'llm', 'fallback')",
    )
    detected_entities: List[str] = Field(
        default_factory=list,
        description="Entities (symbols, filenames, frameworks) extracted during classification",
    )
