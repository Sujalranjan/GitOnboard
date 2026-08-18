"""
Sandbox Router: Endpoints for executing commands in isolated worktree sandboxes.
"""
from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.sandbox_manager import (
    SandboxManager,
    SandboxError,
    InvalidRunError,
    WorktreeNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sandbox", tags=["sandbox"])
sandbox_manager = SandboxManager()


class SandboxExecRequest(BaseModel):
    command: str = Field(..., description="The CLI command to execute inside the run worktree sandbox")
    timeout_sec: Optional[int] = Field(30, ge=1, le=120, description="Execution timeout in seconds (1-120)")


class SandboxExecResponse(BaseModel):
    run_id: str
    command: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    output_truncated: bool = False
    duration_ms: float


@router.post("/{run_id}/exec", response_model=SandboxExecResponse)
async def exec_sandbox_command(
    run_id: str,
    request: SandboxExecRequest,
) -> SandboxExecResponse:
    """
    Executes a shell command inside the validated run worktree sandbox.
    Returns real stdout, stderr, exit code, timeout, and truncation metadata.
    """
    try:
        result = await sandbox_manager.execute_command(
            run_id=run_id,
            command=request.command,
            timeout_sec=request.timeout_sec,
        )

        return SandboxExecResponse(
            run_id=result.run_id,
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            output_truncated=result.output_truncated,
            duration_ms=result.duration_ms,
        )
    except InvalidRunError as e:
        logger.warning(f"Invalid sandbox run_id '{run_id}': {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except WorktreeNotFoundError as e:
        logger.warning(f"Worktree not found for run_id '{run_id}': {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxError as e:
        logger.error(f"Sandbox execution error for run_id '{run_id}': {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected sandbox error for run_id '{run_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal sandbox execution error: {str(e)}")
