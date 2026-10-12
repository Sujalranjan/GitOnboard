"""
Plan lifecycle management for EngineeringAgent:
synthesis, revision, retrieval, authorization assertions, approval, and rejection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.agent.context.contracts import ContextBudget
from backend.agent.planning.contracts import Plan, PlanStatus
from backend.agent.planning.orchestrator import PlanningOrchestrator
from backend.agent.safety import (
    ApprovalActionType,
    ApprovalStatus,
    RiskLevel,
)
from backend.models.implementation import (
    AgentEventType,
    AgentRun,
    AgentState,
    ApprovalRequest,
)

if TYPE_CHECKING:
    from backend.agent.engineering_agent import EngineeringAgent

logger = logging.getLogger(__name__)


class EngineeringAgentPlanOps:
    """Encapsulates plan synthesis, lifecycle approvals, rejections, and authorization gates."""

    def __init__(self, agent: "EngineeringAgent"):
        self.agent = agent

    def get_plan(self, db: Session, run_id: str) -> Optional[Plan]:
        """Retrieves the current Plan object from run metadata."""
        run = self.agent.get_run(db, run_id)
        meta = run.metadata_json or {}
        plan_dict = meta.get("plan")
        if plan_dict and isinstance(plan_dict, dict):
            try:
                return Plan.model_validate(plan_dict)
            except Exception as err:
                logger.warning(f"Failed to parse Plan model from metadata for run '{run_id}': {err}")
        return None

    def revise_plan(
        self,
        db: Session,
        run_id: str,
        feedback: str,
        budget: Optional[ContextBudget] = None,
    ) -> Plan:
        """
        Revises an existing implementation plan based on user review comments.
        Incorporates feedback into the run requirement, creates an incremented plan version,
        and returns the newly synthesized plan in AWAITING_APPROVAL state.
        """
        run = self.agent.get_run(db, run_id)
        if self.agent.state_machine.is_terminal(run.current_state):
            from backend.agent.engineering_agent import EngineeringAgentError
            raise EngineeringAgentError(
                f"Cannot revise plan on run '{run_id}' in terminal state '{run.current_state.value}'"
            )

        current_req = run.user_requirement or ""
        run.user_requirement = f"{current_req}\n\n[Review Feedback / Revision]: {feedback.strip()}"
        flag_modified(run, "user_requirement")
        db.add(run)
        db.commit()
        db.refresh(run)

        return self.create_plan(db, run_id, budget=budget, force_replan=True)

    def create_plan(
        self,
        db: Session,
        run_id: str,
        budget: Optional[ContextBudget] = None,
        force_replan: bool = False,
    ) -> Plan:
        """
        Synthesizes, validates, and records a structured implementation plan.
        Transitions the agent run to AWAITING_APPROVAL upon successful validation.
        """
        run = self.agent.get_run(db, run_id)

        # Invariant: Terminal state check
        if self.agent.state_machine.is_terminal(run.current_state):
            from backend.agent.engineering_agent import EngineeringAgentError
            raise EngineeringAgentError(
                f"Cannot create plan on run '{run_id}' in terminal state '{run.current_state.value}'"
            )

        # Idempotency / Deduplication: If already in AWAITING_APPROVAL with a valid plan, return existing plan
        existing_plan = self.get_plan(db, run_id)
        if not force_replan and run.current_state == AgentState.AWAITING_APPROVAL and existing_plan and (existing_plan.validation and existing_plan.validation.valid):
            existing_app = db.query(ApprovalRequest).filter(
                ApprovalRequest.agent_run_id == run.id,
                ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
                ApprovalRequest.status.in_([ApprovalStatus.PENDING, ApprovalStatus.APPROVED]),
            ).first()
            if existing_app:
                logger.info(f"Plan and ApprovalRequest already active for run '{run_id}' in AWAITING_APPROVAL. Returning existing plan.")
                return existing_plan

        # Transition to PLANNING state if currently in IDLE, UNDERSTANDING, or AWAITING_APPROVAL (replanning)
        if run.current_state in (AgentState.IDLE, AgentState.UNDERSTANDING, AgentState.AWAITING_APPROVAL):
            self.agent.transition_state(db, run.id, to_state=AgentState.PLANNING, reason="Starting plan synthesis")
            db.refresh(run)

        # 1. Emit PLANNING_STARTED
        self.agent.events.emit_event(
            db,
            run,
            AgentEventType.PLANNING_STARTED,
            f"Starting implementation plan synthesis for requirement: '{run.user_requirement[:60]}...'",
            {"repository_id": run.repository_id},
        )

        try:
            # 2. Assemble/fetch repository context
            context = self.agent.assemble_repository_context(db, run.id, budget=budget)

            # Capture repository revision at plan synthesis time
            repo_revision = self.agent.get_repository_revision(run.repository_id, run.worktree_path)

            # Determine plan revision version
            meta = run.metadata_json or {}
            existing_plan_data = meta.get("plan")
            current_version = existing_plan_data.get("version", 0) if isinstance(existing_plan_data, dict) else 0
            new_version = current_version + 1

            # 3. Invoke PlanningOrchestrator
            orchestrator = PlanningOrchestrator(llm_service=self.agent.llm_service)
            plan = orchestrator.create_plan(
                context=context,
                agent_run_id=run.id,
                repository_id=run.repository_id or "default",
                requirement=run.user_requirement,
                db=db,
                version=new_version,
                repository_revision=repo_revision,
            )

            # 4. Handle validation outcome
            if plan.validation and plan.validation.valid:
                self.agent.events.emit_event(
                    db,
                    run,
                    AgentEventType.PLANNING_COMPLETED,
                    f"Implementation plan v{plan.version} synthesized and validated with {len(plan.tasks)} tasks.",
                    {
                        "plan_id": plan.plan_id,
                        "version": plan.version,
                        "task_count": len(plan.tasks),
                        "unknown_count": len(plan.unknowns),
                    },
                )

                self.agent.events.emit_event(
                    db,
                    run,
                    AgentEventType.PLAN_READY_FOR_APPROVAL,
                    f"Plan v{plan.version} is ready for human approval.",
                    {"plan_id": plan.plan_id, "version": plan.version},
                )

                # Persist full plan artifact and bounded summary
                meta["plan"] = plan.model_dump(mode="json")
                run.metadata_json = meta
                flag_modified(run, "metadata_json")
                db.add(run)
                db.commit()

                # Persist plan to history table for long-term audit trail
                try:
                    from backend.models.implementation import AgentRunPlanHistory, AgentRunPlanHistoryStatus

                    plan_history = AgentRunPlanHistory(
                        agent_run_id=run.id,
                        plan_id=plan.plan_id,
                        version=plan.version,
                        status=AgentRunPlanHistoryStatus.READY_FOR_APPROVAL,
                        plan_json=plan.model_dump(mode="json"),
                    )
                    db.add(plan_history)
                    db.commit()

                    prev_plans = db.query(AgentRunPlanHistory).filter(
                        AgentRunPlanHistory.agent_run_id == run.id,
                        AgentRunPlanHistory.version < plan.version,
                    ).all()
                    for prev_plan in prev_plans:
                        if prev_plan.status != AgentRunPlanHistoryStatus.SUPERSEDED:
                            prev_plan.status = AgentRunPlanHistoryStatus.SUPERSEDED
                            prev_plan.superseded_at = plan.updated_at
                            prev_plan.superseded_by_plan_id = plan.plan_id
                            db.add(prev_plan)
                    db.commit()
                except Exception as err:
                    logger.warning(f"Failed to persist plan to history table for run '{run_id}': {err}")

                # Invalidate any previous approvals for older plan revisions
                prev_approvals = db.query(ApprovalRequest).filter(
                    ApprovalRequest.agent_run_id == run.id,
                    ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
                    ApprovalRequest.status.in_([ApprovalStatus.PENDING, ApprovalStatus.APPROVED]),
                ).all()
                for pa in prev_approvals:
                    pa.status = ApprovalStatus.EXPIRED
                    db.add(pa)
                db.commit()

                # Transition run to AWAITING_APPROVAL AFTER all plan prerequisites are persisted
                db.refresh(run)
                if run.current_state == AgentState.PLANNING:
                    self.agent.transition_state(
                        db,
                        run.id,
                        to_state=AgentState.AWAITING_APPROVAL,
                        reason=f"Plan v{plan.version} created and validated with {len(plan.tasks)} tasks; awaiting user review",
                    )
                elif run.current_state != AgentState.AWAITING_APPROVAL:
                    logger.warning(f"Run '{run_id}' in unexpected state {run.current_state.value} during plan validation; expected PLANNING or AWAITING_APPROVAL")

                # Create plan-specific ApprovalRequest bound to exact plan_id, version, and repository revision
                aff_files = [
                    a.get("file") if isinstance(a, dict) else getattr(a, "file", str(a))
                    for a in (plan.affected_areas or [])
                ]
                self.agent.approval_controller.create_approval_request(
                    db=db,
                    agent_run_id=run.id,
                    action_type=ApprovalActionType.PLAN_APPROVAL,
                    action_description=f"Approve implementation plan v{plan.version} ({plan.plan_id}) with {len(plan.tasks)} tasks",
                    risk_level=RiskLevel.HIGH,
                    requested_operation={
                        "plan_id": plan.plan_id,
                        "version": plan.version,
                        "repository_id": run.repository_id or "default",
                        "repository_revision": plan.repository_revision,
                        "task_count": len(plan.tasks),
                    },
                    affected_files=aff_files,
                    reason=f"Human authorization required for plan v{plan.version} ({plan.requirement[:60]})",
                    metadata={"plan_id": plan.plan_id, "version": plan.version, "repository_revision": plan.repository_revision},
                    run_model=run,
                )
            else:
                err_msg = "; ".join(plan.validation.errors) if plan.validation else "Validation failed"
                self.agent.events.emit_event(
                    db,
                    run,
                    AgentEventType.PLANNING_FAILED,
                    f"Plan validation failed: {err_msg}",
                    {"errors": plan.validation.errors if plan.validation else []},
                )
                meta["plan"] = plan.model_dump(mode="json")
                run.metadata_json = meta
                flag_modified(run, "metadata_json")
                db.add(run)
                db.commit()

            return plan

        except Exception as err:
            logger.error(f"Plan creation failed for run '{run_id}': {err}", exc_info=True)
            self.agent.events.emit_event(
                db,
                run,
                AgentEventType.PLANNING_FAILED,
                f"Planning failed: {err}",
                {"error": str(err)},
            )
            from backend.agent.engineering_agent import EngineeringAgentError
            raise EngineeringAgentError(f"Plan synthesis failed: {err}") from err

    def assert_execution_authorized(
        self,
        db: Session,
        run_id: str,
        plan_id: Optional[str] = None,
        plan_version: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> None:
        """
        Server-side central execution authorization gate.
        Enforces requester ownership, run state, plan validation, persisted approval, and revision matching.
        """
        from backend.agent.engineering_agent import EngineeringAgentError
        run = self.agent.get_run(db, run_id)
        if user_id is not None and run.user_id is not None and run.user_id != user_id:
            raise EngineeringAgentError(f"Execution not authorized: User '{user_id}' does not own run '{run_id}'")

        if run.current_state not in (AgentState.AWAITING_APPROVAL, AgentState.EXECUTING):
            raise EngineeringAgentError(
                f"Execution not authorized: Run '{run_id}' is in state '{run.current_state.value}', expected EXECUTING or AWAITING_APPROVAL"
            )

        plan = self.get_plan(db, run_id)
        if not plan:
            raise EngineeringAgentError(f"Execution not authorized: No plan found for run '{run_id}'")

        if plan.status != PlanStatus.APPROVED:
            raise EngineeringAgentError(
                f"Execution not authorized: Plan '{plan.plan_id}' has status '{plan.status.value}', expected APPROVED"
            )

        if not plan.validation or not plan.validation.valid:
            raise EngineeringAgentError(f"Execution not authorized: Plan '{plan.plan_id}' failed validation")

        approval = (
            db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.agent_run_id == run_id,
                ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
                ApprovalRequest.status == ApprovalStatus.APPROVED,
            )
            .order_by(ApprovalRequest.resolved_at.desc(), ApprovalRequest.requested_at.desc())
            .first()
        )

        if not approval:
            raise EngineeringAgentError(
                f"Execution not authorized: No valid APPROVED ApprovalRequest found in database for run '{run_id}'"
            )

        op = approval.requested_operation or {}
        approved_plan_id = op.get("plan_id")
        approved_version = op.get("version")

        if approved_plan_id and approved_plan_id != plan.plan_id:
            raise EngineeringAgentError(
                f"Execution not authorized: Approval plan ID mismatch (approved '{approved_plan_id}' != active '{plan.plan_id}')"
            )

        if approved_version is not None and approved_version != plan.version:
            raise EngineeringAgentError(
                f"Execution not authorized: Approval plan version mismatch (approved v{approved_version} != active v{plan.version})"
            )

        if plan_id and plan_id != plan.plan_id:
            raise EngineeringAgentError(
                f"Execution not authorized: Target plan ID mismatch ('{plan_id}' != active '{plan.plan_id}')"
            )

        if plan_version is not None and plan_version != plan.version:
            raise EngineeringAgentError(
                f"Execution not authorized: Target plan version mismatch (v{plan_version} != active v{plan.version})"
            )

        approved_revision = op.get("repository_revision") or getattr(plan, "repository_revision", None)
        current_revision = self.agent.get_repository_revision(run.repository_id, run.worktree_path)
        if approved_revision and current_revision and approved_revision != current_revision:
            raise EngineeringAgentError(
                f"Execution not authorized: Repository revision mismatch (approved '{approved_revision}' != current '{current_revision}')"
            )

    def approve_plan(
        self,
        db: Session,
        run_id: str,
        resolved_by: str = "human_user",
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """Explicitly approves the synthesized plan."""
        from backend.agent.engineering_agent import EngineeringAgentError
        run = self.agent.get_run(db, run_id)
        if user_id is not None and run.user_id is not None and run.user_id != user_id:
            raise EngineeringAgentError(f"Approval not authorized: User '{user_id}' does not own run '{run_id}'")

        if run.current_state == AgentState.EXECUTING:
            logger.info(f"Run '{run_id}' is already in EXECUTING state. Returning current state idempotently.")
            return run

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot approve plan for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        plan = self.get_plan(db, run_id)
        if not plan:
            raise EngineeringAgentError(f"No plan found to approve for run '{run_id}'")

        if plan.status == PlanStatus.APPROVED:
            logger.info(f"Plan '{plan.plan_id}' is already APPROVED for run '{run_id}'. Returning current state idempotently.")
            return run

        if plan.status != PlanStatus.READY_FOR_APPROVAL:
            raise EngineeringAgentError(
                f"Plan '{plan.plan_id}' is in status '{plan.status.value}'. Only plans in READY_FOR_APPROVAL can be approved."
            )

        now = datetime.now(timezone.utc)
        plan.status = PlanStatus.APPROVED
        plan.resolved_by = resolved_by
        plan.resolved_at = now
        plan.updated_at = now

        meta = run.metadata_json or {}
        meta["plan"] = plan.model_dump(mode="json")
        run.metadata_json = meta
        flag_modified(run, "metadata_json")
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            from backend.models.implementation import AgentRunPlanHistory, AgentRunPlanHistoryStatus
            plan_history = db.query(AgentRunPlanHistory).filter(
                AgentRunPlanHistory.plan_id == plan.plan_id
            ).first()
            if plan_history:
                plan_history.status = AgentRunPlanHistoryStatus.APPROVED
                plan_history.resolved_by = resolved_by
                plan_history.resolved_at = now
                db.add(plan_history)
                db.commit()
        except Exception as err:
            logger.warning(f"Failed to update plan history for approval of plan '{plan.plan_id}': {err}")

        pending_approvals = self.agent.approval_controller.get_pending_approvals(db, agent_run_id=run.id)
        plan_approval = next((a for a in pending_approvals if a.action_type == ApprovalActionType.PLAN_APPROVAL), None)
        if plan_approval:
            self.agent.approval_controller.approve_request(db, approval_id=plan_approval.id, resolved_by=resolved_by, run_model=run)
        else:
            app_req = db.query(ApprovalRequest).filter(
                ApprovalRequest.agent_run_id == run_id,
                ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
            ).order_by(ApprovalRequest.requested_at.desc()).first()
            if app_req and app_req.status == ApprovalStatus.PENDING:
                self.agent.approval_controller.approve_request(db, approval_id=app_req.id, resolved_by=resolved_by, run_model=run)
            elif not app_req:
                created_req = self.agent.approval_controller.create_approval_request(
                    db,
                    agent_run_id=run.id,
                    action_type=ApprovalActionType.PLAN_APPROVAL,
                    action_description=f"Approve implementation plan v{plan.version} ({plan.plan_id}) with {len(plan.tasks)} tasks",
                    requested_operation={
                        "plan_id": plan.plan_id,
                        "version": plan.version,
                        "task_count": len(plan.tasks),
                        "repository_revision": plan.repository_revision,
                    },
                    risk_level=RiskLevel.HIGH,
                    run_model=run,
                )
                self.agent.approval_controller.approve_request(db, approval_id=created_req.id, resolved_by=resolved_by, run_model=run)

        self.agent.events.emit_event(
            db,
            run,
            AgentEventType.PLAN_APPROVED,
            f"Plan v{plan.version} ('{plan.plan_id}') approved by {resolved_by}. Ready for task orchestration.",
            {
                "plan_id": plan.plan_id,
                "version": plan.version,
                "task_count": len(plan.tasks),
                "resolved_by": resolved_by,
            },
        )

        return run

    def reject_plan(
        self,
        db: Session,
        run_id: str,
        reason: Optional[str] = None,
        resolved_by: str = "human_user",
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """Explicitly rejects the synthesized plan."""
        from backend.agent.engineering_agent import EngineeringAgentError
        run = self.agent.get_run(db, run_id)
        if user_id is not None and run.user_id is not None and run.user_id != user_id:
            raise EngineeringAgentError(f"Rejection not authorized: User '{user_id}' does not own run '{run_id}'")

        if run.current_state == AgentState.CANCELLED:
            logger.info(f"Run '{run_id}' is already CANCELLED. Returning current state idempotently.")
            return run

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot reject plan for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        plan = self.get_plan(db, run_id)
        if plan:
            now = datetime.now(timezone.utc)
            plan.status = PlanStatus.REJECTED
            plan.resolved_by = resolved_by
            plan.resolved_at = now
            plan.rejection_reason = reason
            plan.updated_at = now
            meta = run.metadata_json or {}
            meta["plan"] = plan.model_dump(mode="json")
            run.metadata_json = meta
            flag_modified(run, "metadata_json")
            db.add(run)
            db.commit()

            try:
                from backend.models.implementation import AgentRunPlanHistory, AgentRunPlanHistoryStatus
                plan_history = db.query(AgentRunPlanHistory).filter(
                    AgentRunPlanHistory.plan_id == plan.plan_id
                ).first()
                if plan_history:
                    plan_history.status = AgentRunPlanHistoryStatus.REJECTED
                    plan_history.resolved_by = resolved_by
                    plan_history.resolved_at = now
                    plan_history.rejection_reason = reason
                    db.add(plan_history)
                    db.commit()
            except Exception as err:
                logger.warning(f"Failed to update plan history for rejection of plan '{plan.plan_id}': {err}")

        reject_msg = reason or "Plan rejected by user."

        pending_approvals = self.agent.approval_controller.get_pending_approvals(db, agent_run_id=run.id)
        for pa in pending_approvals:
            if pa.action_type == ApprovalActionType.PLAN_APPROVAL:
                self.agent.approval_controller.reject_request(
                    db, approval_id=pa.id, reason=reject_msg, resolved_by=resolved_by, run_model=run
                )

        self.agent.events.emit_event(
            db,
            run,
            AgentEventType.PLAN_REJECTED,
            f"Plan rejected by user: {reject_msg}",
            {
                "plan_id": plan.plan_id if plan else None,
                "reason": reject_msg,
            },
        )

        self.agent.transition_state(
            db,
            run.id,
            to_state=AgentState.CANCELLED,
            reason=f"Plan rejected: {reject_msg}",
        )

        return run
