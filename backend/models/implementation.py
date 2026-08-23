"""
SQLAlchemy models for the AI Implementation Subsystem (Version 4).

Tables:
  - implementations          : Core workflow state machine
  - implementation_contracts : Ground-truth verification contracts
  - implementation_plans     : Step-by-step actionable plan with traceability
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, Enum as SAEnum, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum

from backend.database import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────

class ImplementationStatus(str, Enum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    PLANNING = "PLANNING"
    NEEDS_CONTEXT = "NEEDS_CONTEXT"  # Insufficient retrieval; awaiting extra context
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    PR_CREATED = "PR_CREATED"


class PlanStepStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ComponentType(str, Enum):
    EXISTING = "EXISTING"  # Symbol/file confirmed in the RIM database
    NEW = "NEW"            # Symbol/file to be created by the agent


class AgentState(str, Enum):
    """
    Authoritative granular lifecycle state of an EngineeringAgent session.

    Initial Phase 1 States:
      IDLE ──► UNDERSTANDING ──► PLANNING ──► AWAITING_APPROVAL ──► EXECUTING ──► VERIFYING ──► COMPLETED
                                                                                               └──► FAILED
                                                                                               └──► CANCELLED (Terminal)
    """
    IDLE = "IDLE"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentRunStatus(str, Enum):
    """Coarse legacy status kept in sync for backward-compatible pipeline queries."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def map_agent_state_to_legacy_status(state: AgentState | str) -> AgentRunStatus:
    """
    Deterministic mapping from authoritative granular AgentState to coarse AgentRunStatus.
    """
    val = state.value if isinstance(state, AgentState) else str(state)
    if val == AgentState.IDLE.value:
        return AgentRunStatus.QUEUED
    elif val in (
        AgentState.UNDERSTANDING.value,
        AgentState.PLANNING.value,
        AgentState.AWAITING_APPROVAL.value,
        AgentState.EXECUTING.value,
    ):
        return AgentRunStatus.RUNNING
    elif val == AgentState.VERIFYING.value:
        return AgentRunStatus.VERIFYING
    elif val == AgentState.COMPLETED.value:
        return AgentRunStatus.COMPLETED
    elif val in (AgentState.FAILED.value, AgentState.CANCELLED.value):
        return AgentRunStatus.FAILED
    return AgentRunStatus.RUNNING


class AgentEventType(str, Enum):
    STARTED = "STARTED"
    STATE_TRANSITION = "STATE_TRANSITION"
    CONTRACT_GENERATED = "CONTRACT_GENERATED"
    CODE_GENERATING = "CODE_GENERATING"
    ACTION_STARTED = "ACTION_STARTED"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    TOOL_CALL_STARTED = "TOOL_CALL_STARTED"
    TOOL_CALL_COMPLETED = "TOOL_CALL_COMPLETED"
    TOOL_CALL_FAILED = "TOOL_CALL_FAILED"
    TOOL_CALL_BLOCKED = "TOOL_CALL_BLOCKED"
    TOOL_CALL_APPROVAL_REQUIRED = "TOOL_CALL_APPROVAL_REQUIRED"
    CONTEXT_ASSEMBLY_STARTED = "CONTEXT_ASSEMBLY_STARTED"
    CONTEXT_ASSEMBLY_COMPLETED = "CONTEXT_ASSEMBLY_COMPLETED"
    CONTEXT_ASSEMBLY_FAILED = "CONTEXT_ASSEMBLY_FAILED"
    INTENT_CLASSIFIED = "INTENT_CLASSIFIED"
    AGENT_MESSAGE = "AGENT_MESSAGE"
    PLANNING_STARTED = "PLANNING_STARTED"
    PLANNING_COMPLETED = "PLANNING_COMPLETED"
    PLANNING_FAILED = "PLANNING_FAILED"
    PLAN_READY_FOR_APPROVAL = "PLAN_READY_FOR_APPROVAL"
    PLAN_APPROVED = "PLAN_APPROVED"
    PLAN_REJECTED = "PLAN_REJECTED"
    NEXT_TASK_SELECTED = "NEXT_TASK_SELECTED"
    TASK_READY = "TASK_READY"
    TASK_STARTED = "TASK_STARTED"
    AGENT_TASK_STARTED = "AGENT_TASK_STARTED"
    AGENT_THINKING = "AGENT_THINKING"
    AGENT_TOOL_REQUESTED = "AGENT_TOOL_REQUESTED"
    AGENT_LIMIT_WARNING = "AGENT_LIMIT_WARNING"
    AGENT_COMPLETION_REQUESTED = "AGENT_COMPLETION_REQUESTED"
    AGENT_LOOP_STOPPED = "AGENT_LOOP_STOPPED"
    AGENT_TASK_READY_FOR_VERIFICATION = "AGENT_TASK_READY_FOR_VERIFICATION"
    TASK_EXECUTION_COMPLETED = "TASK_EXECUTION_COMPLETED"
    TASK_EXECUTION_FAILED = "TASK_EXECUTION_FAILED"
    TASK_VERIFYING = "TASK_VERIFYING"
    TASK_PASSED = "TASK_PASSED"
    TASK_FAILED = "TASK_FAILED"
    TASK_BLOCKED = "TASK_BLOCKED"
    TASK_SKIPPED = "TASK_SKIPPED"
    FILE_WRITTEN = "FILE_WRITTEN"

    DIFF_CAPTURED = "DIFF_CAPTURED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_CHECK_STARTED = "VERIFICATION_CHECK_STARTED"
    VERIFICATION_CHECK_COMPLETED = "VERIFICATION_CHECK_COMPLETED"
    VERIFICATION_CHECK_FAILED = "VERIFICATION_CHECK_FAILED"
    VERIFICATION_DEFECT_FOUND = "VERIFICATION_DEFECT_FOUND"
    VERIFICATION_JUDGE_STARTED = "VERIFICATION_JUDGE_STARTED"
    VERIFICATION_JUDGE_COMPLETED = "VERIFICATION_JUDGE_COMPLETED"
    VERIFICATION_PASSED = "VERIFICATION_PASSED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    
    # Phase 8 Diagnosis & Repair Events
    DIAGNOSIS_STARTED = "DIAGNOSIS_STARTED"
    DIAGNOSIS_CONTEXT_ASSEMBLED = "DIAGNOSIS_CONTEXT_ASSEMBLED"
    DIAGNOSIS_EVIDENCE_FOUND = "DIAGNOSIS_EVIDENCE_FOUND"
    REPAIR_STARTED = "REPAIR_STARTED"
    REPAIR_ATTEMPT_STARTED = "REPAIR_ATTEMPT_STARTED"
    REPAIR_ATTEMPT_COMPLETED = "REPAIR_ATTEMPT_COMPLETED"
    REPAIR_REVERIFY_STARTED = "REPAIR_REVERIFY_STARTED"
    REPAIR_REVERIFY_COMPLETED = "REPAIR_REVERIFY_COMPLETED"
    REPAIR_PASSED = "REPAIR_PASSED"
    REPAIR_FAILED = "REPAIR_FAILED"
    REPAIR_LIMIT_WARNING = "REPAIR_LIMIT_WARNING"
    REPAIR_BLOCKED = "REPAIR_BLOCKED"

    # Phase 9 Safety, Approval & Cancellation Events
    ACTION_APPROVAL_REQUESTED = "ACTION_APPROVAL_REQUESTED"
    ACTION_APPROVED = "ACTION_APPROVED"
    ACTION_REJECTED = "ACTION_REJECTED"
    ACTION_EXPIRED = "ACTION_EXPIRED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLATION_COMPLETED = "CANCELLATION_COMPLETED"
    
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PolicyAction(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ApprovalActionType(str, Enum):
    PLAN_APPROVAL = "PLAN_APPROVAL"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    TERMINAL_COMMAND = "TERMINAL_COMMAND"
    GIT_OPERATION = "GIT_OPERATION"
    FILE_MODIFICATION = "FILE_MODIFICATION"


class FileChangeType(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class Implementation(Base):
    """
    Core state-machine entity tracking an AI-assisted implementation request.
    """
    __tablename__ = "implementations"

    id = Column(String, primary_key=True, default=_uuid)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String, nullable=False)
    raw_requirement = Column(Text, nullable=False)
    branch_name = Column(String, nullable=True)           # e.g. "feature/google-oauth"
    worktree_path = Column(String, nullable=True)         # /worktrees/<id>

    status = Column(
        SAEnum(ImplementationStatus, name="implementation_status"),
        nullable=False,
        default=ImplementationStatus.QUEUED,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    # Relationships
    contract = relationship(
        "ImplementationContract",
        back_populates="implementation",
        uselist=False,
        cascade="all, delete-orphan",
    )
    plan_steps = relationship(
        "ImplementationPlan",
        back_populates="implementation",
        cascade="all, delete-orphan",
        order_by="ImplementationPlan.step_number",
    )

    def __repr__(self) -> str:
        return f"<Implementation id={self.id!r} title={self.title!r} status={self.status!r}>"


class ImplementationContract(Base):
    """
    Ground-truth verification contract synthesized from the requirement and evidence.

    evidence_manifest: List of deterministic evidence items (EVID-001, EVID-002...)
    affected_components: List of dicts { file, symbol, component_type, evidence_ids }
    """
    __tablename__ = "implementation_contracts"

    id = Column(String, primary_key=True, default=_uuid)
    implementation_id = Column(
        String, ForeignKey("implementations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # Core contract fields
    acceptance_criteria = Column(JSONType, nullable=False, default=list)  # ["AC-01: ...", "AC-02: ..."]
    affected_components = Column(JSONType, nullable=False, default=list)   # [{file, symbol, component_type, evidence_ids}]
    evidence_manifest = Column(JSONType, nullable=False, default=list)     # [{id, source, file, symbol, similarity, rim_rel}]
    tests_required = Column(JSONType, nullable=False, default=list)        # ["Test OAuth callback returns 200", ...]
    security_considerations = Column(JSONType, nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    implementation = relationship("Implementation", back_populates="contract")

    def __repr__(self) -> str:
        return f"<ImplementationContract impl={self.implementation_id!r} criteria={len(self.acceptance_criteria or [])}>"


class ImplementationPlan(Base):
    """
    A single ordered step in the implementation plan.

    Traceability chain:
        Requirement -> AC-01 -> plan_step -> affected_symbol -> evidence_ids
    """
    __tablename__ = "implementation_plans"

    id = Column(String, primary_key=True, default=_uuid)
    implementation_id = Column(
        String, ForeignKey("implementations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    step_number = Column(Integer, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    # Traceability
    target_files = Column(JSONType, nullable=False, default=list)         # ["auth/routes.py"]
    affected_symbols = Column(JSONType, nullable=False, default=list)     # ["handle_google_callback"]
    component_type = Column(
        SAEnum(ComponentType, name="component_type"),
        nullable=False,
        default=ComponentType.EXISTING,
    )
    acceptance_criteria = Column(JSONType, nullable=False, default=list)  # ["AC-01", "AC-02"]
    evidence_ids = Column(JSONType, nullable=False, default=list)         # ["EVID-001", "EVID-002"]
    expected_changes = Column(Text, nullable=True)
    dependencies = Column(JSONType, nullable=False, default=list)         # [1, 2] (step_numbers of deps)

    status = Column(
        SAEnum(PlanStepStatus, name="plan_step_status"),
        nullable=False,
        default=PlanStepStatus.PENDING,
        index=True,
    )

    implementation = relationship("Implementation", back_populates="plan_steps")

    def __repr__(self) -> str:
        return f"<ImplementationPlan step={self.step_number} title={self.title!r} type={self.component_type!r}>"


class AgentRun(Base):
    """
    A single execution of the Engineering Agent / Coding Agent session.

    AUTHORITY HIERARCHY:
      - `current_state` (AgentState) is the AUTHORITATIVE granular state of the agent run.
      - `status` (AgentRunStatus) is a coarse legacy status kept in sync for backward compatibility.
    """
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=_uuid)
    implementation_id = Column(
        String, ForeignKey("implementations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    task_id = Column(String, nullable=False, index=True)
    repository_id = Column(String, nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_requirement = Column(Text, nullable=True)

    # Authoritative granular state
    current_state = Column(
        SAEnum(AgentState, native_enum=False),
        nullable=False,
        default=AgentState.IDLE,
        index=True,
    )

    # Coarse legacy status
    status = Column(
        SAEnum(AgentRunStatus, native_enum=False),
        nullable=False,
        default=AgentRunStatus.QUEUED,
        index=True,
    )
    iteration = Column(Integer, nullable=False, default=1)
    worktree_path = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONType, nullable=True, default=dict)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    started_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    events = relationship(
        "AgentEvent", back_populates="agent_run", cascade="all, delete-orphan",
        order_by="AgentEvent.created_at",
    )
    file_changes = relationship(
        "FileChange", back_populates="agent_run", cascade="all, delete-orphan",
    )
    transitions = relationship(
        "AgentStateTransition", back_populates="agent_run", cascade="all, delete-orphan",
        order_by="AgentStateTransition.timestamp",
    )
    approvals = relationship(
        "ApprovalRequest", back_populates="agent_run", cascade="all, delete-orphan",
        order_by="ApprovalRequest.requested_at",
    )
    policy_decisions = relationship(
        "PolicyDecisionRecord", back_populates="agent_run", cascade="all, delete-orphan",
        order_by="PolicyDecisionRecord.created_at",
    )
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<AgentRun id={self.id!r} state={self.current_state.value!r} status={self.status.value!r}>"


class ApprovalRequest(Base):
    """
    Durable, first-class human approval request.
    Created when policy evaluates to APPROVAL_REQUIRED or when a plan requires approval.
    """
    __tablename__ = "approval_requests"

    id = Column(String, primary_key=True, default=_uuid)
    agent_run_id = Column(
        String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id = Column(String, nullable=True, index=True)
    tool_call_id = Column(String, nullable=True)

    action_type = Column(
        SAEnum(ApprovalActionType, name="approval_action_type"),
        nullable=False,
        default=ApprovalActionType.TOOL_EXECUTION,
        index=True,
    )
    action_description = Column(Text, nullable=False)
    risk_level = Column(
        SAEnum(RiskLevel, name="risk_level"),
        nullable=False,
        default=RiskLevel.MEDIUM,
        index=True,
    )
    requested_operation = Column(JSONType, nullable=False, default=dict)
    affected_files = Column(JSONType, nullable=False, default=list)
    command = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)

    status = Column(
        SAEnum(ApprovalStatus, name="approval_status"),
        nullable=False,
        default=ApprovalStatus.PENDING,
        index=True,
    )
    requested_at = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONType, nullable=True, default=dict)

    agent_run = relationship("AgentRun", back_populates="approvals")

    def __repr__(self) -> str:
        return f"<ApprovalRequest id={self.id!r} action={self.action_type.value} risk={self.risk_level.value} status={self.status.value}>"


class PolicyDecisionRecord(Base):
    """
    Append-only audit record of safety policy decisions.
    Answers: 'Why was this command blocked / required approval?'
    """
    __tablename__ = "policy_decisions"

    id = Column(String, primary_key=True, default=_uuid)
    agent_run_id = Column(
        String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id = Column(String, nullable=True, index=True)
    tool_call_id = Column(String, nullable=True)
    tool_name = Column(String, nullable=False)
    arguments_summary = Column(Text, nullable=True)
    decision = Column(
        SAEnum(PolicyAction, name="policy_action_decision"),
        nullable=False,
        index=True,
    )
    risk_level = Column(
        SAEnum(RiskLevel, name="policy_risk_level"),
        nullable=False,
        default=RiskLevel.LOW,
    )
    reason = Column(Text, nullable=True)
    policy_version = Column(String, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    metadata_json = Column("metadata", JSONType, nullable=True, default=dict)

    agent_run = relationship("AgentRun", back_populates="policy_decisions")

    def __repr__(self) -> str:
        return f"<PolicyDecisionRecord id={self.id!r} tool={self.tool_name!r} decision={self.decision.value}>"


class AgentStateTransition(Base):
    """
    Append-only audit log of state transitions for an AgentRun.
    """
    __tablename__ = "agent_state_transitions"

    id = Column(String, primary_key=True, default=_uuid)
    agent_run_id = Column(
        String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_state = Column(SAEnum(AgentState, native_enum=False), nullable=False)
    to_state = Column(SAEnum(AgentState, native_enum=False), nullable=False)
    reason = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONType, nullable=True, default=dict)
    timestamp = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)

    agent_run = relationship("AgentRun", back_populates="transitions")

    def __repr__(self) -> str:
        return f"<AgentStateTransition run={self.agent_run_id!r} {self.from_state.value} -> {self.to_state.value}>"


class AgentEvent(Base):
    """An append-only progress event emitted during an AgentRun's execution."""
    __tablename__ = "agent_events"

    id = Column(String, primary_key=True, default=_uuid)
    agent_run_id = Column(
        String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_type = Column(SAEnum(AgentEventType, native_enum=False), nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(JSONType, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)

    agent_run = relationship("AgentRun", back_populates="events")

    def __repr__(self) -> str:
        return f"<AgentEvent run={self.agent_run_id!r} type={self.event_type!r}>"


class FileChange(Base):
    """A single file's change, parsed from an AgentRun's captured git diff."""
    __tablename__ = "file_changes"

    id = Column(String, primary_key=True, default=_uuid)
    agent_run_id = Column(
        String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    file_path = Column(String, nullable=False)
    change_type = Column(SAEnum(FileChangeType, name="file_change_type"), nullable=False)
    lines_added = Column(Integer, nullable=False, default=0)
    lines_removed = Column(Integer, nullable=False, default=0)
    diff_patch = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    agent_run = relationship("AgentRun", back_populates="file_changes")

    def __repr__(self) -> str:
        return f"<FileChange run={self.agent_run_id!r} path={self.file_path!r} type={self.change_type!r}>"
