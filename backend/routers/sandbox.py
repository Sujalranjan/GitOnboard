"""
Sandbox Router: Endpoints for executing commands and managing persistent shell sessions in worktree sandboxes.
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


class SandboxSessionCreateRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Optional custom session identifier")


class SandboxSessionResponse(BaseModel):
    session_id: str
    run_id: str
    worktree_path: str
    created_at: float
    cwd: str


class SandboxExecRequest(BaseModel):
    command: str = Field(..., description="The CLI command to execute inside the run worktree sandbox")
    timeout_sec: Optional[int] = Field(30, ge=1, le=120, description="Execution timeout in seconds (1-120)")
    session_id: Optional[str] = Field(None, description="Optional persistent session identifier")


class SandboxExecResponse(BaseModel):
    run_id: str
    command: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    output_truncated: bool = False
    duration_ms: float
    session_id: Optional[str] = None
    cwd: Optional[str] = None


@router.post("/{run_id}/session", response_model=SandboxSessionResponse)
async def create_sandbox_session(
    run_id: str,
    request: Optional[SandboxSessionCreateRequest] = None,
) -> SandboxSessionResponse:
    """
    Creates or retrieves a persistent interactive shell session for the given run_id.
    Preserves cwd, environment variables, and shell state across commands.
    """
    try:
        req_session_id = request.session_id if request else None
        session = await sandbox_manager.get_or_create_session(
            run_id=run_id,
            session_id=req_session_id,
        )
        return SandboxSessionResponse(
            session_id=session.session_id,
            run_id=session.run_id,
            worktree_path=str(session.worktree_path),
            created_at=session.created_at,
            cwd=session._current_cwd,
        )
    except InvalidRunError as e:
        logger.warning(f"Invalid sandbox run_id '{run_id}': {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except WorktreeNotFoundError as e:
        logger.warning(f"Worktree not found for run_id '{run_id}': {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating session for run_id '{run_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create sandbox session: {str(e)}")


@router.delete("/{run_id}/session/{session_id}")
async def close_sandbox_session(
    run_id: str,
    session_id: str,
) -> dict:
    """
    Closes and terminates a persistent shell session, freeing process and temp resources.
    """
    try:
        await sandbox_manager.close_session(session_id=session_id)
        return {"status": "CLOSED", "session_id": session_id, "run_id": run_id}
    except Exception as e:
        logger.error(f"Error closing session '{session_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to close session: {str(e)}")


@router.post("/{run_id}/exec", response_model=SandboxExecResponse)
async def exec_sandbox_command(
    run_id: str,
    request: SandboxExecRequest,
) -> SandboxExecResponse:
    """
    Executes a shell command inside the persistent shell session for the validated run worktree sandbox.
    Returns real stdout, stderr, exit code, timeout, truncation metadata, session_id, and current cwd.
    """
    try:
        result = await sandbox_manager.execute_command(
            run_id=run_id,
            command=request.command,
            timeout_sec=request.timeout_sec,
            session_id=request.session_id,
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
            session_id=result.session_id,
            cwd=result.cwd,
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

