"""
Evidence classification and artifact schemas for investigations.

Evidence quality determines whether findings can be confirmed.
Only DIRECT evidence is sufficient for repository facts.

Safety invariants enforced:
1. Evidence fields are validated on creation
2. Retrieval zero-results is NOT repository ground truth
3. Confidence bounds are enforced (0.0-1.0)
4. UNVERIFIED evidence never appears as DIRECT
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class InvalidEvidenceError(ValueError):
    """Raised when Evidence is created with invalid parameters."""
    pass


class EvidenceType(str, Enum):
    """Classification of evidence quality."""

    DIRECT = "DIRECT"
    """
    Evidence from actual observation of the system state.
    Examples: source code, parser output, RIM record, retrieval result.
    Sufficient for confirmation.
    """

    INDIRECT = "INDIRECT"
    """
    Evidence about the relationship or properties of direct observations.
    Examples: test results, execution traces, audit logs.
    Generally sufficient for confirmation if multiple pieces align.
    """

    INFERRED = "INFERRED"
    """
    Logic or reasoning about what should be true given other evidence.
    Examples: "X was not found, so parser must not extract it".
    NOT sufficient alone; requires direct evidence of the actual state.
    """

    UNVERIFIED = "UNVERIFIED"
    """
    Claims made by other agents or test fixtures without direct verification.
    Examples: "Phase 8A.6 reported 50% false-negative rate".
    NOT sufficient; requires independent verification.
    """


@dataclass
class Evidence:
    """
    A single piece of evidence supporting or refuting a finding.

    All fields are validated on creation to prevent invalid evidence states.
    """

    # Classification
    evidence_type: EvidenceType
    """Quality/type of evidence (DIRECT, INDIRECT, INFERRED, UNVERIFIED)."""

    # Source
    source: str
    """
    What generated this evidence.
    Examples: "source code", "parser output", "RIM database",
    "search API", "test fixture", "agent report"
    """

    location: str
    """
    Where the evidence can be found.
    Format: file_path:line_number or path or URL
    """

    # Content
    observation: str
    """
    What was actually observed or tested.
    """

    # Confidence
    confidence: float
    """
    Confidence in this evidence (0.0 - 1.0).
    DIRECT evidence: 0.9-1.0
    INDIRECT evidence: 0.6-0.9
    INFERRED evidence: 0.3-0.7
    UNVERIFIED evidence: 0.0-0.5
    """

    # Context
    context: Optional[str] = None
    """Additional context about how this evidence was obtained."""

    contradicts: Optional[str] = None
    """Evidence ID this contradicts, if applicable."""

    def __post_init__(self):
        """Validate evidence fields on creation."""
        # Validate required fields are not empty
        if not self.source or not self.source.strip():
            raise InvalidEvidenceError("Evidence source cannot be empty")

        if not self.location or not self.location.strip():
            raise InvalidEvidenceError("Evidence location cannot be empty")

        if not self.observation or not self.observation.strip():
            raise InvalidEvidenceError("Evidence observation cannot be empty")

        # Validate confidence bounds
        if not (0.0 <= self.confidence <= 1.0):
            raise InvalidEvidenceError(
                f"Evidence confidence must be 0.0-1.0, got {self.confidence}"
            )

        # Validate confidence matches evidence type expectations
        if self.evidence_type == EvidenceType.DIRECT and self.confidence < 0.9:
            raise InvalidEvidenceError(
                f"DIRECT evidence requires confidence >= 0.9, got {self.confidence}"
            )

        if self.evidence_type == EvidenceType.INDIRECT and not (0.5 <= self.confidence < 0.9):
            raise InvalidEvidenceError(
                f"INDIRECT evidence should have confidence 0.5-0.9, got {self.confidence}"
            )

        if self.evidence_type == EvidenceType.INFERRED and not (0.3 <= self.confidence < 0.7):
            raise InvalidEvidenceError(
                f"INFERRED evidence should have confidence 0.3-0.7, got {self.confidence}"
            )

        if self.evidence_type == EvidenceType.UNVERIFIED and self.confidence > 0.5:
            raise InvalidEvidenceError(
                f"UNVERIFIED evidence should have confidence <= 0.5, got {self.confidence}"
            )

    @classmethod
    def from_source_code(cls, file_path: str, symbol: str, line: int = 0) -> "Evidence":
        """Create DIRECT evidence from source code."""
        return cls(
            evidence_type=EvidenceType.DIRECT,
            source="source code",
            location=f"{file_path}:{line}" if line else file_path,
            observation=f"Symbol '{symbol}' found in source",
            confidence=0.95,
        )

    @classmethod
    def from_parser_output(cls, file_path: str, extracted: bool) -> "Evidence":
        """Create DIRECT evidence from parser execution."""
        return cls(
            evidence_type=EvidenceType.DIRECT,
            source="parser output",
            location=file_path,
            observation=f"Parser {'extracted' if extracted else 'did not extract'} symbol",
            confidence=1.0,
        )

    @classmethod
    def from_retrieval_result(cls, query: str, found: bool, result_count: int = 0) -> "Evidence":
        """
        Create INDIRECT evidence from retrieval API.

        IMPORTANT: Retrieval zero-results is NOT direct evidence of repository absence.
        It is INDIRECT evidence of retrieval behavior.

        Retrieval zero-results can mean:
        - Entity does not exist in repository (one possibility)
        - Entity exists but is not indexed (another possibility)
        - Entity exists but retrieval filtering excluded it (another possibility)

        Therefore, this is INDIRECT evidence, not DIRECT repository truth.
        """
        return cls(
            evidence_type=EvidenceType.INDIRECT,
            source="search API",
            location="search_repository endpoint",
            observation=f"Search for '{query}' returned {result_count} results" if found else f"Search for '{query}' returned no results",
            confidence=0.7 if found else 0.5,  # Found is stronger; not-found is weaker
            context="Retrieval result is evidence of search behavior, not repository state",
        )

    @classmethod
    def from_test_fixture(cls, fixture_name: str, claim: str, unverified: bool = True) -> "Evidence":
        """Create UNVERIFIED evidence from test fixture."""
        return cls(
            evidence_type=EvidenceType.UNVERIFIED,
            source="test fixture",
            location=fixture_name,
            observation=claim,
            confidence=0.3 if unverified else 0.5,
            context="Test fixture; requires independent verification against actual repository",
        )

    @classmethod
    def from_agent_report(cls, agent_name: str, finding: str, confidence_hint: float = 0.4) -> "Evidence":
        """Create UNVERIFIED evidence from another agent."""
        return cls(
            evidence_type=EvidenceType.UNVERIFIED,
            source="agent report",
            location=f"Agent: {agent_name}",
            observation=finding,
            confidence=confidence_hint,
            context="Agent report; not direct observation",
        )

    def is_sufficient_for_confirmation(self) -> bool:
        """Check if this single evidence piece is sufficient for confirmation."""
        # DIRECT evidence with high confidence is sufficient
        if self.evidence_type == EvidenceType.DIRECT and self.confidence >= 0.9:
            return True
        # INDIRECT can be sufficient if multiple pieces align (checked elsewhere)
        # INFERRED and UNVERIFIED never sufficient alone
        return False

    def __str__(self) -> str:
        return f"[{self.evidence_type.value}] {self.source}: {self.observation} ({self.confidence:.0%})"
