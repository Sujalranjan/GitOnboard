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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["Engineering Agent"])
agent_service = EngineeringAgent()
graph_orchestrator = AgentGraphOrchestrator(agent_service=agent_service)

_EVENT_CHANNEL_USER_ID = 0


# ──────────────────────────────────────────────────────────────────────────────
# Request & Response Schemas
# ──────────────────────────────────────────────────────────────────────────────

class ClassifyIntentRequest(BaseModel):
    requirement: str = Field(..., description="User prompt to classify")


class ClassifyIntentResponse(BaseModel):
    intent: str
    confidence: float
    reason: str
    method: str
    response: str


class CreateAgentRunRequest(BaseModel):
    repository_id: str = Field(..., description="Target repository name or identifier")
    user_requirement: str = Field(..., description="Natural language feature requirement")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional configuration parameters")


class StateTransitionItem(BaseModel):
    from_state: str
    to_state: str
    reason: Optional[str] = None
    timestamp: str


class EventItem(BaseModel):
    event_id: str
    sequence: int
    agent_run_id: str
    task_id: Optional[str] = None
    event_type: str
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    timestamp: Optional[str] = None


class AgentRunResponse(BaseModel):
    id: str
    task_id: str
    repository_id: Optional[str]
    user_requirement: Optional[str]
    current_state: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    error_message: Optional[str] = None


class AgentRunDetailResponse(AgentRunResponse):
    transitions: List[StateTransitionItem] = Field(default_factory=list)
    events: List[EventItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TransitionStateRequest(BaseModel):
    to_state: str = Field(..., description="Target AgentState (e.g. PLANNING, EXECUTING, VERIFYING, COMPLETED, FAILED)")
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ControlledActionRequest(BaseModel):
    action_type: str = Field(default="inspect_repository", description="Action to execute (e.g. inspect_repository, read_file, get_symbol)")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ControlledActionResponse(BaseModel):
    run_id: str
    action_type: str
    status: str
    duration_ms: float
    result: Dict[str, Any]


class CancelAgentRunRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Reason for cancellation")


class RejectPlanRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Reason for rejecting the plan")


class ApprovalRequestItem(BaseModel):
    id: str
    agent_run_id: str
    task_id: Optional[str] = None
    action_type: str
    action_description: str
    risk_level: str
    command: Optional[str] = None
    reason: Optional[str] = None
    status: str
    requested_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    rejection_reason: Optional[str] = None


class ApproveActionRequest(BaseModel):
    resolved_by: Optional[str] = Field(default="human_user", description="Identifier of human approving action")


class RejectActionRequest(BaseModel):
    reason: str = Field(..., description="Reason explaining why action was rejected")
    resolved_by: Optional[str] = Field(default="human_user", description="Identifier of human rejecting action")


class WorkspaceChangesResponse(BaseModel):
    agent_run_id: str
    worktree_path: Optional[str] = None
    modified_files: List[str] = Field(default_factory=list)
    added_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)
    diff: str = ""


class WorkspaceSnapshotResponse(BaseModel):
    run: AgentRunDetailResponse
    plan: Optional[Dict[str, Any]] = None
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    active_task: Optional[Dict[str, Any]] = None
    changes: WorkspaceChangesResponse
    verification: Optional[Dict[str, Any]] = None
    pending_approvals: List[ApprovalRequestItem] = Field(default_factory=list)
    latest_events: List[EventItem] = Field(default_factory=list)



from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

# ──────────────────────────────────────────────────────────────────────────────
# Authorization Helper
# ──────────────────────────────────────────────────────────────────────────────

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
    with SessionLocal() as db:
        try:
            logger.info(f"Starting background task execution for approved run '{run_id}'")
            while True:
                task, exec_res = agent_service.execute_next_task(db=db, run_id=run_id)
                if not task:
                    break
        except Exception as err:
            logger.error(f"Background task execution failed for run '{run_id}': {err}", exc_info=True)


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/classify", response_model=ClassifyIntentResponse)
def classify_intent_endpoint(
    req: ClassifyIntentRequest,
    current_user: User = Depends(get_current_user),
) -> ClassifyIntentResponse:
    """
    Direct endpoint for fast, synchronous intent classification and response synthesis.
    """
    from backend.agent.intent import IntentRouter, Intent
    router_inst = IntentRouter()
    result = router_inst.classify(req.requirement)

    responses = {
        Intent.CHAT: "Hello! I am your Repository Intelligence Assistant. You can ask me to explore files, explain architectures, plan features, or implement changes.",
        Intent.EXPLORE: f"Exploration query recognized for: '{req.requirement}'. The repository AST symbol tables and file layout are cataloged.",
        Intent.EXPLAIN: f"Explanation query recognized for: '{req.requirement}'. The codebase architecture models and call graphs are available for inspection.",
        Intent.PLAN: f"Plan intent recognized for: '{req.requirement}'. High-level DAG change estimation classified successfully.",
        Intent.IMPLEMENT: f"Implement intent recognized for: '{req.requirement}'. Code modification request classified successfully.",
        Intent.CLARIFY: f"Your request '{req.requirement}' is ambiguous or underspecified. Please specify which files, functions, or features you want to modify or inspect.",
    }

    return ClassifyIntentResponse(
        intent=result.intent.value,
        confidence=result.confidence,
        reason=result.reason,
        method=result.classification_method,
        response=responses.get(result.intent, "Request processed."),
    )


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


@router.post("/runs/{run_id}/plan/approve", response_model=AgentRunResponse)
def approve_run_plan(
    run_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Explicitly approves the synthesized plan and starts background execution of tasks.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        run = agent_service.approve_plan(db=db, run_id=run_id)
        run = agent_service.start_plan_execution(db=db, run_id=run_id)
        background_tasks.add_task(_background_execute_approved_plan, run_id)
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


@router.post("/runs/{run_id}/plan/reject", response_model=AgentRunResponse)
def reject_run_plan(
    run_id: str,
    req: Optional[RejectPlanRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Explicitly rejects the plan and transitions run back to PLANNING for revision.
    CRITICAL INVARIANT: Rejection NEVER triggers task implementation.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        reason = req.reason if req else None
        run = agent_service.reject_plan(db=db, run_id=run_id, reason=reason)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Starts controlled execution of the approved implementation plan.
    Strict preconditions: Run must be in AWAITING_APPROVAL and Plan must be APPROVED.
    """
    _get_authorized_run(run_id, current_user, db)
    try:
        run = agent_service.start_plan_execution(db=db, run_id=run_id)
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
    run = _get_authorized_run(run_id, current_user, db)
    try:
        plan = agent_service.get_plan(db, run_id)
        plan_dict = plan.model_dump(mode="json") if plan else None

        tasks = agent_service.get_plan_tasks(db, run_id)
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
    run = _get_authorized_run(run_id, current_user, db)

    channel = f"agent:{run.id}"
    queue = task_manager.subscribe(current_user.id, channel)

    async def event_generator():
        try:
            # 1. Replay historical events with sequence numbers
            for idx, evt in enumerate(run.events or []):
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
                yield {
                    "event": evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type),
                    "data": json.dumps(evt_dict),
                }

            # 2. Stream live events
            seq_counter = len(run.events or [])
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                    seq_counter += 1
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
                    yield {"comment": "keepalive"}
        finally:
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


# ──────────────────────────────────────────────────────────────────────────────
# Serialization & Workspace Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _serialize_run(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=run.id,
        task_id=run.task_id,
        repository_id=run.repository_id,
        user_requirement=run.user_requirement,
        current_state=run.current_state.value if hasattr(run.current_state, "value") else str(run.current_state),
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        started_at=run.started_at.isoformat() if run.started_at else "",
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        cancellation_reason=run.cancellation_reason,
        error_message=run.error_message,
    )


def _serialize_event(e: AgentEvent, seq: int = 0) -> EventItem:
    return EventItem(
        event_id=e.id,
        sequence=seq,
        agent_run_id=e.agent_run_id,
        task_id=getattr(e.agent_run, "task_id", None) if e.agent_run else None,
        event_type=e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
        message=e.message,
        payload=e.payload or {},
        created_at=e.created_at.isoformat() if e.created_at else "",
        timestamp=e.created_at.isoformat() if e.created_at else "",
    )


def _serialize_approval_request(a: ApprovalRequest) -> ApprovalRequestItem:
    return ApprovalRequestItem(
        id=a.id,
        agent_run_id=a.agent_run_id,
        task_id=a.task_id,
        action_type=a.action_type.value if hasattr(a.action_type, "value") else str(a.action_type),
        action_description=a.action_description,
        risk_level=a.risk_level.value if hasattr(a.risk_level, "value") else str(a.risk_level),
        command=a.command,
        reason=a.reason,
        status=a.status.value if hasattr(a.status, "value") else str(a.status),
        requested_at=a.requested_at.isoformat() if a.requested_at else "",
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        resolved_by=a.resolved_by,
        rejection_reason=a.rejection_reason,
    )


def _compute_workspace_changes(run: AgentRun) -> WorkspaceChangesResponse:
    import os
    import subprocess

    if not run.worktree_path or not os.path.exists(run.worktree_path):
        return WorkspaceChangesResponse(agent_run_id=run.id, worktree_path=run.worktree_path)

    try:
        st_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=run.worktree_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        mod_files: List[str] = []
        add_files: List[str] = []
        del_files: List[str] = []
        if st_proc.returncode == 0:
            for line in st_proc.stdout.splitlines():
                if not line.strip():
                    continue
                status_code = line[:2].strip()
                fpath = line[3:].strip()
                if "M" in status_code:
                    mod_files.append(fpath)
                elif "A" in status_code or "?" in status_code:
                    add_files.append(fpath)
                elif "D" in status_code:
                    del_files.append(fpath)
                else:
                    mod_files.append(fpath)

        diff_proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=run.worktree_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        diff_str = diff_proc.stdout if diff_proc.returncode == 0 else ""
        if not diff_str:
            diff_proc2 = subprocess.run(
                ["git", "diff"],
                cwd=run.worktree_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            diff_str = diff_proc2.stdout if diff_proc2.returncode == 0 else ""

        return WorkspaceChangesResponse(
            agent_run_id=run.id,
            worktree_path=run.worktree_path,
            modified_files=mod_files,
            added_files=add_files,
            deleted_files=del_files,
            diff=diff_str,
        )
    except Exception as err:
        logger.warning(f"Failed to compute workspace changes for run '{run.id}': {err}")
        return WorkspaceChangesResponse(agent_run_id=run.id, worktree_path=run.worktree_path)


def _serialize_run_detail(run: AgentRun) -> AgentRunDetailResponse:
    transitions = [
        StateTransitionItem(
            from_state=t.from_state.value if hasattr(t.from_state, "value") else str(t.from_state),
            to_state=t.to_state.value if hasattr(t.to_state, "value") else str(t.to_state),
            reason=t.reason,
            timestamp=t.timestamp.isoformat() if t.timestamp else "",
        )
        for t in (run.transitions or [])
    ]
    events = [_serialize_event(e, idx + 1) for idx, e in enumerate(run.events or [])]
    return AgentRunDetailResponse(
        id=run.id,
        task_id=run.task_id,
        repository_id=run.repository_id,
        user_requirement=run.user_requirement,
        current_state=run.current_state.value if hasattr(run.current_state, "value") else str(run.current_state),
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        started_at=run.started_at.isoformat() if run.started_at else "",
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        cancellation_reason=run.cancellation_reason,
        error_message=run.error_message,
        transitions=transitions,
        events=events,
        metadata=run.metadata_json or {},
    )
