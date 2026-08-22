"""
Phase 8: Failure Diagnosis & Agentic Repair module for GitOnBoard.
"""
from backend.agent.repair.contracts import (
    Defect,
    DiagnosisCategory,
    DiagnosisContext,
    DiagnosisStatus,
    FailureCategory,
    RepairAttempt,
    RepairConfig,
    RepairResult,
    RepairStatus,
)
from backend.agent.repair.diagnosis import FailureDiagnosisController
from backend.agent.repair.limits import RepairAttemptTracker
from backend.agent.repair.repair import RepairController

__all__ = [
    "Defect",
    "DiagnosisCategory",
    "DiagnosisContext",
    "DiagnosisStatus",
    "FailureCategory",
    "RepairAttempt",
    "RepairConfig",
    "RepairResult",
    "RepairStatus",
    "FailureDiagnosisController",
    "RepairAttemptTracker",
    "RepairController",
]
