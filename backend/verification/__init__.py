"""
Multi-Vector Verification Mesh for GitOnBoard.

Submodules:
  - schemas: Pydantic data models for Defects, VerificationResults, and VerificationReports.
  - static_verifier: AST symbol, import, and package manifest checker.
  - dynamic_verifier: Test execution (pytest/jest), linting, and type checking runner.
  - contract_verifier: Implementation Contract coverage and invariant verifier.
  - judge: Aggregates multi-vector evidence into structured VerificationReports.
  - orchestrator: Full end-to-end task lifecycle, sandboxed execution, and repair loop manager.
"""
from .schemas import (
    DefectSeverity,
    DefectCategory,
    Defect,
    ExecutionState,
    VerificationResult,
    VerificationReport,
)
from .static_verifier import StaticVerifier
from .dynamic_verifier import DynamicVerifier
from .contract_verifier import ContractVerifier
from .judge import Judge
from .orchestrator import VerificationOrchestrator

__all__ = [
    "DefectSeverity",
    "DefectCategory",
    "Defect",
    "ExecutionState",
    "VerificationResult",
    "VerificationReport",
    "StaticVerifier",
    "DynamicVerifier",
    "ContractVerifier",
    "Judge",
    "VerificationOrchestrator",
]
