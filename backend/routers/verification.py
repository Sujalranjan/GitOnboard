"""
FastAPI Router for Verification Mesh & Automated Repair Loop (/api/v1/verify, /api/v1/repair).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.implementation import Implementation, ImplementationContract, ImplementationStatus
from backend.services.git_manager import GitManager, GitManagerError
from backend.verification import (
    ContractVerifier,
    Defect,
    DynamicVerifier,
    Judge,
    StaticVerifier,
    VerificationReport,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Verification & Repair"])
git_manager = GitManager()


# ──────────────────────────────────────────────────────────────────────────────
# Request & Response Schemas
# ──────────────────────────────────────────────────────────────────────────────

class VerifyRunRequest(BaseModel):
    run_id: str = Field(description="Unique run ID or implementation ID")
    repo_id: Union[str, int] = Field(default="default", description="Repository ID or name")
    worktree_path: Optional[str] = Field(default=None, description="Path to isolated worktree sandbox")
    contract_id: Optional[str] = Field(default=None, description="ImplementationContract ID or Implementation ID")
    base_branch: str = Field(default="main", description="Base branch to compare diff against")


class RepairIterateRequest(BaseModel):
    run_id: str = Field(description="Unique run ID or implementation ID")
    repo_id: Union[str, int] = Field(default="default", description="Repository ID or name")
    worktree_path: Optional[str] = Field(default=None, description="Path to isolated worktree sandbox")
    defects: List[Defect] = Field(default_factory=list, description="Defects identified in previous run")
    iteration: int = Field(default=1, description="Current repair iteration count (1..3)")
    contract_id: Optional[str] = Field(default=None, description="ImplementationContract ID")
    patch_text: Optional[str] = Field(default=None, description="Corrective patch text if available")


class RepairIterateResponse(BaseModel):
    run_id: str
    status: str  # "VERIFIED", "REPAIRING", "UNRESOLVED", "FAILED"
    iteration: int
    message: str
    verification_report: Optional[VerificationReport] = None
    repaired_diff: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/verify/run", response_model=VerificationReport)
async def run_verification(
    req: VerifyRunRequest,
    db: Session = Depends(get_db),
) -> VerificationReport:
    """
    Executes Multi-Vector Verification (Static, Dynamic, Contract) on an isolated Git worktree.
    Aggregates evidence into a structured VerificationReport.
    """
    logger.info(f"Received verification request for run '{req.run_id}', repo_id='{req.repo_id}'")

    # 1. Resolve worktree path
    wt_path: Path
    if req.worktree_path and Path(req.worktree_path).exists():
        wt_path = Path(req.worktree_path).resolve()
    else:
        # Check standard worktree path data/worktrees/<repo_id>_<run_id>
        default_wt = Path(settings.worktrees_dir) / f"{req.repo_id}_{req.run_id}"
        if default_wt.exists():
            wt_path = default_wt.resolve()
        else:
            # Fallback: create worktree from source repo if needed
            try:
                wt_path = git_manager.create_worktree(
                    repo_id=req.repo_id,
                    run_id=req.run_id,
                    base_branch=req.base_branch,
                )
            except GitManagerError as err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not resolve or create Git worktree sandbox: {err}",
                )

    # 2. Extract git diff & modified files list
    git_diff = git_manager.get_diff(wt_path, base_branch=req.base_branch)
    modified_files = git_manager.list_modified_files(wt_path, base_branch=req.base_branch)

    # 3. Load ImplementationContract from DB if available
    contract_data: Dict[str, Any] = {}
    contract_id = req.contract_id or req.run_id
    contract_record = db.query(ImplementationContract).filter(
        (ImplementationContract.id == contract_id) | (ImplementationContract.implementation_id == contract_id)
    ).first()

    if contract_record:
        contract_data = {
            "affected_components": contract_record.affected_components or [],
            "tests_required": contract_record.tests_required or [],
            "acceptance_criteria": contract_record.acceptance_criteria or [],
            "security_considerations": contract_record.security_considerations or [],
        }

    # 4. Execute Multi-Vector Verification Mesh
    static_result = StaticVerifier().verify(wt_path, modified_files, git_diff)
    dynamic_result = DynamicVerifier().verify(wt_path, modified_files)
    contract_result = ContractVerifier().verify(contract_data, modified_files, git_diff)

    # 5. Aggregate evidence via Judge
    report = Judge().aggregate(req.run_id, static_result, dynamic_result, contract_result)

    # 6. Update Implementation status in database if tracking record exists
    impl_record = db.query(Implementation).filter(Implementation.id == req.run_id).first()
    if impl_record:
        impl_record.status = (
            ImplementationStatus.VERIFIED if report.passed else ImplementationStatus.FAILED
        )
        impl_record.worktree_path = str(wt_path)
        db.commit()

    return report


@router.post("/repair/iterate", response_model=RepairIterateResponse)
async def iterate_repair(
    req: RepairIterateRequest,
    db: Session = Depends(get_db),
) -> RepairIterateResponse:
    """
    Executes automated defect repair loop bounded to a maximum of 3 iterations.
    Applies corrective patches to the worktree and re-runs multi-vector verification.
    """
    logger.info(
        f"Received repair iteration request for run '{req.run_id}', iteration={req.iteration}/3"
    )

    # 1. Enforce Bounded Iteration Guard (Max 3 passes)
    if req.iteration > 3:
        logger.warning(f"Repair iteration {req.iteration} exceeds maximum allowed passes (3). Marking UNRESOLVED.")
        return RepairIterateResponse(
            run_id=req.run_id,
            status="UNRESOLVED",
            iteration=req.iteration,
            message="Maximum repair attempts (3) exceeded. Remaining defects require manual review.",
            verification_report=None,
            repaired_diff=None,
        )

    # 2. Resolve worktree path
    wt_path: Path
    if req.worktree_path and Path(req.worktree_path).exists():
        wt_path = Path(req.worktree_path).resolve()
    else:
        wt_path = (Path(settings.worktrees_dir) / f"{req.repo_id}_{req.run_id}").resolve()
        if not wt_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worktree sandbox not found at {wt_path}",
            )

    # 3. Apply corrective patch if provided, or format defects for repair patch
    if req.patch_text and req.patch_text.strip():
        applied = git_manager.apply_patch(wt_path, req.patch_text)
        if not applied:
            logger.warning(f"Failed to apply repair patch on iteration {req.iteration}")
    else:
        # Format repair instructions for LLM repair service
        defect_summary = "\n".join(
            f"- [{d.category}] {d.file_path}: {d.description}" for d in req.defects
        )
        logger.info(f"Formated {len(req.defects)} defect(s) for repair agent prompt:\n{defect_summary}")

    # 4. Re-execute Multi-Vector Verification
    git_diff = git_manager.get_diff(wt_path)
    modified_files = git_manager.list_modified_files(wt_path)

    contract_data: Dict[str, Any] = {}
    contract_id = req.contract_id or req.run_id
    contract_record = db.query(ImplementationContract).filter(
        (ImplementationContract.id == contract_id) | (ImplementationContract.implementation_id == contract_id)
    ).first()

    if contract_record:
        contract_data = {
            "affected_components": contract_record.affected_components or [],
            "tests_required": contract_record.tests_required or [],
            "acceptance_criteria": contract_record.acceptance_criteria or [],
        }

    static_res = StaticVerifier().verify(wt_path, modified_files, git_diff)
    dynamic_res = DynamicVerifier().verify(wt_path, modified_files)
    contract_res = ContractVerifier().verify(contract_data, modified_files, git_diff)

    report = Judge().aggregate(req.run_id, static_res, dynamic_res, contract_res)

    # 5. Determine repair loop state
    if report.passed:
        final_status = "VERIFIED"
        message = f"Repair iteration {req.iteration} successfully resolved all defects."
    elif req.iteration >= 3:
        final_status = "UNRESOLVED"
        message = f"Repair iteration {req.iteration} completed with remaining unresolved defects."
    else:
        final_status = "REPAIRING"
        message = f"Repair iteration {req.iteration} completed with {len(report.defects)} remaining defect(s). Ready for next iteration."

    # Update database status if record exists
    impl_record = db.query(Implementation).filter(Implementation.id == req.run_id).first()
    if impl_record:
        impl_record.status = (
            ImplementationStatus.VERIFIED if report.passed
            else (ImplementationStatus.REPAIRING if req.iteration < 3 else ImplementationStatus.FAILED)
        )
        db.commit()

    return RepairIterateResponse(
        run_id=req.run_id,
        status=final_status,
        iteration=req.iteration,
        message=message,
        verification_report=report,
        repaired_diff=git_diff,
    )
