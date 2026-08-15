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


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class Implementation(Base):
    """
    Core state-machine entity tracking an AI-assisted implementation request.
    """
    __tablename__ = "implementations"

    id = Column(String, primary_key=True, default=_uuid)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
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
