"""
Deterministic priority assignment policy for context items.

Priority is determined based on evidence type, source, relevance, and confidence.
Same evidence always receives same priority (no randomness, no learning).
"""

from typing import Optional

from backend.agent.context.contracts import ContextEvidence

from .models import ContextItemPriority


class PriorityPolicy:
    """Deterministic policy for assigning priorities to context evidence."""

    # Thresholds for priority assignment
    HIGH_RELEVANCE_THRESHOLD = 0.85
    HIGH_CONFIDENCE_THRESHOLD = 0.8
    MEDIUM_RELEVANCE_THRESHOLD = 0.6
    MEDIUM_CONFIDENCE_THRESHOLD = 0.75
    LOW_RELEVANCE_THRESHOLD = 0.5

    @staticmethod
    def assign_priority(
        evidence: ContextEvidence,
        source_type_hint: Optional[str] = None,
    ) -> tuple[ContextItemPriority, str]:
        """
        Assign priority to evidence using deterministic rules.

        Args:
            evidence: The ContextEvidence item
            source_type_hint: Optional hint about context (e.g., "requirement_analysis")

        Returns:
            Tuple of (priority, reason_string)

        Priority rules:
        - PROTECTED: User requirements, critical RIM facts, high-relevance/confidence symbols
        - ACTIVE: Retrieved matches, currently-read symbols, high-confidence evidence
        - COMPRESSIBLE: Secondary evidence, supporting context, medium relevance
        - DISPOSABLE: Low-relevance expansion, redundant evidence
        """

        # PROTECTED: User requirements
        if evidence.source_type == "requirement_analysis":
            return (
                ContextItemPriority.PROTECTED,
                "User requirement (requirement_analysis source type)"
            )

        # PROTECTED: Critical RIM facts
        if evidence.source_type in ("rim_symbol", "rim_route"):
            return (
                ContextItemPriority.PROTECTED,
                f"Critical RIM fact ({evidence.source_type})"
            )

        # PROTECTED: High-relevance, high-confidence symbols
        if (evidence.relevance > PriorityPolicy.HIGH_RELEVANCE_THRESHOLD and
            evidence.confidence > PriorityPolicy.HIGH_CONFIDENCE_THRESHOLD):
            return (
                ContextItemPriority.PROTECTED,
                f"High relevance ({evidence.relevance:.2f}) and confidence ({evidence.confidence:.2f})"
            )

        # DISPOSABLE: Low-relevance evidence (regardless of confidence)
        if evidence.relevance < PriorityPolicy.LOW_RELEVANCE_THRESHOLD:
            return (
                ContextItemPriority.DISPOSABLE,
                f"Low relevance expansion ({evidence.relevance:.2f})"
            )

        # ACTIVE: Retrieved matches with high confidence
        if evidence.source_type == "retrieval":
            if evidence.confidence > PriorityPolicy.MEDIUM_CONFIDENCE_THRESHOLD:
                return (
                    ContextItemPriority.ACTIVE,
                    f"Retrieval match with high confidence ({evidence.confidence:.2f})"
                )

        # ACTIVE: High-confidence evidence
        if evidence.confidence > PriorityPolicy.MEDIUM_CONFIDENCE_THRESHOLD:
            return (
                ContextItemPriority.ACTIVE,
                f"High confidence evidence ({evidence.confidence:.2f})"
            )

        # COMPRESSIBLE: Medium relevance evidence
        if evidence.relevance >= PriorityPolicy.MEDIUM_RELEVANCE_THRESHOLD:
            return (
                ContextItemPriority.COMPRESSIBLE,
                f"Medium relevance secondary evidence ({evidence.relevance:.2f})"
            )

        # Default: COMPRESSIBLE for anything not matched above
        return (
            ContextItemPriority.COMPRESSIBLE,
            f"Supporting context (relevance={evidence.relevance:.2f}, confidence={evidence.confidence:.2f})"
        )

    @staticmethod
    def can_compress(priority: ContextItemPriority) -> bool:
        """Check if priority level allows compression."""
        return priority in (
            ContextItemPriority.COMPRESSIBLE,
            ContextItemPriority.DISPOSABLE,
        )

    @staticmethod
    def can_drop(priority: ContextItemPriority) -> bool:
        """Check if priority level allows dropping."""
        return priority in (
            ContextItemPriority.DISPOSABLE,
            ContextItemPriority.COMPRESSIBLE,  # Can drop after compression
        )

    @staticmethod
    def must_protect(priority: ContextItemPriority) -> bool:
        """Check if priority level is protected from modification."""
        return priority == ContextItemPriority.PROTECTED
