"""
Data models and enumerations for the documentation-aware repository summary pipeline.
"""
from __future__ import annotations
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocType(str, Enum):
    PRIMARY_README = "PRIMARY_README"
    ARCHITECTURE = "ARCHITECTURE"
    CONTRIBUTING = "CONTRIBUTING"
    PRODUCT_SYSTEM_DOCS = "PRODUCT_SYSTEM_DOCS"
    API_DOCS = "API_DOCS"
    GUIDES_TUTORIALS = "GUIDES_TUTORIALS"
    DIAGRAMS = "DIAGRAMS"
    AGENT_INSTRUCTIONS = "AGENT_INSTRUCTIONS"
    GENERIC_DOCS = "GENERIC_DOCS"


class DocPriority(IntEnum):
    HIGHEST = 100        # README, Architecture, System Design
    HIGH = 75            # Contributing, Core Product Docs
    MEDIUM = 50          # API Docs, Guides, Tutorials, Diagrams
    AGENT_CONTEXT = 20   # Agent/Tool Instructions (AGENTS.md, CLAUDE.md, skill.md)
    LOW = 10             # Generic / Misc Docs
    EXCLUDE = 0          # Ignored, vendored, build output


class DiscoveredDoc(BaseModel):
    path: str
    filename: str
    doc_type: DocType
    priority: DocPriority
    raw_size: int
    line_count: int
    headings: List[str] = Field(default_factory=list)
    content: str = ""
    is_truncated: bool = False
    token_estimate: int = 0


class BudgetedDocContext(BaseModel):
    primary_docs: List[DiscoveredDoc] = Field(default_factory=list)
    supporting_docs: List[DiscoveredDoc] = Field(default_factory=list)
    diagram_docs: List[DiscoveredDoc] = Field(default_factory=list)
    agent_docs: List[DiscoveredDoc] = Field(default_factory=list)
    omitted_docs: List[str] = Field(default_factory=list)
    total_chars: int = 0
    total_tokens_est: int = 0


class SummaryGenerationResult(BaseModel):
    summary_markdown: str
    doc_context_stats: Dict[str, Any] = Field(default_factory=dict)
    discrepancies_detected: List[str] = Field(default_factory=list)
    tool_calls_made: List[Dict[str, Any]] = Field(default_factory=list)
