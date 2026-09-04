"""
Finding schema and state machine for investigations.

A Finding represents a potential issue discovered during investigation.
It progresses through defined states to ensure proper evidence gathering.

Safety invariants enforced:
1. State transitions are validated and enforced
2. Negative claims cannot bypass ground-truth verification
3. Confirmation requires ACTUAL validated Evidence objects, not metadata
4. Ground truth must be represented by Evidence objects, not paths
5. Contradictory evidence blocks confirmation
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Literal

if TYPE_CHECKING:
    from backend.investigation.evidence import Evidence


class InvalidFindingStateError(ValueError):
    """Raised when an invalid state transition is attempted."""
    pass


class MissingGroundTruthError(ValueError):
    """Raised when ground truth is required but missing."""
    pass


class FindingSeverity(str, Enum):
    """Investigation finding severity levels."""
    P0 = "P0"  # Critical: Data corruption, safety issues, incorrect knowledge
    P1 = "P1"  # Major: Significant recall failures, systematic issues
    P2 = "P2"  # Minor: Edge cases, non-critical inefficiencies


class FindingStatus(str, Enum):
    """Investigation state machine for findings."""
    OBSERVED = "OBSERVED"
    """Initial observation; hypothesis formed but not yet verified."""

    HYPOTHESIS = "HYPOTHESIS"
    """Claim stated but ground truth not yet verified."""

    GROUND_TRUTH_VERIFIED = "GROUND_TRUTH_VERIFIED"
    """For claims about existence/absence, repository verification complete."""

    INVESTIGATED = "INVESTIGATED"
    """Scout has gathered evidence; awaiting independent verification."""

    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    """Verification agent attempted to disprove; awaiting final verdict."""

    CONFIRMED = "CONFIRMED"
    """Finding confirmed with direct evidence; safe to act on."""

    REFUTED = "REFUTED"
    """Finding actively disproven; contradicting evidence found."""

    UNRESOLVED = "UNRESOLVED"
    """Insufficient evidence; investigation cannot proceed."""


@dataclass
class Finding:
    """
    A single investigation finding with full lifecycle tracking.

    A finding is NOT confirmed until it has passed through the complete
    state machine with direct evidence.
    """

    # Identity
    finding_id: str
    """Unique identifier: RETRIEVAL-001, PARSER-002, etc."""

    # Content
    claim: str
    """The specific claim being investigated."""

    claim_type: Literal[
        "EXISTS", "ABSENT", "MISSING", "FUNCTIONAL",
        "RETRIEVAL_FAILURE", "PARSER_FAILURE", "INDEX_FAILURE"
    ]
    """Type of claim for routing to appropriate validators."""

    # Status tracking
    status: FindingStatus = FindingStatus.OBSERVED
    """Current position in investigation state machine."""

    severity: FindingSeverity = FindingSeverity.P1
    """P0 (critical), P1 (major), P2 (minor)."""

    # Evidence - ACTUAL validated Evidence objects (not just metadata)
    evidence: List["Evidence"] = field(default_factory=list)
    """Actual validated Evidence objects. This determines evidence validity."""

    # Metadata about where to find evidence (for context minimization)
    evidence_files: List[str] = field(default_factory=list)
    """Paths to JSON/artifact files containing evidence (for reference, not validation)."""

    evidence_summary: str = ""
    """Brief summary of evidence collected so far (presentation only, not evidence validation)."""

    # Ground truth (for negative/absence claims)
    ground_truth_claim: Optional[Literal["EXISTS", "ABSENT"]] = None
    """For claims about existence, the actual verified state."""

    ground_truth_evidence: Optional["Evidence"] = None
    """Actual validated Evidence representing ground-truth verification (not a path)."""

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    # Next steps
    next_investigation: str = ""
    """What should be investigated next if this finding is confirmed."""

    # Metadata
    scout_agent: Optional[str] = None
    """Which agent investigated this finding."""

    verification_attempts: int = 0
    """How many times verification was attempted."""

    contradictory_evidence: Optional[str] = None
    """Path to evidence contradicting this finding, if any."""

    def can_proceed_to_investigation(self) -> bool:
        """
        Check if finding has sufficient evidence to proceed downstream.

        For negative claims (ABSENT, MISSING), ground truth MUST be verified.
        For positive claims (EXISTS, FUNCTIONAL), hypothesis is sufficient.
        """
        if self.claim_type in ("ABSENT", "MISSING"):
            return self.status in (
                FindingStatus.GROUND_TRUTH_VERIFIED,
                FindingStatus.INVESTIGATED,
                FindingStatus.INDEPENDENTLY_VERIFIED,
                FindingStatus.CONFIRMED,
                FindingStatus.REFUTED,
            )
        else:
            return self.status in (
                FindingStatus.HYPOTHESIS,
                FindingStatus.INVESTIGATED,
                FindingStatus.INDEPENDENTLY_VERIFIED,
                FindingStatus.CONFIRMED,
                FindingStatus.REFUTED,
            )

    def _validate_transition(self, new_status: FindingStatus):
        """
        Validate that a status transition is allowed.

        Enforces the intended state machine:
        OBSERVED → HYPOTHESIS → [GROUND_TRUTH_VERIFIED] → INVESTIGATED
                            → INDEPENDENTLY_VERIFIED → CONFIRMED/REFUTED/UNRESOLVED

        For negative claims (ABSENT, MISSING), GROUND_TRUTH_VERIFIED is mandatory
        before proceeding to INVESTIGATED.
        """
        current = self.status
        is_negative_claim = self.claim_type in ("ABSENT", "MISSING")

        # Valid transitions from each state
        valid_transitions = {
            FindingStatus.OBSERVED: [FindingStatus.HYPOTHESIS],

            FindingStatus.HYPOTHESIS: (
                [FindingStatus.GROUND_TRUTH_VERIFIED] if is_negative_claim
                else [FindingStatus.INVESTIGATED]
            ),

            FindingStatus.GROUND_TRUTH_VERIFIED: [FindingStatus.INVESTIGATED],

            FindingStatus.INVESTIGATED: [FindingStatus.INDEPENDENTLY_VERIFIED],

            FindingStatus.INDEPENDENTLY_VERIFIED: [
                FindingStatus.CONFIRMED,
                FindingStatus.REFUTED,
                FindingStatus.UNRESOLVED,
            ],

            # Terminal states
            FindingStatus.CONFIRMED: [FindingStatus.REFUTED],  # Can refute a confirmed finding if new evidence
            FindingStatus.REFUTED: [FindingStatus.INVESTIGATED],  # Can re-investigate
            FindingStatus.UNRESOLVED: [FindingStatus.INVESTIGATED],  # Can re-investigate
        }

        if current not in valid_transitions:
            raise InvalidFindingStateError(f"Unknown state: {current}")

        if new_status not in valid_transitions[current]:
            raise InvalidFindingStateError(
                f"Invalid transition: {current.value} → {new_status.value}"
            )

    def advance_status(self, new_status: FindingStatus):
        """
        Transition to new status with full validation.

        Raises InvalidFindingStateError if the transition is not allowed.
        """
        self._validate_transition(new_status)
        self.status = new_status
        self.last_updated = datetime.now()

    def has_direct_evidence(self) -> bool:
        """
        Check if finding has direct evidence meeting confirmation requirements.

        CRITICAL: This checks ACTUAL Evidence objects, not metadata.

        Requirements:
        - At least one Evidence object with type=DIRECT
        - Confidence >= 0.9
        - No unresolved contradictions
        - No UNVERIFIED, INFERRED, or INDIRECT evidence masquerading as DIRECT

        This method does NOT rely on evidence_files, evidence_summary, or other
        metadata. Those are for artifact navigation, not evidence validation.
        """
        # IMPORT MOVED HERE to avoid circular import
        from backend.investigation.evidence import EvidenceType

        # Check for unresolved contradictions
        if self.contradictory_evidence:
            return False

        # Must have actual validated Evidence objects
        if not self.evidence:
            return False

        # Look for at least one DIRECT evidence with sufficient confidence
        for evid in self.evidence:
            if evid.evidence_type == EvidenceType.DIRECT and evid.confidence >= 0.9:
                return True

        # No valid DIRECT evidence found
        return False

    def is_ready_for_confirmation(self) -> bool:
        """
        Check if finding can be marked CONFIRMED.

        All requirements must be met; this is conservative.

        Requirements:
        1. Status must be INDEPENDENTLY_VERIFIED (state machine reached)
        2. Verification must have been attempted (at least once)
        3. Direct evidence must exist (and be validated)
        4. No unresolved contradictions
        5. For negative claims: ground truth must be verified with evidence

        Returns False if any requirement is not met.
        Raises MissingGroundTruthError if negative claim lacks GT evidence.
        """
        # Requirement 1: Must be in the right state
        if self.status != FindingStatus.INDEPENDENTLY_VERIFIED:
            return False

        # Requirement 2: Must have attempted verification
        if self.verification_attempts < 1:
            return False

        # Requirement 3: Must have direct evidence
        if not self.has_direct_evidence():
            return False

        # Requirement 4: No unresolved contradictions
        if self.contradictory_evidence:
            return False

        # Requirement 5: Negative claims require ACTUAL validated ground-truth Evidence
        if self.claim_type in ("ABSENT", "MISSING"):
            from backend.investigation.evidence import EvidenceType

            if self.ground_truth_claim is None:
                raise MissingGroundTruthError(
                    f"Negative claim {self.claim_type} requires ground_truth_claim to be set"
                )

            if self.ground_truth_evidence is None:
                raise MissingGroundTruthError(
                    f"Negative claim {self.claim_type} requires ground_truth_evidence Evidence object (not path)"
                )

            # Ground truth claim must match the negative claim type
            if self.claim_type == "ABSENT" and self.ground_truth_claim != "ABSENT":
                raise MissingGroundTruthError(
                    f"ABSENT claim requires ground_truth_claim='ABSENT', got '{self.ground_truth_claim}'"
                )

            # Ground truth evidence must be DIRECT with sufficient confidence
            if self.ground_truth_evidence.evidence_type != EvidenceType.DIRECT:
                raise MissingGroundTruthError(
                    f"Ground truth evidence must be DIRECT, got {self.ground_truth_evidence.evidence_type.value}"
                )

            if self.ground_truth_evidence.confidence < 0.9:
                raise MissingGroundTruthError(
                    f"Ground truth evidence must have confidence >= 0.9, got {self.ground_truth_evidence.confidence}"
                )

        return True


@dataclass
class FindingPacket:
    """
    Compact finding transmission from scout to main agent.

    Contains only essential information; detailed evidence lives in
    artifact files, not in the main context.

    Safety: is_actionable is derived from status, not set independently.
    """

    finding_id: str
    severity: FindingSeverity
    status: FindingStatus

    # One-paragraph summary
    summary: str

    # Where the evidence lives
    evidence_location: str  # Path to findings/RETRIEVAL-001.md
    data_location: str      # Path to findings/RETRIEVAL-001.json

    # What happens next
    recommended_next_investigation: str

    # Whether main context can act on this
    is_actionable: bool = False
    """Derived from status; True only if status is CONFIRMED."""

    def __post_init__(self):
        """Validate packet consistency."""
        # is_actionable must match status
        expected_actionable = (self.status == FindingStatus.CONFIRMED)
        if self.is_actionable != expected_actionable:
            raise ValueError(
                f"is_actionable must be {expected_actionable} when status={self.status.value}"
            )

        # Summary must not be empty
        if not self.summary or not self.summary.strip():
            raise ValueError("FindingPacket summary cannot be empty")

        # Locations must be provided
        if not self.evidence_location or not self.evidence_location.strip():
            raise ValueError("FindingPacket evidence_location cannot be empty")

        if not self.data_location or not self.data_location.strip():
            raise ValueError("FindingPacket data_location cannot be empty")

    def to_context_string(self) -> str:
        """Format for main agent context (keep < 500 chars per finding)."""
        # Status symbol based on actual status, not is_actionable
        if self.status == FindingStatus.CONFIRMED:
            status_symbol = "✓"
        elif self.status in (FindingStatus.REFUTED, FindingStatus.UNRESOLVED):
            status_symbol = "✗"
        else:
            status_symbol = "⚠"

        return f"""{status_symbol} {self.finding_id} [{self.severity.value}]

{self.summary}

Evidence: {self.evidence_location}
Next: {self.recommended_next_investigation}
"""
