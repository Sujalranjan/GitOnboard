"""
ApprovalController: Manages the lifecycle of first-class persistent human approval requests.

Enforces:
  1. Approval requests are durable database objects, not ephemeral in-memory state.
  2. Approval state transitions emit real-time SSE events via AgentEventCoordinator.
  3. Action rejection returns structured failure context to the agent rather than aborting the entire run.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.safety.contracts import ApprovalResolution, PolicyDecision
from backend.models.implementation import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    ApprovalActionType,
    ApprovalRequest,
    ApprovalStatus,
    PolicyAction,
    PolicyDecisionRecord,
    RiskLevel,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalError(Exception):
    """Base exception for approval lifecycle errors."""
    pass


class ApprovalNotFoundError(ApprovalError):
    pass


class ApprovalInvalidStateError(ApprovalError):
    pass


class ApprovalController:
    """
    Manages creation, resolution, persistence, and audit logging of approval requests.
    """

    def __init__(self, event_coordinator: Optional[AgentEventCoordinator] = None):
        self.event_coordinator = event_coordinator or AgentEventCoordinator()

    def create_approval_request(
        self,
        db: Session,
        agent_run_id: str,
        action_type: ApprovalActionType,
        action_description: str,
        risk_level: RiskLevel,
        task_id: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        requested_operation: Optional[Dict[str, Any]] = None,
        affected_files: Optional[List[str]] = None,
        command: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        run_model: Optional[AgentRun] = None,
    ) -> ApprovalRequest:
        """
        Creates and persists a new ApprovalRequest in PENDING state.
        Emits an ACTION_APPROVAL_REQUESTED SSE event.
        """
        req = ApprovalRequest(
            agent_run_id=agent_run_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            action_type=action_type,
            action_description=action_description,
            risk_level=risk_level,
            requested_operation=requested_operation or {},
            affected_files=affected_files or [],
            command=command,
            reason=reason,
            status=ApprovalStatus.PENDING,
            requested_at=_now(),
            metadata_json=metadata or {},
        )
        db.add(req)
        db.commit()
        db.refresh(req)

        # Emit real-time SSE event
        run = run_model or db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
        if run:
            self.event_coordinator.emit_event(
                db=db,
                agent_run=run,
                event_type=AgentEventType.ACTION_APPROVAL_REQUESTED,
                message=f"Approval required for '{action_description}' (risk: {risk_level.value})",
                payload={
                    "approval_id": req.id,
                    "task_id": task_id,
                    "tool_call_id": tool_call_id,
                    "action_type": action_type.value,
                    "risk_level": risk_level.value,
                    "command": command,
                    "reason": reason,
                    "affected_files": affected_files or [],
                },
            )

        logger.info(f"ApprovalController: Created approval request '{req.id}' for run '{agent_run_id}' ({action_type.value})")
        return req

    def approve_request(
        self,
        db: Session,
        approval_id: str,
        resolved_by: str = "human_user",
        run_model: Optional[AgentRun] = None,
    ) -> ApprovalRequest:
        """
        Marks an approval request as APPROVED.
        Emits an ACTION_APPROVED SSE event.
        """
        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not req:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found")

        if req.status != ApprovalStatus.PENDING:
            raise ApprovalInvalidStateError(
                f"Cannot approve request '{approval_id}' in state '{req.status.value}' (must be PENDING)"
            )

        req.status = ApprovalStatus.APPROVED
        req.resolved_at = _now()
        req.resolved_by = resolved_by
        db.add(req)
        db.commit()
        db.refresh(req)

        run = run_model or db.query(AgentRun).filter(AgentRun.id == req.agent_run_id).first()
        if run:
            self.event_coordinator.emit_event(
                db=db,
                agent_run=run,
                event_type=AgentEventType.ACTION_APPROVED,
                message=f"Action '{req.action_description}' approved by {resolved_by}",
                payload={
                    "approval_id": req.id,
                    "task_id": req.task_id,
                    "resolved_by": resolved_by,
                    "action_type": req.action_type.value,
                },
            )

        logger.info(f"ApprovalController: Approval request '{approval_id}' APPROVED by '{resolved_by}'")
        return req

    def reject_request(
        self,
        db: Session,
        approval_id: str,
        reason: str,
        resolved_by: str = "human_user",
        run_model: Optional[AgentRun] = None,
    ) -> ApprovalRequest:
        """
        Marks an approval request as REJECTED.
        Emits an ACTION_REJECTED SSE event.
        """
        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not req:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found")

        if req.status != ApprovalStatus.PENDING:
            raise ApprovalInvalidStateError(
                f"Cannot reject request '{approval_id}' in state '{req.status.value}' (must be PENDING)"
            )

        req.status = ApprovalStatus.REJECTED
        req.resolved_at = _now()
        req.resolved_by = resolved_by
        req.rejection_reason = reason
        db.add(req)
        db.commit()
        db.refresh(req)

        run = run_model or db.query(AgentRun).filter(AgentRun.id == req.agent_run_id).first()
        if run:
            self.event_coordinator.emit_event(
                db=db,
                agent_run=run,
                event_type=AgentEventType.ACTION_REJECTED,
                message=f"Action '{req.action_description}' rejected: {reason}",
                payload={
                    "approval_id": req.id,
                    "task_id": req.task_id,
                    "resolved_by": resolved_by,
                    "rejection_reason": reason,
                    "action_type": req.action_type.value,
                },
            )

        logger.info(f"ApprovalController: Approval request '{approval_id}' REJECTED by '{resolved_by}' (reason: {reason})")
        return req

    def get_request(self, db: Session, approval_id: str) -> Optional[ApprovalRequest]:
        """Queries an approval request by its ID."""
        return db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()

    def get_pending_approvals(self, db: Session, agent_run_id: str) -> List[ApprovalRequest]:
        """Queries all pending approval requests for a specific run."""
        return (
            db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.agent_run_id == agent_run_id,
                ApprovalRequest.status == ApprovalStatus.PENDING,
            )
            .order_by(ApprovalRequest.requested_at.asc())
            .all()
        )

    def record_policy_decision(
        self,
        db: Session,
        agent_run_id: str,
        tool_name: str,
        decision: PolicyDecision,
        task_id: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecisionRecord:
        """Persists a PolicyDecisionRecord to maintain complete auditability."""
        rec = PolicyDecisionRecord(
            agent_run_id=agent_run_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments_summary=json.dumps(arguments or {}, default=str)[:1000],
            decision=decision.action,
            risk_level=decision.risk_level,
            reason=decision.reason,
            policy_version="1.0",
            created_at=_now(),
            metadata_json=decision.metadata,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec
