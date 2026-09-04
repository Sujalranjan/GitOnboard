"""
Multi-Agent Investigation Framework

Enables Claude Code to delegate repository investigations to specialized agents
while keeping main context small and preventing bad test data from cascading
through multiple investigation stages.

Key concepts:
- Scout agents investigate independently
- Ground-truth is independently verified against repository
- Findings must have direct evidence
- Contradictions are actively tested
- Context is minimized for main agent

Safety invariants enforced at creation time:
- State transitions are validated
- Evidence fields are validated
- Ground-truth requirements are enforced
- Confirmation readiness checks are comprehensive
- Ground truth is repository-grounded, never agent-asserted
"""

from backend.investigation.finding import (
    Finding,
    FindingStatus,
    FindingSeverity,
    FindingPacket,
    InvalidFindingStateError,
    MissingGroundTruthError,
)
from backend.investigation.evidence import (
    Evidence,
    EvidenceType,
    InvalidEvidenceError,
)
from backend.investigation.ground_truth import (
    GroundTruthValidator,
    GroundTruthResult,
    VerificationStatus,
)
from backend.investigation.scout import (
    ScoutAgent,
    ScoutHypothesis,
    ScoutStrategy,
)
from backend.investigation.verifier import (
    VerificationAgent,
    VerificationContext,
    VerificationResult,
)

__all__ = [
    "Finding",
    "FindingStatus",
    "FindingSeverity",
    "FindingPacket",
    "InvalidFindingStateError",
    "MissingGroundTruthError",
    "Evidence",
    "EvidenceType",
    "InvalidEvidenceError",
    "GroundTruthValidator",
    "GroundTruthResult",
    "VerificationStatus",
    "ScoutAgent",
    "ScoutHypothesis",
    "ScoutStrategy",
    "VerificationAgent",
    "VerificationContext",
    "VerificationResult",
]
