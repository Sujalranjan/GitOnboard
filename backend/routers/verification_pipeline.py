"""
FastAPI Router for End-to-End Verification Pipeline (/api/v1/pipeline).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.database import get_db
from backend.models.implementation import AgentRun, FileChange
from backend.task_manager import task_manager
from backend.verification import (
    Defect,
    VerificationOrchestrator,
    VerificationReport,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["Verification Pipeline"])
orchestrator = VerificationOrchestrator()

_EVENT_CHANNEL_USER_ID = 0  # matches backend.services.agent_events._EVENT_CHANNEL_USER_ID

# In-memory store for worktree paths keyed by task_id (P7: worktree persistence)
_task_worktree_paths: Dict[str, str] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Request & Response Schemas
# ──────────────────────────────────────────────────────────────────────────────

class SubmitTaskRequest(BaseModel):
    repo_name: str = Field(default="default", description="Target repository name or ID")
    prompt: str = Field(description="Natural language feature requirement prompt")


class SubmitTaskResponse(BaseModel):
    task_id: str
    repo_name: str
    contract: Dict[str, Any]
    status: str = "CONTRACT_GENERATED"


class ExecuteTaskRequest(BaseModel):
    repo_name: str = Field(default="default")
    contract_id: Optional[str] = None
    contract_data: Optional[Dict[str, Any]] = None


class ExecuteTaskResponse(BaseModel):
    task_id: str
    run_id: str
    diff: str
    report: VerificationReport
    iteration: int = 1


class RepairTaskRequest(BaseModel):
    repo_name: str = Field(default="default")
    defects: List[Defect] = Field(default_factory=list)
    iteration: int = Field(default=1)
    contract_data: Optional[Dict[str, Any]] = None


class RepairTaskResponse(BaseModel):
    task_id: str
    run_id: str
    diff: str
    report: VerificationReport
    iteration: int
    status: str


# ──────────────────────────────────────────────────────────────────────────────
# Router Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/task/submit", response_model=SubmitTaskResponse)
async def submit_pipeline_task(
    req: SubmitTaskRequest,
    db: Session = Depends(get_db),
) -> SubmitTaskResponse:
    """
    Step 1: Accepts feature prompt requirement and synthesizes an ImplementationContract JSON.
    """
    logger.info(f"Pipeline: Submitting task requirement for repo '{req.repo_name}'")
    contract = await orchestrator.generate_contract(req.repo_name, req.prompt, db)
    task_id = f"task-{int(contract.get('id', '0').replace('contract-', '') if isinstance(contract.get('id'), str) else contract.get('id', 0))}"

    return SubmitTaskResponse(
        task_id=task_id,
        repo_name=req.repo_name,
        contract=contract,
        status="CONTRACT_GENERATED",
    )


@router.post("/task/{task_id}/execute", response_model=ExecuteTaskResponse)
async def execute_pipeline_task(
    task_id: str,
    req: ExecuteTaskRequest,
    db: Session = Depends(get_db),
) -> ExecuteTaskResponse:
    """
    Step 2: Spawns isolated Git worktree sandbox, runs agent patch, and executes Multi-Vector Verification.
    """
    logger.info(f"Pipeline: Executing sandboxed task '{task_id}' for repo '{req.repo_name}'")

    contract_data = req.contract_data or {
        "id": req.contract_id or f"contract-{task_id}",
        "requirement": "Requirement implementation",
        "required_endpoints": [],
        "expected_components": [],
        "invariants": ["Implementation must satisfy the stated requirement"],
        "affected_components": [],
    }

    # 1. Run agent inside Git worktree
    wt_path, raw_diff, mod_files = await orchestrator.run_agent(req.repo_name, contract_data, task_id, db=db)

    # Store worktree path for repair step (P7: worktree persistence)
    _task_worktree_paths[task_id] = str(wt_path)

    # 2. Run multi-vector verification
    report = orchestrator.verify_run(
        run_id=task_id,
        repo_id=req.repo_name,
        worktree_path=wt_path,
        contract_data=contract_data,
        modified_files=mod_files,
        git_diff=raw_diff,
        db=db,
    )

    return ExecuteTaskResponse(
        task_id=task_id,
        run_id=task_id,
        diff=raw_diff,
        report=report,
        iteration=1,
    )


@router.post("/task/{task_id}/repair", response_model=RepairTaskResponse)
async def repair_pipeline_task(
    task_id: str,
    req: RepairTaskRequest,
    db: Session = Depends(get_db),
) -> RepairTaskResponse:
    """
    Step 3: Executes Adversarial Repair Loop bounded strictly to 3 iterations.
    """
    logger.info(f"Pipeline: Executing repair iteration {req.iteration}/3 for task '{task_id}'")

    contract_data = req.contract_data or {
        "id": f"contract-{task_id}",
        "requirement": "Requirement implementation",
        "required_endpoints": [],
        "expected_components": [],
        "invariants": ["Implementation must satisfy the stated requirement"],
    }

    # P7: Retrieve stored worktree path from execute step
    stored_path = _task_worktree_paths.get(task_id)
    if stored_path:
        wt_path = Path(stored_path).resolve()
    else:
        wt_path = (Path(settings.worktrees_dir) / f"{req.repo_name}_{task_id}").resolve()
    wt_path.mkdir(parents=True, exist_ok=True)

    report, status_str, repaired_diff = await orchestrator.judge_and_repair(
        task_id=task_id,
        repo_id=req.repo_name,
        worktree_path=wt_path,
        contract_data=contract_data,
        defects=req.defects,
        iteration=req.iteration,
        db=db,
    )

    return RepairTaskResponse(
        task_id=task_id,
        run_id=task_id,
        diff=repaired_diff,
        report=report,
        iteration=req.iteration,
        status=status_str,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Agent Events (SSE) & Structured Diff
# ──────────────────────────────────────────────────────────────────────────────

class FileChangeResponse(BaseModel):
    file_path: str
    change_type: str
    lines_added: int
    lines_removed: int
    diff_patch: Optional[str] = None


@router.get("/task/{task_id}/events/stream")
async def stream_agent_events(task_id: str, request: Request, db: Session = Depends(get_db)):
    """
    SSE stream of AgentEvent rows for a task_id's most recent AgentRun. Reuses the
    same TaskManager pub/sub as /api/repos/{repo_name}/tasks/stream rather than a
    second streaming mechanism.
    """

    async def event_generator():
        channel = f"agent:{task_id}"
        queue = task_manager.subscribe(_EVENT_CHANNEL_USER_ID, channel)
        try:
            agent_run = (
                db.query(AgentRun)
                .filter(AgentRun.task_id == task_id)
                .order_by(AgentRun.started_at.desc())
                .first()
            )
            if agent_run:
                for evt in agent_run.events:
                    yield {
                        "data": json.dumps(
                            {
                                "event_type": evt.event_type.value if hasattr(evt.event_type, "value") else evt.event_type,
                                "message": evt.message,
                                "payload": evt.payload,
                                "created_at": evt.created_at.isoformat() if evt.created_at else None,
                            }
                        )
                    }

            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {"data": payload}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            task_manager.unsubscribe(_EVENT_CHANNEL_USER_ID, channel, queue)

    return EventSourceResponse(event_generator())


@router.get("/task/{task_id}/changes", response_model=List[FileChangeResponse])
async def get_task_file_changes(task_id: str, db: Session = Depends(get_db)) -> List[FileChangeResponse]:
    """Returns the persisted, structured FileChange rows for a task's latest AgentRun."""
    agent_run = (
        db.query(AgentRun)
        .filter(AgentRun.task_id == task_id)
        .order_by(AgentRun.started_at.desc())
        .first()
    )
    if not agent_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No agent run found for task_id '{task_id}'")

    changes = (
        db.query(FileChange)
        .filter(FileChange.agent_run_id == agent_run.id)
        .order_by(FileChange.created_at)
        .all()
    )
    return [
        FileChangeResponse(
            file_path=c.file_path,
            change_type=c.change_type.value if hasattr(c.change_type, "value") else c.change_type,
            lines_added=c.lines_added,
            lines_removed=c.lines_removed,
            diff_patch=c.diff_patch,
        )
        for c in changes
    ]
