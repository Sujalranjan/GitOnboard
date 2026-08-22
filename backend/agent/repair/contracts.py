"""
Phase 8 Repair Contracts & Data Models for GitOnBoard Engineering Agent.

Defines the typed models for:
  - RepairStatus & DiagnosisStatus enums
  - FailureCategory enum
  - Normalized Defect model
  - DiagnosisContext (structured agent diagnosis input)
  - RepairAttempt (per-cycle attempt record)
  - RepairResult (structured repair completion and verification outcome)
  - RepairConfig (bounded limits and timeouts)
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.agent.verification.contracts import (
    DefectCategory,
    DefectSeverity,
    VerificationDefect,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
)


def _generate_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RepairStatus(str, Enum):
    """Lifecycle status of a repair attempt or session."""
    NOT_STARTED = "NOT_STARTED"
    DIAGNOSING = "DIAGNOSING"
    REPAIRING = "REPAIRING"
    REVERIFYING = "REVERIFYING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class DiagnosisStatus(str, Enum):
    """Status of defect diagnosis analysis."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    UNRESOLVED = "UNRESOLVED"


class FailureCategory(str, Enum):
    """Normalized classification of failure origins."""
    SYNTAX_ERROR = "SYNTAX_ERROR"
    TYPE_ERROR = "TYPE_ERROR"
    TEST_FAILURE = "TEST_FAILURE"
    CONTRACT_FAILURE = "CONTRACT_FAILURE"
    STATIC_FAILURE = "STATIC_FAILURE"
    RUNTIME_FAILURE = "RUNTIME_FAILURE"
    COMMAND_FAILURE = "COMMAND_FAILURE"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


# Alias for backward/forward naming compatibility
DiagnosisCategory = FailureCategory


class RepairConfig(BaseModel):
    """Configuration limits for bounded self-repair loops."""
    max_repair_attempts: int = Field(default=3, description="Maximum number of repair attempts before blocking")
    max_agent_iterations_per_attempt: int = Field(default=10, description="Max agent turns per repair attempt")
    max_repair_duration_sec: float = Field(default=300.0, description="Overall timeout across repair cycles in seconds")
    max_repeated_failure_signatures: int = Field(default=2, description="Max consecutive identical failure/diff signatures before blocking")
    fail_fast: bool = Field(default=True, description="Stop re-verification on first failing vector")


class Defect(BaseModel):
    """
    Normalized failure / defect representation for structured diagnosis.
    Prevents the LLM from parsing raw backend exception traces directly.
    """
    defect_id: str = Field(default_factory=_generate_id, description="Unique defect identifier")
    task_id: str = Field(description="Associated task ID")
    verification_id: Optional[str] = Field(default=None, description="Verification run ID that surfaced this defect")
    category: FailureCategory = Field(default=FailureCategory.UNKNOWN, description="Normalized failure classification")
    severity: DefectSeverity = Field(default=DefectSeverity.HIGH, description="Defect severity level")
    message: str = Field(description="Clear, actionable error description")
    command: Optional[str] = Field(default=None, description="Command that produced the failure, if applicable")
    exit_code: Optional[int] = Field(default=None, description="Process exit code if command executed")
    stdout_summary: Optional[str] = Field(default=None, description="Bounded stdout snippet")
    stderr_summary: Optional[str] = Field(default=None, description="Bounded stderr / traceback snippet")
    stack_trace: Optional[str] = Field(default=None, description="Normalized stack trace or error location")
    affected_files: List[str] = Field(default_factory=list, description="Files implicated in this defect")
    affected_symbols: List[str] = Field(default_factory=list, description="Symbols implicated in this defect")
    expected_behavior: Optional[str] = Field(default=None, description="Expected invariant or acceptance criterion")
    actual_behavior: Optional[str] = Field(default=None, description="Observed failing behavior")
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Associated raw or parsed evidence objects")
    created_at: str = Field(default_factory=_now_iso, description="ISO timestamp of defect capture")


class DiagnosisContext(BaseModel):
    """
    Structured diagnosis context delivered to the Engineering Agent.
    Transforms raw verification failures into actionable investigation evidence.
    """
    diagnosis_id: str = Field(default_factory=_generate_id, description="Unique diagnosis identifier")
    task_id: str = Field(description="Task being diagnosed and repaired")
    task_title: str = Field(default="", description="Title of the task")
    task_description: str = Field(default="", description="Description of the task")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Original acceptance criteria to satisfy")
    defects: List[Defect] = Field(default_factory=list, description="Normalized defects to address")
    primary_category: FailureCategory = Field(default=FailureCategory.UNKNOWN, description="Primary failure classification")
    affected_files: List[str] = Field(default_factory=list, description="Deduplicated list of affected files")
    affected_symbols: List[str] = Field(default_factory=list, description="Deduplicated list of affected symbols")
    failing_commands: List[str] = Field(default_factory=list, description="Commands that failed during verification")
    failing_checks: List[str] = Field(default_factory=list, description="Names of verification checks that failed")
    repository_context_summary: Optional[str] = Field(default=None, description="Targeted repository evidence summary")
    repair_attempt_number: int = Field(default=1, description="Current repair attempt index (1-based)")
    repair_constraints: List[str] = Field(
        default_factory=lambda: [
            "Investigate files and symbols using repository tools before modifying.",
            "Make minimal, targeted edits strictly addressing the diagnosed defects.",
            "Do NOT remove or weaken acceptance criteria or disable tests.",
            "Ensure all syntax, type signatures, and import relationships remain valid.",
        ],
        description="Operational constraints for the repair agent",
    )
    known_evidence_summary: str = Field(default="", description="Fact-based summary of confirmed evidence")
    created_at: str = Field(default_factory=_now_iso, description="Timestamp of diagnosis context creation")


class RepairAttempt(BaseModel):
    """
    Durable record of a single repair cycle.
    Persisted to provide a full audit trail without private chain-of-thought.
    """
    attempt_id: str = Field(default_factory=_generate_id, description="Unique repair attempt ID")
    task_id: str = Field(description="Associated task ID")
    attempt_number: int = Field(default=1, description="Attempt number (1-based)")
    diagnosis_id: str = Field(description="Associated diagnosis ID")
    status: RepairStatus = Field(default=RepairStatus.NOT_STARTED, description="Lifecycle status of attempt")
    defect_ids: List[str] = Field(default_factory=list, description="IDs of defects targeted in this attempt")
    changed_files: List[str] = Field(default_factory=list, description="Files modified during this attempt")
    diff: Optional[str] = Field(default=None, description="Unified diff generated in this attempt")
    verification_id: Optional[str] = Field(default=None, description="Verification run ID evaluating this repair")
    verification_status: Optional[str] = Field(default=None, description="Verification verdict (PASSED/FAILED)")
    failure_reason: Optional[str] = Field(default=None, description="Reason if attempt failed or blocked")
    started_at: str = Field(default_factory=_now_iso, description="Start timestamp")
    completed_at: Optional[str] = Field(default=None, description="Completion timestamp")
    stop_reason: Optional[str] = Field(default=None, description="Stop reason from agent loop")


class RepairResult(BaseModel):
    """
    Overall outcome of the repair orchestration for a task.
    """
    task_id: str = Field(description="Task identifier")
    status: RepairStatus = Field(description="Final repair status (PASSED, FAILED, BLOCKED, CANCELLED)")
    passed: bool = Field(default=False, description="True if task successfully repaired and re-verified")
    diagnosis_id: Optional[str] = Field(default=None, description="Latest diagnosis ID")
    attempts_used: int = Field(default=0, description="Total repair attempts executed")
    max_attempts: int = Field(default=3, description="Configured maximum repair attempts")
    changed_files: List[str] = Field(default_factory=list, description="All files modified across repairs")
    diff: Optional[str] = Field(default=None, description="Cumulative unified diff of final state")
    verification_result: Optional[VerificationResult] = Field(default=None, description="Final verification result")
    history: List[RepairAttempt] = Field(default_factory=list, description="Chronological attempt records")
    stop_reason: Optional[str] = Field(default=None, description="Reason repair halted")
    summary: str = Field(default="", description="Executive summary of the repair outcome")
