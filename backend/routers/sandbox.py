"""
Sandbox Router: Endpoints for executing commands and managing persistent shell sessions in worktree sandboxes.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

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


# ──────────────────────────────────────────────────────────────────────────────
# Interactive PTY terminal: a real bidirectional terminal session, distinct from
# the request/response /exec endpoint above. See PtySession for the platform
# backends (POSIX pty vs Windows ConPTY via pywinpty).
# ──────────────────────────────────────────────────────────────────────────────


class TerminalResetResponse(BaseModel):
    status: str
    run_id: str
    session_id: str
    cwd: str


@router.post("/{run_id}/terminal/reset", response_model=TerminalResetResponse)
async def reset_sandbox_terminal(run_id: str) -> TerminalResetResponse:
    """
    Terminates the run's interactive PTY shell (killing its process tree) and
    starts a fresh one in the same worktree. Any websocket still attached to the
    old session will see it exit; the frontend is expected to reconnect after
    calling this.
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
    Bidirectional terminal stream. Binary frames carry raw keystroke/output bytes
    in both directions (written straight through to the pty — Ctrl+C, Ctrl+D,
    arrow keys, etc. all pass through unmodified for the shell's tty layer to
    interpret). Text frames are JSON control messages; currently only
    `{"type": "resize", "rows": N, "cols": N}` from the client.

    The underlying PtySession is NOT closed when this socket disconnects — the
    shell keeps running so a reconnect (page refresh, panel close/reopen) can
    reattach to the same session. Recent output is replayed on (re)connect so a
    reattach doesn't drop straight into a blank screen.
    """
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
                # Check for JSON control message (e.g. resize)
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

                # If not a resize control, write text directly as UTF-8 input bytes
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

