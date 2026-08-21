"""
FastAPI Router for Engineering Agent Subsystem (/api/v1/agent).

Provides endpoints for creating, inspecting, controlling, and streaming agent runs.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from backend.models.implementation import AgentEvent, AgentRun, AgentState
from backend.task_manager import task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["Engineering Agent"])
agent_service = EngineeringAgent()

_EVENT_CHANNEL_USER_ID = 0


# ──────────────────────────────────────────────────────────────────────────────
# Request & Response Schemas
# ──────────────────────────────────────────────────────────────────────────────

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
    event_type: str
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


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



# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/runs", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
def create_agent_run(
    req: CreateAgentRunRequest,
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Creates and initializes a new EngineeringAgent session in UNDERSTANDING state.
    """
    try:
        run = agent_service.create_run(
            db=db,
            repository_id=req.repository_id,
            user_requirement=req.user_requirement,
            config=req.config,
        )
        return _serialize_run(run)
    except EngineeringAgentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Error creating agent run: {err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create agent run")


@router.get("/runs/{run_id}", response_model=AgentRunDetailResponse)
def get_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
) -> AgentRunDetailResponse:
    """
    Retrieves full lifecycle state, transition history, and events for an agent run.
    """
    try:
        run = agent_service.get_run(db, run_id)
        return _serialize_run_detail(run)
    except RunNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.post("/runs/{run_id}/transition", response_model=AgentRunResponse)
def transition_agent_state(
    run_id: str,
    req: TransitionStateRequest,
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Applies a validated state transition to an active agent run.
    """
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
    db: Session = Depends(get_db),
) -> ControlledActionResponse:
    """
    Executes a controlled deterministic operation inside the agent run lifecycle.
    """
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
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Cancels an active agent run, locking it into terminal CANCELLED state.
    """
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
    db: Session = Depends(get_db),
) -> List[EventItem]:
    """
    Returns persisted historical events for an agent run.
    """
    run = agent_service.get_run(db, run_id)
    return [
        EventItem(
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
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Assembles and returns structured repository evidence for an active run.
    """
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
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Synthesizes and validates an implementation plan for the run.
    Transitions run to AWAITING_APPROVAL upon successful validation.
    """
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
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieves the current implementation plan for an agent run.
    """
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
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Explicitly approves the synthesized plan.
    CRITICAL INVARIANT: Approval does NOT execute tasks (PLAN_APPROVED != TASK_EXECUTION_STARTED).
    """
    try:
        run = agent_service.approve_plan(db=db, run_id=run_id)
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
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Explicitly rejects the plan and transitions run back to PLANNING for revision.
    CRITICAL INVARIANT: Rejection NEVER triggers task implementation.
    """
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
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    """
    Starts controlled execution of the approved implementation plan.
    Strict preconditions: Run must be in AWAITING_APPROVAL and Plan must be APPROVED.
    """
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
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Executes the next eligible task deterministically according to DAG dependencies.
    """
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
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns all tasks and current lifecycle statuses for the run.
    """
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
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns details of an individual task by task_id.
    """
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


@router.get("/runs/{run_id}/events/stream")
async def stream_agent_events(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Server-Sent Events (SSE) stream for real-time AgentRun events.
    Reuses existing TaskManager pub/sub infrastructure.
    """
    try:
        run = agent_service.get_run(db, run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"AgentRun '{run_id}' not found")

    channel = f"agent:{run.id}"
    queue = task_manager.subscribe(_EVENT_CHANNEL_USER_ID, channel)

    async def event_generator():
        try:
            # 1. Replay historical events
            for evt in run.events:
                yield {
                    "event": evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type),
                    "data": json.dumps(
                        {
                            "agent_run_id": run.id,
                            "task_id": run.task_id,
                            "event_type": evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type),
                            "message": evt.message,
                            "payload": evt.payload or {},
                            "created_at": evt.created_at.isoformat() if evt.created_at else None,
                        }
                    ),
                }

            # 2. Stream live events
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield {"data": payload}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            task_manager.unsubscribe(_EVENT_CHANNEL_USER_ID, channel, queue)

    return EventSourceResponse(event_generator())


@router.get("/tools", response_model=List[Dict[str, Any]])
def list_agent_tools() -> List[Dict[str, Any]]:
    """
    Returns safe, serializable catalog of registered agent tool schemas and policy states.
    Handlers are strictly internal and never exposed.
    """
    return agent_service.tools.list_catalog()


# ──────────────────────────────────────────────────────────────────────────────
# Serialization Helpers
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
    events = [
        EventItem(
            event_type=e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
            message=e.message,
            payload=e.payload or {},
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in (run.events or [])
    ]
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
