"""
Context lifecycle management models for Phase 2L.

ContextItem: Extends ContextEvidence with lifecycle metadata.
CompressedContext: Tracks compression operations with provenance.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.agent.context.contracts import ContextEvidence


class ContextItemPriority(str, Enum):
    """Priority level for context item retention."""

    PROTECTED = "PROTECTED"
    """Never compress or drop. User requirements, critical RIM facts."""

    ACTIVE = "ACTIVE"
    """Preferred to keep. Currently read symbols, retrieved matches."""

    COMPRESSIBLE = "COMPRESSIBLE"
    """Candidates for summarization. Secondary evidence, supporting context."""

    DISPOSABLE = "DISPOSABLE"
    """Candidates for drop. Low-relevance expansion, redundant items."""


class ContextItemState(str, Enum):
    """Lifecycle state of a context item."""

    ACTIVE = "ACTIVE"
    """Item is included in active context."""

    REFERENCE = "REFERENCE"
    """Item was dropped or summarized; content hidden from active context."""

    COMPRESSED = "COMPRESSED"
    """Item was replaced with a summary."""

    DROPPED = "DROPPED"
    """Item was removed from active context but content preserved."""


class ContextItem(ContextEvidence):
    """
    ContextEvidence extended with lifecycle metadata.

    Adds:
    - Immutable item ID
    - Priority and state tracking
    - Token accounting
    - Compression tracking
    - Provenance timestamps
    """

    context_item_id: str = Field(
        description="UUID-based immutable identifier. Format: ctx_NNNN_XXXXXXXX"
    )
    priority: ContextItemPriority = Field(
        default=ContextItemPriority.ACTIVE,
        description="Priority level for retention decisions"
    )
    estimated_tokens: int = Field(
        default=0,
        description="Per-item token cost estimate"
    )
    state: ContextItemState = Field(
        default=ContextItemState.ACTIVE,
        description="Lifecycle state (ACTIVE, REFERENCE, COMPRESSED, DROPPED)"
    )

    # Compression tracking
    is_compressed: bool = Field(
        default=False,
        description="Whether this item is a compressed version of original"
    )
    compression_summary: Optional[str] = Field(
        default=None,
        description="Summary text if this item is compressed"
    )
    original_context_item_id: Optional[str] = Field(
        default=None,
        description="If this IS a compressed version, ID of original item"
    )
    compression_timestamp: Optional[datetime] = Field(
        default=None,
        description="When compression occurred"
    )

    # Provenance
    created_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When this item was created"
    )
    retrieval_source: str = Field(
        default="unknown",
        description="How item was added: 'retrieval', 'rim_symbol', 'rim_route', 'source_excerpt', etc"
    )

    # For debugging/audit
    reason_for_priority: Optional[str] = Field(
        default=None,
        description="Rationale for assigned priority level"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_evidence(
        cls,
        evidence: ContextEvidence,
        priority: ContextItemPriority = ContextItemPriority.ACTIVE,
        retrieval_source: str = "unknown",
        estimated_tokens: int = 0,
        reason_for_priority: Optional[str] = None,
    ) -> "ContextItem":
        """Create ContextItem from ContextEvidence, assigning ID and defaults."""
        item_index = 0  # Will be set by ContextManager when adding
        item_id = f"ctx_{item_index:04d}_{uuid4().hex[:8]}"

        return cls(
            context_item_id=item_id,
            priority=priority,
            estimated_tokens=estimated_tokens,
            state=ContextItemState.ACTIVE,
            is_compressed=False,
            created_timestamp=datetime.now(),
            retrieval_source=retrieval_source,
            reason_for_priority=reason_for_priority,
            # ContextEvidence fields
            source_type=evidence.source_type,
            source_id=evidence.source_id,
            relevance=evidence.relevance,
            confidence=evidence.confidence,
            summary=evidence.summary,
            data=evidence.data,
            metadata=evidence.metadata,
        )


class CompressedContext(BaseModel):
    """
    Provenance record for a compression operation.

    Tracks original item, summary, compression metadata.
    """

    original_item_id: str = Field(
        description="ID of original ContextItem before compression"
    )
    summary_item_id: str = Field(
        description="ID of new ContextItem containing summary"
    )
    compression_summary: str = Field(
        description="Summary text replacing original content"
    )
    compression_model: str = Field(
        default="claude-opus-4-8",
        description="Model used for compression"
    )
    compression_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When compression occurred"
    )
    original_tokens: int = Field(
        description="Token count of original item"
    )
    summary_tokens: int = Field(
        description="Token count of compressed summary"
    )
    token_savings: int = Field(
        description="Tokens saved by compression"
    )
    original_still_retrievable: bool = Field(
        default=True,
        description="Whether original content can be re-requested"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)
