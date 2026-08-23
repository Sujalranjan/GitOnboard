"""
FastAPI Router for Verification Mesh & Automated Repair Loop (/api/v1/verify, /api/v1/repair).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.models.implementation import AgentRun, Implementation, ImplementationContract, ImplementationStatus
from backend.models.repository import Repository
from backend.models.user import User
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
# Security Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _verify_verification_ownership(
    run_id: str,
    repo_id: Union[str, int],
    current_user: User,
    db: Session,
) -> Tuple[Optional[AgentRun], Optional[Implementation]]:
    """
    Verifies that the current_user owns the run, implementation, or repository.
    Rejects unauthorized access with 403 Forbidden.
    """
    run = db.query(AgentRun).filter((AgentRun.id == run_id) | (AgentRun.task_id == run_id)).first()
    impl = db.query(Implementation).filter(Implementation.id == run_id).first()
    repo = None
    if repo_id != "default":
        repo = db.query(Repository).filter(
            (Repository.id == (int(repo_id) if str(repo_id).isdigit() else -1)) |
            (Repository.url.endswith(f"/{repo_id}")) |
            (Repository.url.endswith(f"/{repo_id}.git"))
        ).first()

    if run:
        if run.user_id is not None:
            if run.user_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: not run owner")
        else:
            is_owned = False
            if run.repository_id:
                r = db.query(Repository).filter(
                    (Repository.id == (int(run.repository_id) if run.repository_id.isdigit() else -1)) |
                    (Repository.url.endswith(f"/{run.repository_id}")) |
                    (Repository.url.endswith(f"/{run.repository_id}.git"))
                ).first()
                if r and r.user_id == current_user.id:
                    is_owned = True
            if not is_owned and run.implementation_id:
                i = db.query(Implementation).filter(Implementation.id == run.implementation_id).first()
                if i and i.user_id == current_user.id:
                    is_owned = True
            if not is_owned:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: unverified legacy run owner")
    elif impl:
        if impl.user_id is not None and impl.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: not implementation owner")
    elif repo:
        if repo.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: not repository owner")

    return run, impl


def _validate_and_resolve_worktree(
    worktree_path: Optional[str],
    run_id: str,
    repo_id: Union[str, int],
    expected_worktree_path: Optional[str] = None,
) -> Path:
    """
    Validates that worktree_path is strictly contained within settings.worktrees_dir,
    is a real directory, does not escape via traversal or symlinks, and matches the expected run.
    """
    base_dir = Path(settings.worktrees_dir).resolve()

    if worktree_path:
        wt_path = Path(worktree_path).resolve()

        # Enforce strict directory containment inside settings.worktrees_dir
        try:
            is_contained = wt_path.is_relative_to(base_dir) and wt_path != base_dir
        except AttributeError:
            is_contained = base_dir in wt_path.parents and wt_path != base_dir

        if not is_contained:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security violation: worktree_path must be strictly contained within worktrees directory",
            )

        if not wt_path.exists() or not wt_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worktree directory not found at {wt_path}",
            )

        # Enforce that the path corresponds to the expected run/repo
        if expected_worktree_path:
            expected_resolved = Path(expected_worktree_path).resolve()
            if wt_path != expected_resolved and run_id not in wt_path.name:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: worktree path does not correspond to requested run",
                )
        elif run_id not in wt_path.name:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: worktree path does not match run identifier",
            )

        return wt_path

    default_wt = (base_dir / f"{repo_id}_{run_id}").resolve()
    return default_wt


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerificationReport:
    """
    Executes Multi-Vector Verification (Static, Dynamic, Contract) on an isolated Git worktree.
    Enforces authentication, run/repo ownership, and strict worktree containment.
    """
    logger.info(f"Received verification request for run '{req.run_id}', repo_id='{req.repo_id}' by user '{current_user.id}'")

    # 1. Verify run/repository ownership
    run, impl = _verify_verification_ownership(req.run_id, req.repo_id, current_user, db)

    # 2. Resolve and contain worktree path
    expected_wt = (run.worktree_path if run else (impl.worktree_path if impl else None))
    if req.worktree_path:
        wt_path = _validate_and_resolve_worktree(req.worktree_path, req.run_id, req.repo_id, expected_wt)
    else:
        # Check standard worktree path data/worktrees/<repo_id>_<run_id>
        default_wt = _validate_and_resolve_worktree(None, req.run_id, req.repo_id)
        if default_wt.exists():
            wt_path = default_wt
        else:
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

    # 3. Extract git diff & modified files list
    git_diff = git_manager.get_diff(wt_path, base_branch=req.base_branch)
    modified_files = git_manager.list_modified_files(wt_path, base_branch=req.base_branch)

    # 4. Load ImplementationContract from DB if available
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

    # 5. Execute Multi-Vector Verification Mesh
    static_result = StaticVerifier().verify(wt_path, modified_files, git_diff)
    dynamic_result = DynamicVerifier().verify(wt_path, modified_files)
    contract_result = ContractVerifier().verify(contract_data, modified_files, git_diff)

    # 6. Aggregate evidence via Judge
    report = Judge().aggregate(req.run_id, static_result, dynamic_result, contract_result)

    # 7. Update Implementation status in database if tracking record exists
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RepairIterateResponse:
    """
    Executes automated defect repair loop bounded to a maximum of 3 iterations.
    Enforces authentication, run ownership, and strict worktree path containment.
    """
    logger.info(
        f"Received repair iteration request for run '{req.run_id}', iteration={req.iteration}/3 by user '{current_user.id}'"
    )

    # 1. Verify run/repository ownership
    run, impl = _verify_verification_ownership(req.run_id, req.repo_id, current_user, db)

    # 2. Enforce Bounded Iteration Guard (Max 3 passes)
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

    # 3. Resolve and contain worktree path
    expected_wt = (run.worktree_path if run else (impl.worktree_path if impl else None))
    wt_path = _validate_and_resolve_worktree(req.worktree_path, req.run_id, req.repo_id, expected_wt)
    if not wt_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worktree sandbox not found at {wt_path}",
        )

    # 4. Apply corrective patch if provided, or format defects for repair patch
    if req.patch_text and req.patch_text.strip():
        applied = git_manager.apply_patch(wt_path, req.patch_text)
        if not applied:
            logger.warning(f"Failed to apply repair patch on iteration {req.iteration}")
    else:
        defect_summary = "\n".join(
            f"- [{d.category}] {d.file_path}: {d.description}" for d in req.defects
        )
        logger.info(f"Formatted {len(req.defects)} defect(s) for repair agent prompt:\n{defect_summary}")

    # 5. Re-execute Multi-Vector Verification
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

    # 6. Determine repair loop state
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
