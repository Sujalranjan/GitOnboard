"""
Sandbox Router: Endpoints for executing commands and managing persistent shell sessions in worktree sandboxes.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
import jwt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal, get_db
from backend.dependencies.auth import get_current_user
from backend.models.implementation import AgentRun, Implementation
from backend.models.repository import Repository
from backend.models.user import User
from backend.services.pty_session import PtyUnavailableError
from backend.services.sandbox_manager import (
    SandboxManager,
    SandboxError,
    InvalidRunError,
    WorktreeNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sandbox", tags=["sandbox"])
sandbox_manager = SandboxManager()


def verify_sandbox_run_owner(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRun:
    """
    Verifies that the authenticated user owns the AgentRun or Repository associated with run_id.
    """
    run = db.query(AgentRun).filter((AgentRun.id == run_id) | (AgentRun.task_id == run_id)).first()
    if not run:
        # Check if run_id is a repository owned by current_user
        repo = db.query(Repository).filter(
            Repository.user_id == current_user.id,
            (Repository.id == (int(run_id) if run_id.isdigit() else -1)) |
            (Repository.url.endswith(f"/{run_id}")) |
            (Repository.url.endswith(f"/{run_id}.git"))
        ).first()
        if repo:
            latest_run = db.query(AgentRun).filter(
                (AgentRun.repository_id == str(repo.id)) |
                (AgentRun.repository_id == run_id),
                AgentRun.user_id == current_user.id,
            ).order_by(AgentRun.created_at.desc()).first()
            if latest_run:
                return latest_run
            return AgentRun(
                id=run_id,
                task_id=f"workspace_{run_id}",
                repository_id=str(repo.id),
                user_id=current_user.id,
                user_requirement=f"Workspace shell for {run_id}",
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"AgentRun or repository '{run_id}' not found")

    if run.user_id is not None:
        if run.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: not run owner")
        return run

    # Legacy NULL user_id check
    is_owned = False
    if run.repository_id:
        repo = db.query(Repository).filter(
            (Repository.id == (int(run.repository_id) if run.repository_id.isdigit() else -1)) |
            (Repository.url.endswith(f"/{run.repository_id}")) |
            (Repository.url.endswith(f"/{run.repository_id}.git"))
        ).first()
        if repo and repo.user_id == current_user.id:
            is_owned = True

    if not is_owned and run.implementation_id:
        impl = db.query(Implementation).filter(Implementation.id == run.implementation_id).first()
        if impl and impl.user_id == current_user.id:
            is_owned = True

    if not is_owned:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: unverified legacy run owner")

    return run


def _authenticate_ws_run(websocket: WebSocket, run_id: str) -> Tuple[User, AgentRun]:
    """
    Authenticates and authorizes WebSocket connection from cookie before accepting.
    """
    token = websocket.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token cookie required")

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("user_id") or payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")
        user_id = int(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired authentication token")

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        run = db.query(AgentRun).filter((AgentRun.id == run_id) | (AgentRun.task_id == run_id)).first()
        if not run:
            # Check if run_id is a repository owned by user
            repo = db.query(Repository).filter(
                Repository.user_id == user.id,
                (Repository.id == (int(run_id) if run_id.isdigit() else -1)) |
                (Repository.url.endswith(f"/{run_id}")) |
                (Repository.url.endswith(f"/{run_id}.git"))
            ).first()
            if repo:
                latest_run = db.query(AgentRun).filter(
                    (AgentRun.repository_id == str(repo.id)) |
                    (AgentRun.repository_id == run_id),
                    AgentRun.user_id == user.id,
                ).order_by(AgentRun.created_at.desc()).first()
                if latest_run:
                    return user, latest_run
                return user, AgentRun(
                    id=run_id,
                    task_id=f"workspace_{run_id}",
                    repository_id=str(repo.id),
                    user_id=user.id,
                    user_requirement=f"Workspace shell for {run_id}",
                )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"AgentRun or repository '{run_id}' not found")

        is_owned = False
        if run.user_id is not None:
            is_owned = (run.user_id == user.id)
        else:
            if run.repository_id:
                repo = db.query(Repository).filter(
                    (Repository.id == (int(run.repository_id) if run.repository_id.isdigit() else -1)) |
                    (Repository.url.endswith(f"/{run.repository_id}")) |
                    (Repository.url.endswith(f"/{run.repository_id}.git"))
                ).first()
                if repo and repo.user_id == user.id:
                    is_owned = True
            if not is_owned and run.implementation_id:
                impl = db.query(Implementation).filter(Implementation.id == run.implementation_id).first()
                if impl and impl.user_id == user.id:
                    is_owned = True

        if not is_owned:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: not run owner")

        return user, run


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
    auth_run: AgentRun = Depends(verify_sandbox_run_owner),
) -> SandboxSessionResponse:
    """
    Creates or retrieves a persistent interactive shell session for an authorized run.
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
    auth_run: AgentRun = Depends(verify_sandbox_run_owner),
) -> dict:
    """
    Closes and terminates a persistent shell session on an authorized run.
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
    auth_run: AgentRun = Depends(verify_sandbox_run_owner),
) -> SandboxExecResponse:
    """
    Executes a shell command inside the persistent shell session for an authorized run.
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


# ──────────────────────────────────────────────────────────────────────────────
# Interactive PTY terminal
# ──────────────────────────────────────────────────────────────────────────────

class TerminalResetResponse(BaseModel):
    status: str
    run_id: str
    session_id: str
    cwd: str


@router.post("/{run_id}/terminal/reset", response_model=TerminalResetResponse)
async def reset_sandbox_terminal(
    run_id: str,
    auth_run: AgentRun = Depends(verify_sandbox_run_owner),
) -> TerminalResetResponse:
    """
    Terminates the run's interactive PTY shell and starts a fresh one for an authorized run.
    """
    try:
        session = await sandbox_manager.reset_pty_session(run_id)
        return TerminalResetResponse(
            status="RESET",
            run_id=run_id,
            session_id=session.session_id,
            cwd=str(session.worktree_path),
        )
    except InvalidRunError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PtyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error resetting terminal for run_id '{run_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reset terminal: {str(e)}")


@router.websocket("/{run_id}/terminal")
async def sandbox_terminal_ws(websocket: WebSocket, run_id: str) -> None:
    """
    Bidirectional terminal stream authenticated via access_token cookie prior to accept.
    """
    try:
        _authenticate_ws_run(websocket, run_id)
    except HTTPException as e:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=e.detail)
        return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    await websocket.accept()

    try:
        session = await sandbox_manager.get_or_create_pty_session(run_id)
    except InvalidRunError as e:
        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        await websocket.close(code=4400)
        return
    except PtyUnavailableError as e:
        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        await websocket.close(code=4500)
        return
    except Exception as e:
        logger.error(f"Error starting pty session for run_id '{run_id}': {e}", exc_info=True)
        await websocket.send_text(json.dumps({"type": "error", "message": "Failed to start terminal session"}))
        await websocket.close(code=1011)
        return

    output_queue = session.subscribe()

    scrollback = session.get_scrollback()
    if scrollback:
        await websocket.send_bytes(scrollback)

    async def pump_output() -> None:
        try:
            while True:
                chunk = await output_queue.get()
                if chunk is None:
                    await websocket.send_text(json.dumps({"type": "exit"}))
                    return
                await websocket.send_bytes(chunk)
        except (WebSocketDisconnect, RuntimeError):
            pass

    reader_task = asyncio.create_task(pump_output())

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            raw_bytes = message.get("bytes")
            if raw_bytes is not None:
                session.write(raw_bytes)
                continue

            raw_text = message.get("text")
            if raw_text is not None:
                if raw_text.strip().startswith("{"):
                    try:
                        control = json.loads(raw_text)
                        if isinstance(control, dict) and control.get("type") == "resize":
                            try:
                                session.resize(int(control.get("rows", 24)), int(control.get("cols", 80)))
                            except (TypeError, ValueError):
                                pass
                            continue
                    except (ValueError, TypeError):
                        pass

                session.write(raw_text.encode("utf-8"))
    except WebSocketDisconnect:
        pass
    finally:
        session.unsubscribe(output_queue)
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, Exception):
            pass


