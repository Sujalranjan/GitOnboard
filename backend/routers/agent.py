"""
FastAPI Router for Engineering Agent Subsystem (/api/v1/agent).

Provides endpoints for creating, inspecting, controlling, and streaming agent runs.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.agent.engineering_agent import (
    EngineeringAgent,
    EngineeringAgentError,
    RunNotFoundError,
)
from backend.agent.state_machine import InvalidStateTransitionError
from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.models.user import User
from backend.models.implementation import (
    AgentEvent,
    AgentRun,
    AgentState,
    ApprovalActionType,
    ApprovalRequest,
    ApprovalStatus,
    RiskLevel,
)
from backend.task_manager import task_manager
from backend.agent.graph import AgentGraphOrchestrator
from backend.ai.service import build_default_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["Engineering Agent"])
agent_service = EngineeringAgent(llm_service=build_default_service())
graph_orchestrator = AgentGraphOrchestrator(agent_service=agent_service)

_EVENT_CHANNEL_USER_ID = 0


# Re-export schemas for backward compatibility
from backend.routers.agent_schemas import (  # noqa: F401
    AgentRunDetailResponse,
    AgentRunResponse,
    ApprovalRequestItem,
    ApproveActionRequest,
    CancelAgentRunRequest,
    ClassifyIntentRequest,
    ClassifyIntentResponse,
    ControlledActionRequest,
    ControlledActionResponse,
    CreateAgentRunRequest,
    EventItem,
    ExplainSymbolRequest,
    FileContentRequest,
    FileContentResponse,
    QuickIntentResponse,
    RejectActionRequest,
    RejectPlanRequest,
    RevisePlanRequest,
    StateTransitionItem,
    SymbolExplanation,
    SymbolGraphEdge,
    SymbolGraphNode,
    SymbolGraphQueryRequest,
    SymbolGraphQueryResponse,
    TransitionStateRequest,
    WorkspaceChangesResponse,
    WorkspaceSnapshotResponse,
)
from backend.routers.agent_helpers import (
    compute_workspace_changes as _compute_workspace_changes,
    serialize_approval_request as _serialize_approval_request,
    serialize_event as _serialize_event,
    serialize_run as _serialize_run,
    serialize_run_detail as _serialize_run_detail,
)
from backend.routers.agent_intent_routes import router as intent_router
from backend.routers.agent_repo_tools import router as repo_tools_router

router.include_router(intent_router)
router.include_router(repo_tools_router)

def _get_authorized_run(run_id: str, current_user: User, db: Session) -> AgentRun:
    """
    Retrieves and deterministically verifies ownership of an AgentRun.
    - user_id match => authorized
    - legacy NULL user_id => authorized ONLY if ownership can be deterministically
      proven via associated repository or implementation
    - otherwise => 403 Forbidden (never fall back to 'run exists')
    """
    try:
        run = agent_service.get_run(db, run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"AgentRun '{run_id}' not found")

    if run.user_id is not None:
        if run.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: not run owner")
        return run

    # Legacy NULL user_id run authorization check
    is_owned = False
    if run.repository_id:
        from backend.models.repository import Repository
        repo = db.query(Repository).filter(
            (Repository.id == (int(run.repository_id) if run.repository_id.isdigit() else -1)) |
            (Repository.url.endswith(f"/{run.repository_id}")) |
            (Repository.url.endswith(f"/{run.repository_id}.git"))
        ).first()
        if repo and repo.user_id == current_user.id:
            is_owned = True

    if not is_owned and run.implementation_id:
        from backend.models.implementation import Implementation
        impl = db.query(Implementation).filter(Implementation.id == run.implementation_id).first()
        if impl and impl.user_id == current_user.id:
            is_owned = True

    if not is_owned:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: unverified legacy run owner")

    return run


def _background_plan_run(run_id: str):
    from backend.database import SessionLocal
    with SessionLocal() as db:
        try:
            logger.info(f"Starting background plan synthesis via LangGraph for run '{run_id}'")
            graph_orchestrator.run_graph(run_id=run_id, db=db)
        except Exception as err:
            logger.error(f"Background plan synthesis via LangGraph failed for run '{run_id}': {err}", exc_info=True)


def _background_execute_approved_plan(run_id: str):
    from backend.database import SessionLocal
    logger.info(f"[BACKGROUND] Starting background task executor for run '{run_id}'")
    with SessionLocal() as db:
        try:
            logger.info(f"[BACKGROUND] DB session created for run '{run_id}'")
            has_failure = False
            task_count = 0
            while True:
                logger.info(f"[BACKGROUND] Calling execute_next_task for run '{run_id}' (iteration {task_count})")
                task, exec_res = agent_service.execute_next_task(db=db, run_id=run_id)
                logger.info(f"[BACKGROUND] execute_next_task returned - task: {task.task_id if task else None}, success: {exec_res.success if exec_res else None}")

                if not task:
                    # All tasks completed
                    logger.info(f"[BACKGROUND] No more tasks for run '{run_id}' - completing run (has_failure={has_failure})")
                    if has_failure:
                        logger.info(f"[BACKGROUND] Completing run '{run_id}' with FAILURE")
                        agent_service.complete_run(db, run_id, success=False, failure_reason="One or more tasks failed")
                    else:
                        logger.info(f"[BACKGROUND] Completing run '{run_id}' with SUCCESS")
                        agent_service.complete_run(db, run_id, success=True)
                    break
                # Check if this task execution failed
                task_count += 1
                logger.info(f"[BACKGROUND] Task #{task_count} completed: {task.task_id}, success={exec_res.success if exec_res else None}")
                if exec_res and not exec_res.success:
                    logger.warning(f"[BACKGROUND] Task failed - marking run for eventual failure")
                    has_failure = True
        except Exception as err:
            logger.error(f"[BACKGROUND] Background task execution failed for run '{run_id}': {err}", exc_info=True)
            agent_service.complete_run(db, run_id, success=False, failure_reason=str(err))


# ──────────────────────────────────────────────────────────────────────────────



@router.post("/runs", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
def create_agent_run(
    req: CreateAgentRunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Creates and initializes a new EngineeringAgent session in UNDERSTANDING state for authenticated user.
    Automatically kicks off background context assembly and LLM plan synthesis.
    """
    # Verify repository ownership if repository_id matches an existing DB repository
    if req.repository_id:
        from backend.models.repository import Repository
        repo = db.query(Repository).filter(
            (Repository.id == (int(req.repository_id) if req.repository_id.isdigit() else -1)) |
            (Repository.url.endswith(f"/{req.repository_id}")) |
            (Repository.url.endswith(f"/{req.repository_id}.git"))
        ).first()
        if repo and repo.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: not repository owner")

    try:
        run = agent_service.create_run(
            db=db,
            repository_id=req.repository_id,
            user_requirement=req.user_requirement,
            config=req.config,
            user_id=current_user.id,
        )
        background_tasks.add_task(_background_plan_run, run.id)
        return _serialize_run(run)
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Error creating agent run: {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create agent run")


@router.get("/runs", response_model=List[AgentRunResponse])
def list_agent_runs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[AgentRunResponse]:
    """
    Lists all agent runs owned by the authenticated user.
    """
    runs = db.query(AgentRun).filter(AgentRun.user_id == current_user.id).order_by(AgentRun.started_at.desc()).all()
    return [_serialize_run(r) for r in runs]


@router.get("/runs/{run_id}", response_model=AgentRunDetailResponse)
def get_agent_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunDetailResponse:
    """
    Retrieves full lifecycle state, transition history, and events for an authorized agent run.
    """
    run = _get_authorized_run(run_id, current_user, db)
    return _serialize_run_detail(run)


@router.post("/runs/{run_id}/transition", response_model=AgentRunResponse)
def transition_agent_state(
    run_id: str,
    req: TransitionStateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Applies a validated state transition to an authorized agent run.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        run = agent_service.transition_state(
            db=db,
            run_id=run_id,
            to_state=req.to_state,
            reason=req.reason,
            metadata=req.metadata,
        )
        return _serialize_run(run)
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except InvalidStateTransitionError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))
    except Exception as err:
        logger.error(f"State transition error: {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/runs/{run_id}/action", response_model=ControlledActionResponse)
def execute_controlled_action(
    run_id: str,
    req: ControlledActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ControlledActionResponse:
    """
    Executes a controlled deterministic operation inside an authorized agent run.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        result = agent_service.execute_controlled_action(
            db=db,
            run_id=run_id,
            action_type=req.action_type,
            parameters=req.parameters,
        )
        return ControlledActionResponse(**result)
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Controlled action execution error: {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/runs/{run_id}/cancel", response_model=AgentRunResponse)
def cancel_agent_run(
    run_id: str,
    req: Optional[CancelAgentRunRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Cancels an active authorized agent run, locking it into terminal CANCELLED state.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        reason = req.reason if req else None
        run = agent_service.cancel_run(db, run_id, reason=reason)
        return _serialize_run(run)
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except InvalidStateTransitionError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except Exception as err:
        logger.error(f"Run cancellation error: {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/events", response_model=List[EventItem])
def get_agent_events(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[EventItem]:
    """
    Returns persisted historical events for an authorized agent run.
    """
    run = _get_authorized_run(run_id, current_user, db)
    return [
        EventItem(
            event_id=str(e.id),
            sequence=getattr(e, "sequence", 0) or 0,
            agent_run_id=getattr(e, "agent_run_id", None) or run.id,
            task_id=getattr(e, "task_id", None),
            event_type=e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
            message=e.message,
            payload=e.payload or {},
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in run.events
    ]


@router.post("/runs/{run_id}/context", response_model=Dict[str, Any])
def assemble_run_context(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Assembles and returns structured repository evidence for an authorized active run.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        context = agent_service.assemble_repository_context(db=db, run_id=run_id)
        return context.model_dump()
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Context assembly endpoint failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/runs/{run_id}/plan", response_model=Dict[str, Any])
def create_run_plan(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Synthesizes and validates an implementation plan for the authorized run.
    Transitions run to AWAITING_APPROVAL upon successful validation.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        plan = agent_service.create_plan(db=db, run_id=run_id)
        return plan.model_dump(mode="json")
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except InvalidStateTransitionError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Plan creation endpoint failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/plan", response_model=Dict[str, Any])
def get_run_plan(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieves the current implementation plan for an authorized agent run.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        plan = agent_service.get_plan(db=db, run_id=run_id)
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No plan found for run '{run_id}'")
        return plan.model_dump(mode="json")
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Get plan endpoint failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/plan/history", response_model=List[Dict[str, Any]])
def get_run_plan_history(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Retrieves the complete history of implementation plans for an authorized agent run.
    Plans are ordered by version descending (newest first).
    """
    logger.info(f"[PLAN_HISTORY] GET /runs/{run_id}/plan/history - User: {current_user.id if current_user else 'unknown'}")
    _get_authorized_run(run_id, current_user, db)
    try:
        from backend.models.implementation import AgentRunPlanHistory
        plans = (
            db.query(AgentRunPlanHistory)
            .filter(AgentRunPlanHistory.agent_run_id == run_id)
            .order_by(AgentRunPlanHistory.version.desc())
            .all()
        )
        logger.info(f"[PLAN_HISTORY] Found {len(plans) if plans else 0} plans for run '{run_id}'")
        return [
            {
                "plan_id": p.plan_id,
                "version": p.version,
                "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "resolved_by": p.resolved_by,
                "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
                "rejection_reason": p.rejection_reason,
                "superseded_at": p.superseded_at.isoformat() if p.superseded_at else None,
                **p.plan_json,  # Unpack the full plan data
            }
            for p in plans
        ]
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        logger.error(f"Get plan history failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/plan/history/{plan_id}", response_model=Dict[str, Any])
def get_run_plan_by_id(
    run_id: str,
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieves a specific plan version from an authorized agent run's history.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        from backend.models.implementation import AgentRunPlanHistory
        plan_record = (
            db.query(AgentRunPlanHistory)
            .filter(
                AgentRunPlanHistory.agent_run_id == run_id,
                AgentRunPlanHistory.plan_id == plan_id,
            )
            .first()
        )
        if not plan_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan '{plan_id}' not found in run '{run_id}'",
            )
        return {
            "plan_id": plan_record.plan_id,
            "version": plan_record.version,
            "status": plan_record.status.value if hasattr(plan_record.status, "value") else str(plan_record.status),
            "created_at": plan_record.created_at.isoformat() if plan_record.created_at else None,
            "resolved_by": plan_record.resolved_by,
            "resolved_at": plan_record.resolved_at.isoformat() if plan_record.resolved_at else None,
            "rejection_reason": plan_record.rejection_reason,
            "superseded_at": plan_record.superseded_at.isoformat() if plan_record.superseded_at else None,
            **plan_record.plan_json,  # Unpack the full plan data
        }
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Get plan by ID failed for run '{run_id}', plan '{plan_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/runs/{run_id}/plan/approve", response_model=AgentRunResponse)
def approve_run_plan(
    run_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Explicitly approves the synthesized plan and starts background execution of tasks.
    Idempotency: If run is already EXECUTING, returns current run without duplicate worker.
    """
    logger.info(f"[APPROVE] POST /runs/{run_id}/plan/approve - User: {current_user.id if current_user else 'unknown'}")
    run = _get_authorized_run(run_id, current_user, db)
    logger.info(f"[APPROVE] Run found - ID: {run.id}, current_state: {run.current_state}")
    if run.current_state == AgentState.EXECUTING:
        logger.info(f"[APPROVE] Run '{run_id}' is already in EXECUTING state; returning current run.")
        return _serialize_run(run)
    try:
        resolved_by = current_user.username if hasattr(current_user, "username") else "human_user"
        logger.info(f"[APPROVE] Calling agent_service.approve_plan for run '{run_id}'")
        run = agent_service.approve_plan(db=db, run_id=run_id, resolved_by=resolved_by, user_id=current_user.id)
        logger.info(f"[APPROVE] Plan approved, run state: {run.current_state}")

        logger.info(f"[APPROVE] Calling agent_service.start_plan_execution for run '{run_id}'")
        run = agent_service.start_plan_execution(db=db, run_id=run_id, user_id=current_user.id)
        logger.info(f"[APPROVE] Plan execution started, run state: {run.current_state}")

        db.refresh(run)  # Ensure we have the latest state before returning
        logger.info(f"[APPROVE] DB refreshed, run state: {run.current_state}")

        logger.info(f"[APPROVE] Adding background task for run '{run_id}'")
        background_tasks.add_task(_background_execute_approved_plan, run_id)
        logger.info(f"[APPROVE] Returning serialized run")
        return _serialize_run(run)
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except InvalidStateTransitionError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Plan approval endpoint failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/runs/{run_id}/plan/revise", response_model=Dict[str, Any])
def revise_run_plan(
    run_id: str,
    req: RevisePlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Revises the implementation plan for the authorized run by incorporating user feedback,
    incrementing the plan version, and keeping the run in AWAITING_APPROVAL state.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        plan = agent_service.revise_plan(db=db, run_id=run_id, feedback=req.feedback)
        return plan.model_dump(mode="json")
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except InvalidStateTransitionError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Plan revision endpoint failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/runs/{run_id}/plan/reject", response_model=AgentRunResponse)
def reject_run_plan(
    run_id: str,
    req: Optional[RejectPlanRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Explicitly rejects the plan and transitions run to terminal CANCELLED state.
    CRITICAL INVARIANT: Rejection NEVER triggers task implementation.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        reason = req.reason if req else None
        resolved_by = current_user.username if hasattr(current_user, "username") else "human_user"
        run = agent_service.reject_plan(db=db, run_id=run_id, reason=reason, resolved_by=resolved_by, user_id=current_user.id)
        return _serialize_run(run)
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except InvalidStateTransitionError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Plan rejection endpoint failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/runs/{run_id}/execute", response_model=AgentRunResponse)
def execute_approved_plan(
    run_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Starts controlled execution of the approved implementation plan.
    Strict preconditions: Run must be in AWAITING_APPROVAL and Plan must be APPROVED with valid ApprovalRequest.
    """
    run = _get_authorized_run(run_id, current_user, db)
    if run.current_state == AgentState.EXECUTING:
        logger.info(f"Run '{run_id}' is already in EXECUTING state; returning current run.")
        return _serialize_run(run)
    try:
        # Enforce server-side execution authorization gate
        agent_service.assert_execution_authorized(db=db, run_id=run_id, user_id=current_user.id)
        run = agent_service.start_plan_execution(db=db, run_id=run_id, user_id=current_user.id)
        background_tasks.add_task(_background_execute_approved_plan, run_id)
        return _serialize_run(run)
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except InvalidStateTransitionError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Plan execution start failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/runs/{run_id}/tasks/next")
def execute_next_plan_task(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Executes the next eligible task deterministically according to DAG dependencies.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        task, exec_result = agent_service.execute_next_task(db=db, run_id=run_id)
        if not task:
            return {"message": "No eligible tasks ready for execution", "task": None, "result": None}
        return {
            "task": task.model_dump(mode="json"),
            "result": exec_result.model_dump(mode="json") if exec_result else None,
        }
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Execute next task failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/tasks")
def get_run_tasks(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns all tasks and current lifecycle statuses for the authorized run.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        tasks = agent_service.get_plan_tasks(db=db, run_id=run_id)
        return [t.model_dump(mode="json") for t in tasks]
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        logger.error(f"Get plan tasks failed for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/tasks/{task_id}")
def get_run_task_detail(
    run_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns details of an individual task by task_id for an authorized run.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        task = agent_service.get_plan_task(db=db, run_id=run_id, task_id=task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
        return task.model_dump(mode="json")
    except HTTPException:
        raise
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        logger.error(f"Get plan task detail failed for run '{run_id}', task '{task_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/workspace", response_model=WorkspaceSnapshotResponse)
def get_workspace_snapshot(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceSnapshotResponse:
    """
    Atomic snapshot of the complete workspace state for an authorized run.
    """
    logger.info(f"[WORKSPACE] GET /runs/{run_id}/workspace - User: {current_user.id if current_user else 'unknown'}")
    run = _get_authorized_run(run_id, current_user, db)
    logger.info(f"[WORKSPACE] Run found - state: {run.current_state}, id: {run.id}")
    try:
        plan = agent_service.get_plan(db, run_id)
        logger.info(f"[WORKSPACE] Plan retrieved - id: {plan.plan_id if plan else None}, status: {plan.status if plan else None}")
        plan_dict = plan.model_dump(mode="json") if plan else None

        tasks = agent_service.get_plan_tasks(db, run_id)
        logger.info(f"[WORKSPACE] Tasks retrieved - count: {len(tasks) if tasks else 0}")
        tasks_list = [t.model_dump(mode="json") for t in tasks]

        # Determine active task
        active_task = None
        for t in tasks:
            t_status = t.status.value if hasattr(t.status, "value") else str(t.status)
            if t_status in ("RUNNING", "VERIFYING", "DIAGNOSING", "REPAIRING", "REVERIFYING"):
                active_task = t.model_dump(mode="json")
                break
        if not active_task and tasks_list:
            for t in tasks:
                t_status = t.status.value if hasattr(t.status, "value") else str(t.status)
                if t_status == "READY":
                    active_task = t.model_dump(mode="json")
                    break

        changes = _compute_workspace_changes(run)
        pending_approvals = [
            _serialize_approval_request(a)
            for a in agent_service.approval_controller.get_pending_approvals(db, run_id)
        ]

        verification_data = run.metadata_json.get("verification_result") if run.metadata_json else None
        recent_events = [_serialize_event(e, idx + 1) for idx, e in enumerate(run.events or [])]
        logger.info(f"[WORKSPACE] Events retrieved - count: {len(recent_events)}")
        if recent_events:
            logger.info(f"[WORKSPACE] First 5 events: {[e.event_type if hasattr(e, 'event_type') else str(e) for e in recent_events[:5]]}")

        logger.info(f"[WORKSPACE] Returning workspace snapshot")
        return WorkspaceSnapshotResponse(
            run=_serialize_run_detail(run),
            plan=plan_dict,
            tasks=tasks_list,
            active_task=active_task,
            changes=changes,
            verification=verification_data,
            pending_approvals=pending_approvals,
            latest_events=recent_events,
        )
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        logger.error(f"Workspace snapshot error for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/approvals", response_model=List[ApprovalRequestItem])
def get_pending_approvals(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ApprovalRequestItem]:
    """
    Returns pending human approval requests for an authorized active run.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        approvals = agent_service.approval_controller.get_pending_approvals(db, run_id)
        return [_serialize_approval_request(a) for a in approvals]
    except Exception as err:
        logger.error(f"Failed to get approvals for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


from backend.agent.safety.approval import (
    ApprovalInvalidStateError,
    ApprovalNotFoundError,
)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRequestItem)
def approve_action_request(
    approval_id: str,
    req: Optional[ApproveActionRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalRequestItem:
    """
    Approves a pending action approval request on an authorized run.
    """
    approval_record = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not approval_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ApprovalRequest '{approval_id}' not found")
    _get_authorized_run(approval_record.agent_run_id, current_user, db)

    try:
        resolved_by = req.resolved_by if req and req.resolved_by else current_user.username
        approval = agent_service.approve_action(db, approval_id=approval_id, resolved_by=resolved_by)
        return _serialize_approval_request(approval)
    except ApprovalNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except ApprovalInvalidStateError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        logger.error(f"Approve action request error: {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRequestItem)
def reject_action_request(
    approval_id: str,
    req: RejectActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalRequestItem:
    """
    Rejects a pending action approval request with human feedback reason on an authorized run.
    """
    approval_record = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not approval_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ApprovalRequest '{approval_id}' not found")
    _get_authorized_run(approval_record.agent_run_id, current_user, db)

    try:
        resolved_by = req.resolved_by if req.resolved_by else current_user.username
        approval = agent_service.reject_action(
            db, approval_id=approval_id, reason=req.reason, resolved_by=resolved_by
        )
        return _serialize_approval_request(approval)
    except ApprovalNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except ApprovalInvalidStateError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        logger.error(f"Reject action request error: {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/changes", response_model=WorkspaceChangesResponse)
def get_run_changes(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceChangesResponse:
    """
    Returns modified, added, deleted files and unified diff for an authorized run.
    """
    run = _get_authorized_run(run_id, current_user, db)
    try:
        return _compute_workspace_changes(run)
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        logger.error(f"Get changes error for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/verification", response_model=Dict[str, Any])
def get_run_verification(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns latest multi-vector verification results and defect reports for an authorized run.
    """
    run = _get_authorized_run(run_id, current_user, db)
    try:
        verif = run.metadata_json.get("verification_result") if run.metadata_json else None
        if not verif:
            return {
                "agent_run_id": run.id,
                "status": "NOT_STARTED",
                "passed": False,
                "checks": [],
                "defects": [],
                "summary": "No verification checks executed yet.",
            }
        return verif
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except Exception as err:
        logger.error(f"Get verification error for run '{run_id}': {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/runs/{run_id}/events/stream")
async def stream_agent_events(
    run_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Server-Sent Events (SSE) stream for real-time AgentRun events for an authorized user.
    """
    logger.info(f"[STREAM] GET /runs/{run_id}/events/stream - User: {current_user.id if current_user else 'unknown'}")
    run = _get_authorized_run(run_id, current_user, db)
    logger.info(f"[STREAM] SSE stream opened for run '{run_id}', historical events: {len(run.events or [])}")

    channel = f"agent:{run.id}"
    queue = task_manager.subscribe(current_user.id, channel)
    logger.info(f"[STREAM] Subscribed to channel: {channel}")

    async def event_generator():
        try:
            # 1. Replay historical events with sequence numbers
            historical_count = 0
            for idx, evt in enumerate(run.events or []):
                historical_count += 1
                evt_dict = {
                    "event_id": evt.id,
                    "sequence": idx + 1,
                    "agent_run_id": run.id,
                    "task_id": run.task_id,
                    "event_type": evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type),
                    "message": evt.message,
                    "payload": evt.payload or {},
                    "created_at": evt.created_at.isoformat() if evt.created_at else None,
                    "timestamp": evt.created_at.isoformat() if evt.created_at else None,
                }
                logger.debug(f"[STREAM] Replaying historical event #{idx+1}: {evt.event_type}")
                yield {
                    "event": evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type),
                    "data": json.dumps(evt_dict),
                }
            logger.info(f"[STREAM] Replayed {historical_count} historical events, now waiting for live events")

            # 2. Stream live events
            seq_counter = len(run.events or [])
            live_event_count = 0
            while True:
                if await request.is_disconnected():
                    logger.info(f"[STREAM] Client disconnected from stream for run '{run_id}'")
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                    seq_counter += 1
                    live_event_count += 1
                    logger.info(f"[STREAM] Received live event #{live_event_count} (sequence {seq_counter}): {payload[:100]}")
                    try:
                        parsed = json.loads(payload)
                        if isinstance(parsed, dict) and "sequence" not in parsed:
                            parsed["sequence"] = seq_counter
                            parsed.setdefault("event_id", f"live-{seq_counter}")
                            payload = json.dumps(parsed)
                    except Exception:
                        pass
                    yield {"data": payload}
                except asyncio.TimeoutError:
                    logger.debug(f"[STREAM] Keepalive for run '{run_id}'")
                    yield {"comment": "keepalive"}
        finally:
            logger.info(f"[STREAM] Closing stream for run '{run_id}' - live events received: {live_event_count}")
            task_manager.unsubscribe(current_user.id, channel, queue)

    return EventSourceResponse(event_generator())


@router.get("/tools", response_model=List[Dict[str, Any]])
def list_agent_tools(
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Returns safe, serializable catalog of registered agent tool schemas and policy states.
    Handlers are strictly internal and never exposed.
    """
    return agent_service.tools.list_catalog()

