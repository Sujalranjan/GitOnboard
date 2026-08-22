"""
Planning Contracts & Data Structures for GitOnBoard Engineering Agent.

Defines the typed models for:
  - PlanStatus & PlanTaskStatus enums
  - PlanTask (individual task in the DAG with dependencies, affected files, criteria, and verification strategy)
  - PlanValidationResult (structured outcome of PlanValidator)
  - Plan (complete validated plan artifact with bounded summaries)
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class PlanStatus(str, Enum):
    """Lifecycle status of a synthesized implementation plan."""
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INVALID = "INVALID"


class PlanTaskStatus(str, Enum):
    """Lifecycle status of an individual task in a plan."""
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    DIAGNOSING = "DIAGNOSING"
    REPAIRING = "REPAIRING"
    REVERIFYING = "REVERIFYING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class PlanTask(BaseModel):
    """
    An individual actionable task within the implementation plan DAG.
    """
    task_id: str = Field(description="Unique task identifier, e.g. 'task-1'")
    step_number: int = Field(default=1, description="Sequential step index")
    title: str = Field(description="Short human-readable summary of the task")
    description: str = Field(description="Detailed technical description of the task actions")
    status: PlanTaskStatus = Field(default=PlanTaskStatus.PENDING, description="Task lifecycle status")
    dependencies: List[str] = Field(default_factory=list, description="IDs of tasks that must complete before this task")
    affected_files: List[str] = Field(default_factory=list, description="Files expected to be created or modified")
    affected_symbols: List[str] = Field(default_factory=list, description="Symbols expected to be added or modified")
    component_type: str = Field(default="EXISTING", description="'EXISTING' or 'NEW'")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Measurable criteria confirming task success")
    verification_strategy: str = Field(default="verify_static", description="Targeted verification tool or test approach")
    evidence_ids: List[str] = Field(default_factory=list, description="Referenced evidence IDs supporting this task")
    attempt_count: int = Field(default=0, description="Number of execution attempts")
    failure_reason: Optional[str] = Field(default=None, description="Detailed explanation if task failed")
    blocked_reason: Optional[str] = Field(default=None, description="Upstream failure explanation if task became blocked")
    started_at: Optional[datetime] = Field(default=None, description="Timestamp when task execution started")
    completed_at: Optional[datetime] = Field(default=None, description="Timestamp when task completed (PASSED, FAILED, BLOCKED, SKIPPED)")
    updated_at: Optional[datetime] = Field(default=None, description="Timestamp of latest task state update")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary task metadata")



class PlanValidationResult(BaseModel):
    """
    Structured outcome of the PlanValidator evaluation.
    """
    valid: bool = Field(description="True if the plan satisfies all validation rules")
    errors: List[str] = Field(default_factory=list, description="Fatal errors that prevent plan approval")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal observations or unknowns")
    missing_requirements: List[str] = Field(default_factory=list, description="Unaddressed requirement items")
    missing_acceptance_criteria: List[str] = Field(default_factory=list, description="Tasks lacking measurable criteria")
    dependency_cycles: List[List[str]] = Field(default_factory=list, description="Detected circular dependency paths")
    missing_verification: List[str] = Field(default_factory=list, description="Tasks lacking a verification strategy")
    unknowns: List[str] = Field(default_factory=list, description="Explicit unknowns carried forward")


class Plan(BaseModel):
    """
    The canonical, validated implementation plan artifact for an EngineeringAgent run.
    """
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    agent_run_id: str = Field(description="AgentRun ID this plan belongs to")
    repository_id: str = Field(description="Target repository identifier")
    requirement: str = Field(description="User requirement string being addressed")
    version: int = Field(default=1, description="Plan revision number")
    status: PlanStatus = Field(default=PlanStatus.DRAFT, description="Current plan approval status")
    
    # Bounded summaries of repository context
    repository_understanding: Dict[str, Any] = Field(default_factory=dict, description="Bounded summary of understanding")
    architecture_context: Dict[str, Any] = Field(default_factory=dict, description="Bounded summary of architecture context")
    affected_areas: List[Dict[str, Any]] = Field(default_factory=list, description="Affected components and files")
    constraints: List[str] = Field(default_factory=list, description="Architectural constraints")
    
    # Task Graph
    tasks: List[PlanTask] = Field(default_factory=list, description="Actionable tasks forming a DAG")
    task_dependencies: Dict[str, List[str]] = Field(default_factory=dict, description="DAG map: task_id -> [dependency_task_ids]")
    
    # Global acceptance and verification
    acceptance_criteria: List[str] = Field(default_factory=list, description="Global acceptance criteria")
    verification_strategy: str = Field(default="verify_static", description="Global verification strategy")
    
    # Uncertainty & validation
    risks: List[str] = Field(default_factory=list, description="Identified technical and architectural risks")
    unknowns: List[str] = Field(default_factory=list, description="Explicit unresolved questions or missing context")
    validation: Optional[PlanValidationResult] = Field(default=None, description="Validation result from PlanValidator")
    
    # Audit timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_task(self, task_id: str) -> Optional[PlanTask]:
        """Retrieves a task by its task_id."""
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def to_bounded_summary(self) -> Dict[str, Any]:
        """
        Produces a lightweight, bounded summary for persistence in run metadata_json.
        """
        return {
            "plan_id": self.plan_id,
            "version": self.version,
            "status": self.status.value,
            "task_count": len(self.tasks),
            "tasks": [
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "status": t.status.value,
                    "dependencies": t.dependencies,
                    "affected_files": t.affected_files,
                    "criteria_count": len(t.acceptance_criteria),
                    "verification": t.verification_strategy,
                }
                for t in self.tasks
            ],
            "unknowns_count": len(self.unknowns),
            "risks_count": len(self.risks),
            "is_valid": self.validation.valid if self.validation else False,
            "validation_errors": self.validation.errors if self.validation else [],
            "validation_warnings": self.validation.warnings if self.validation else [],
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
