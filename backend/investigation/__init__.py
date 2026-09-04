"""
Multi-Agent Investigation Framework

Enables Claude Code to delegate repository investigations to specialized agents
while keeping main context small and preventing bad test data from cascading
through multiple investigation stages.

Key concepts:
- Scout agents investigate independently
- Ground-truth is verified before diagnosis
- Findings must have direct evidence
- Contradictions are actively tested
- Context is minimized for main agent

Safety invariants enforced at creation time:
- State transitions are validated
- Evidence fields are validated
- Ground-truth requirements are enforced
- Confirmation readiness checks are comprehensive
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
]
