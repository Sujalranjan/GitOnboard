"""
Contracts and typed domain models for Phase 7 Verification-Driven Execution.

Defines:
  - VerificationType: STATIC, DYNAMIC, CONTRACT, FULL
  - VerificationStatus: PENDING, RUNNING, PASSED, FAILED, SKIPPED, ERROR, CANCELLED
  - DefectSeverity: CRITICAL, HIGH, MEDIUM, LOW
  - DefectCategory: Standard taxonomy for static, dynamic, contract, and syntax defects
  - VerificationCheck: Individual verification step specification
  - VerificationEvidence: Persistent verification evidence envelope with timings, exit codes, and output
  - VerificationDefect: Normalized defect record for Phase 8 diagnosis handoff
  - VerificationStrategy: Task-specific verification plan
  - VerificationResult: Comprehensive aggregate verification result envelope
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VerificationType(str, Enum):
    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"
    CONTRACT = "CONTRACT"
    FULL = "FULL"


class VerificationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class DefectSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DefectCategory(str, Enum):
    STATIC_SYMBOL_MISSING = "STATIC_SYMBOL_MISSING"
    STATIC_IMPORT_MISSING = "STATIC_IMPORT_MISSING"
    DYNAMIC_TEST_FAILURE = "DYNAMIC_TEST_FAILURE"
    DYNAMIC_BUILD_FAILURE = "DYNAMIC_BUILD_FAILURE"
    DYNAMIC_LINT_FAILURE = "DYNAMIC_LINT_FAILURE"
    CONTRACT_OMISSION = "CONTRACT_OMISSION"
    CONTRACT_INVARIANT_VIOLATION = "CONTRACT_INVARIANT_VIOLATION"
    ARCHITECTURE_ERROR = "ARCHITECTURE_ERROR"
    VERIFICATION_TIMEOUT = "VERIFICATION_TIMEOUT"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class VerificationDefect(BaseModel):
    """
    Normalized defect model produced during verification.
    Serves as the structured defect payload consumed by Phase 8 FailureDiagnosisController.
    """
    defect_id: str = Field(default_factory=_uuid, description="Unique identifier of defect")
    type: str = Field(default=DefectCategory.DYNAMIC_TEST_FAILURE.value, description="Defect classification category")
    severity: str = Field(default=DefectSeverity.HIGH.value, description="Severity level")
    message: str = Field(description="Actionable explanation of defect")
    file: Optional[str] = Field(default=None, description="Relative file path containing the defect")
    symbol: Optional[str] = Field(default=None, description="Affected symbol/function/class if known")
    line: Optional[int] = Field(default=None, description="Line number if available")
    command: Optional[str] = Field(default=None, description="Command that revealed the defect")
    stack: Optional[str] = Field(default=None, description="Stack trace or test failure output snippet")
    evidence_id: Optional[str] = Field(default=None, description="Reference to parent VerificationEvidence")


class VerificationCheck(BaseModel):
    """
    Specification of a single verification check in a verification strategy.
    """
    check_id: str = Field(default_factory=_uuid, description="Unique check identifier")
    type: VerificationType = Field(description="Type of check: STATIC, DYNAMIC, CONTRACT, FULL")
    name: str = Field(description="Human-readable name of check")
    command: Optional[str] = Field(default=None, description="Specific terminal command if applicable")
    required: bool = Field(default=True, description="Whether this check is required for PASSED status")
    timeout: float = Field(default=60.0, description="Maximum execution timeout in seconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context parameters")


class VerificationEvidence(BaseModel):
    """
    Concrete persisted verification evidence backing a specific check.
    """
    verification_id: str = Field(description="Parent verification session ID")
    check_id: str = Field(description="ID of check that produced this evidence")
    status: VerificationStatus = Field(description="Check status outcome")
    command: Optional[str] = Field(default=None, description="Executed command")
    exit_code: Optional[int] = Field(default=None, description="Process exit code")
    stdout_summary: Optional[str] = Field(default=None, description="Bounded summary of stdout")
    stderr_summary: Optional[str] = Field(default=None, description="Bounded summary of stderr")
    defects: List[VerificationDefect] = Field(default_factory=list, description="Defects discovered during check")
    duration_ms: float = Field(default=0.0, description="Check execution time in milliseconds")
    timestamp: str = Field(default_factory=_now, description="Timestamp of evidence generation")


class VerificationStrategy(BaseModel):
    """
    Resolved verification strategy for a given task or full plan.
    """
    task_id: str = Field(description="Target task identifier")
    required_types: List[VerificationType] = Field(default_factory=list, description="Required verification vectors")
    checks: List[VerificationCheck] = Field(default_factory=list, description="Ordered verification checks")
    is_final_verification: bool = Field(default=False, description="Whether this is a final plan-level verification")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    """
    Comprehensive aggregate result of running a verification strategy.
    """
    verification_id: str = Field(default_factory=_uuid, description="Unique verification session ID")
    task_id: str = Field(description="Target task identifier")
    status: VerificationStatus = Field(description="Authoritative status: PASSED, FAILED, ERROR, CANCELLED")
    passed: bool = Field(description="True if and only if all required checks passed with valid evidence")
    checks: List[VerificationCheck] = Field(default_factory=list, description="List of checks evaluated")
    passed_checks: List[str] = Field(default_factory=list, description="Names or IDs of checks that passed")
    failed_checks: List[str] = Field(default_factory=list, description="Names or IDs of checks that failed")
    defects: List[VerificationDefect] = Field(default_factory=list, description="All itemized defects discovered")
    evidence: List[VerificationEvidence] = Field(default_factory=list, description="Persisted evidence items")
    duration_ms: float = Field(default=0.0, description="Total verification duration in milliseconds")
    judge_result: Optional[Dict[str, Any]] = Field(default=None, description="Judge synthesis report details")
    summary: str = Field(default="", description="Executive summary of verification verdict")
