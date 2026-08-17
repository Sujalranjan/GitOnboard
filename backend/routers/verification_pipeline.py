"""
FastAPI Router for End-to-End Verification Pipeline (/api/v1/pipeline).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.verification import (
    Defect,
    VerificationOrchestrator,
    VerificationReport,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["Verification Pipeline"])
orchestrator = VerificationOrchestrator()


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
    contract = orchestrator.generate_contract(req.repo_name, req.prompt, db)
    task_id = f"task-{int(contract.get('id', '0').replace('contract-', ''))}"

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
        "required_endpoints": ["POST /api/todos", "GET /api/todos"],
        "expected_components": ["src/pages/api/todos.ts"],
        "invariants": ["Request payload validation required using schema"],
        "affected_components": [{"file": "src/pages/api/todos.ts", "symbol": "handler"}],
    }

    # 1. Run agent inside Git worktree
    wt_path, raw_diff, mod_files = orchestrator.run_agent(req.repo_name, contract_data, task_id)

    # 2. Run multi-vector verification
    report = orchestrator.verify_run(
        run_id=task_id,
        repo_id=req.repo_name,
        worktree_path=wt_path,
        contract_data=contract_data,
        modified_files=mod_files,
        git_diff=raw_diff,
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
        "required_endpoints": ["POST /api/todos", "GET /api/todos"],
        "expected_components": ["src/pages/api/todos.ts"],
        "invariants": ["Request payload validation required using schema"],
    }

    wt_path = (Path(settings.worktrees_dir) / f"{req.repo_name}_{task_id}").resolve()
    wt_path.mkdir(parents=True, exist_ok=True)

    report, status_str, repaired_diff = orchestrator.judge_and_repair(
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
