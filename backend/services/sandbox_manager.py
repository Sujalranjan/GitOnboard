"""
SandboxManager: Controlled Host Subprocess Execution for Worktree Sandboxes.

Security Boundary Specification:
- Phase 2 provides controlled host subprocess execution with the run's worktree as `cwd`.
- Path validation verifies that the execution root resides within the server-side worktree storage directory.
- Sensitive environment variables (JWT secrets, GitHub OAuth secrets, Azure storage keys) are stripped.
- Real-time chunked streaming enforces an independent 1MB output limit on stdout and stderr, terminating the process group immediately if exceeded.
- Process group management ensures runaway child/grandchild processes are killed on timeout or stream limit.
- NOTE: This is NOT a full hypervisor or container/namespace VM; shell commands still run on the host OS under server permissions.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from backend.config import settings
from backend.logger import emit_execution_log, sanitize_log_data

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 1024 * 1024  # 1 MB stream limit per stream
DEFAULT_TIMEOUT_SEC = 30
MIN_TIMEOUT_SEC = 1
MAX_TIMEOUT_SEC = 120

# Environment variable keys that must be stripped before spawning subprocesses
SENSITIVE_ENV_KEYS = {
    "JWT_SECRET",
    "GITHUB_CLIENT_SECRET",
    "AZURE_STORAGE_ACCOUNT_KEY",
    "AZURE_STORAGE_CONNECTION_STRING",
    "LOCAL_DATABASE_URL",
    "PROD_DATABASE_URL",
    "DATABASE_URL",
    "GITHUB_ACCESS_TOKEN",
}


class SandboxError(Exception):
    """Base exception for sandbox execution errors."""
    pass


class WorktreeNotFoundError(SandboxError):
    """Raised when the requested run worktree does not exist on disk."""
    pass


class InvalidRunError(SandboxError):
    """Raised when the run_id is invalid or path traversal is detected."""
    pass


@dataclass
class SandboxExecResult:
    run_id: str
    command: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    output_truncated: bool
    duration_ms: float


class SandboxManager:
    """
    Manages controlled subprocess execution inside run worktree sandboxes.
    """

    def __init__(self, base_worktree_dir: Optional[Path] = None):
        self.base_dir = (base_worktree_dir or Path(settings.worktrees_dir)).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def resolve_worktree(self, run_id: str) -> Path:
        """
        Resolves and validates the worktree directory for a run_id server-side.
        Prevents path traversal and verifies the canonical path is within base_dir.
        """
        if not run_id or not run_id.strip() or ".." in run_id or "/" in run_id or "\\" in run_id:
            raise InvalidRunError(f"Invalid run identifier: '{run_id}'")

        # Search for matching directory in worktrees root
        clean_run_id = run_id.strip()
        candidates = []

        # 1. Exact match or repo_runid match
        for item in self.base_dir.iterdir():
            if item.is_dir():
                if item.name == clean_run_id or item.name.endswith(f"_{clean_run_id}"):
                    candidates.append(item)

        if candidates:
            target = candidates[0].resolve()
        else:
            # Fallback to default worktree path if created for run
            target = (self.base_dir / clean_run_id).resolve()

        # Path validation: Must reside within base_dir
        try:
            target.relative_to(self.base_dir)
        except ValueError:
            raise InvalidRunError(f"Path traversal detected for run '{run_id}'")

        if not target.exists() or not target.is_dir():
            # If not yet created on disk, initialize run worktree directory
            target.mkdir(parents=True, exist_ok=True)

        return target

    def _get_sanitized_env(self) -> Dict[str, str]:
        """Returns a copy of os.environ with sensitive secrets stripped."""
        clean_env = {}
        for k, v in os.environ.items():
            if k.upper() not in SENSITIVE_ENV_KEYS:
                clean_env[k] = v
        clean_env["GITONBOARD_SANDBOX"] = "1"
        return clean_env

    def _kill_process_group(self, proc: asyncio.subprocess.Process) -> None:
        """Terminates the process and its entire child process group."""
        pid = proc.pid
        if not pid:
            return

        if sys.platform == "win32":
            try:
                import subprocess
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=5,
                )
            except Exception as e:
                logger.debug(f"Windows taskkill error: {e}")
                try:
                    proc.kill()
                except Exception:
                    pass
        else:
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.debug(f"POSIX killpg error: {e}")
                try:
                    proc.kill()
                except Exception:
                    pass

    async def execute_command(
        self,
        run_id: str,
        command: str,
        timeout_sec: Optional[int] = DEFAULT_TIMEOUT_SEC,
    ) -> SandboxExecResult:
        """
        Executes a shell command inside the validated run worktree sandbox.
        Enforces streaming output limits, timeout enforcement, process group cleanup,
        and structured execution logging.
        """
        if not command or not command.strip():
            raise SandboxError("Command cannot be empty")

        worktree_path = self.resolve_worktree(run_id)
        timeout = max(MIN_TIMEOUT_SEC, min(MAX_TIMEOUT_SEC, timeout_sec or DEFAULT_TIMEOUT_SEC))

        env = self._get_sanitized_env()
        start_time = time.time()

        # Platform-specific process group creation
        kwargs = {
            "cwd": str(worktree_path),
            "env": env,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }

        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid
        else:
            import subprocess
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = await asyncio.create_subprocess_shell(command, **kwargs)

        stdout_chunks = []
        stderr_chunks = []
        stdout_bytes_read = 0
        stderr_bytes_read = 0
        output_truncated = False
        timed_out = False

        async def read_stream(stream, is_stdout: bool):
            nonlocal stdout_bytes_read, stderr_bytes_read, output_truncated
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                if is_stdout:
                    if stdout_bytes_read + len(chunk) <= MAX_OUTPUT_BYTES:
                        stdout_chunks.append(chunk)
                        stdout_bytes_read += len(chunk)
                    else:
                        remaining = MAX_OUTPUT_BYTES - stdout_bytes_read
                        if remaining > 0:
                            stdout_chunks.append(chunk[:remaining])
                            stdout_bytes_read += remaining
                        output_truncated = True
                        self._kill_process_group(proc)
                        break
                else:
                    if stderr_bytes_read + len(chunk) <= MAX_OUTPUT_BYTES:
                        stderr_chunks.append(chunk)
                        stderr_bytes_read += len(chunk)
                    else:
                        remaining = MAX_OUTPUT_BYTES - stderr_bytes_read
                        if remaining > 0:
                            stderr_chunks.append(chunk[:remaining])
                            stderr_bytes_read += remaining
                        output_truncated = True
                        self._kill_process_group(proc)
                        break

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(proc.stdout, is_stdout=True),
                    read_stream(proc.stderr, is_stdout=False),
                    proc.wait(),
                ),
                timeout=timeout,
            )
            exit_code = proc.returncode if proc.returncode is not None else 0
        except asyncio.TimeoutError:
            timed_out = True
            self._kill_process_group(proc)
            exit_code = -1
            stderr_chunks.append(f"\n[Command timed out after {timeout} seconds]".encode("utf-8"))

        duration_ms = (time.time() - start_time) * 1000

        stdout_str = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        stderr_str = b"".join(stderr_chunks).decode("utf-8", errors="replace")

        # Emit structured execution log
        emit_execution_log(
            event_type="sandbox_command_exec",
            status="SUCCESS" if exit_code == 0 else "FAIL",
            task_id=run_id,
            worktree_id=str(worktree_path),
            details={
                "command": command,
                "exit_code": exit_code,
                "duration_ms": round(duration_ms, 2),
                "timed_out": timed_out,
                "output_truncated": output_truncated,
                "stdout_length": len(stdout_str),
                "stderr_length": len(stderr_str),
            },
        )

        return SandboxExecResult(
            run_id=run_id,
            command=command,
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=exit_code,
            timed_out=timed_out,
            output_truncated=output_truncated,
            duration_ms=round(duration_ms, 2),
        )
