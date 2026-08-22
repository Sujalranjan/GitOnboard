"""
Phase 7 Verification-Driven Execution Subsystem.

Exports:
  - Contracts & Enums: VerificationType, VerificationStatus, DefectSeverity, DefectCategory,
                       VerificationCheck, VerificationEvidence, VerificationDefect,
                       VerificationStrategy, VerificationResult
  - Engine & Services: VerificationStrategyResolver, VerificationEvidenceCollector,
                       VerificationResultAggregator, VerificationDispatcher
"""
from backend.agent.verification.contracts import (
    DefectCategory,
    DefectSeverity,
    VerificationCheck,
    VerificationDefect,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
    VerificationStrategy,
    VerificationType,
)
from backend.agent.verification.dispatcher import VerificationDispatcher
from backend.agent.verification.evidence import VerificationEvidenceCollector
from backend.agent.verification.result import VerificationResultAggregator
from backend.agent.verification.strategy import VerificationStrategyResolver

__all__ = [
    "VerificationType",
    "VerificationStatus",
    "DefectSeverity",
    "DefectCategory",
    "VerificationCheck",
    "VerificationEvidence",
    "VerificationDefect",
    "VerificationStrategy",
    "VerificationResult",
    "VerificationStrategyResolver",
    "VerificationEvidenceCollector",
    "VerificationResultAggregator",
    "VerificationDispatcher",
]
