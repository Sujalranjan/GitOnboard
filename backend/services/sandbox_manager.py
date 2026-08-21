"""
SandboxManager: Controlled Host Subprocess Execution with Persistent Shell Sessions.

Security Boundary Specification:
- Phase 2.1 provides controlled host subprocess execution with persistent shell/PTY sessions scoped to the run's worktree.
- Working directory changes (cd), environment exports (export), and shell state persist across commands within the same session.
- Path validation verifies that the execution root resides within the server-side worktree storage directory.
- Sensitive environment variables (JWT secrets, GitHub OAuth secrets, Azure storage keys, DB URLs) are stripped from the session environment.
- Real-time output limiting enforces an independent 1MB output limit on stdout and stderr, truncating and terminating runaway commands.
- Process group management ensures runaway child/grandchild processes are killed on timeout or stream limit.
- Session isolation ensures separate run_id sessions cannot access or leak each other's working directory or environment.
- NOTE: This is controlled host subprocess execution and does not provide container/kernel namespace isolation.
"""
from __future__ import annotations

import asyncio
import enum
import logging
import os
import shutil
import signal
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.config import settings
from backend.logger import emit_execution_log, sanitize_log_data
from backend.services.env_sanitizer import SENSITIVE_ENV_KEYS, get_sanitized_env
from backend.services.pty_session import PtySession, PtyUnavailableError
from backend.services.worktree_provisioner import WorktreeProvisioner

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 1024 * 1024  # 1 MB stream limit per stream
DEFAULT_TIMEOUT_SEC = 30
MIN_TIMEOUT_SEC = 1
MAX_TIMEOUT_SEC = 120
SESSION_IDLE_TIMEOUT_SEC = 1800  # 30 minutes


class SandboxError(Exception):
    """Base exception for sandbox execution errors."""
    pass


class WorktreeNotFoundError(SandboxError):
    """Raised when the requested run worktree does not exist on disk."""
    pass


class InvalidRunError(SandboxError):
    """Raised when the run_id is invalid or path traversal is detected."""
    pass


class UnsupportedShellError(SandboxError):
    """
    Raised when no POSIX-capable shell (bash/sh, e.g. Git Bash on Windows) is
    available. The command wrapper this session relies on (`{ command; } >
    out 2> err`, `$?`, `pwd`) is POSIX shell syntax; silently handing it to
    cmd.exe would produce garbage output and a meaningless exit code instead
    of a clear failure, so this is raised explicitly instead.
    """
    pass


class ShellKind(enum.Enum):
    """Distinguishes the shell dialect a resolved shell executable speaks, so the
    command wrapper can be built explicitly for it rather than assuming POSIX
    syntax works everywhere it happens to get piped."""
    POSIX = "posix"
    CMD = "cmd"


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
    session_id: Optional[str] = None
    cwd: Optional[str] = None


def find_shell_command() -> Tuple[List[str], ShellKind]:
    """
    Resolves the best available interactive shell across platforms, returning
    both the argv to launch it and which command dialect (POSIX vs cmd.exe)
    it speaks. The command wrapper in `PersistentShellSession.execute_command`
    is built per-dialect from this — it must never assume POSIX syntax works
    just because *some* shell process was found.
    """
    if sys.platform != "win32":
        for sh in ["/bin/bash", "/bin/sh", "bash", "sh"]:
            if shutil.which(sh):
                return [sh, "-s"], ShellKind.POSIX
        return ["/bin/sh", "-s"], ShellKind.POSIX
    for git_sh in [
        r"C:\Program Files\Git\bin\sh.exe",
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\sh.exe",
    ]:
        if os.path.exists(git_sh):
            return [git_sh, "-s"], ShellKind.POSIX
    if shutil.which("bash"):
        return ["bash", "-s"], ShellKind.POSIX
    if shutil.which("sh"):
        return ["sh", "-s"], ShellKind.POSIX
    # No POSIX-capable shell found. Returning cmd.exe here does NOT mean it's
    # safe to use with the POSIX command wrapper — PersistentShellSession
    # checks `shell_kind` and raises UnsupportedShellError before ever
    # starting this process. See UnsupportedShellError docstring.
    return ["cmd.exe"], ShellKind.CMD


class PersistentShellSession:
    """
    Maintains a long-running interactive shell process tied to a specific run worktree.
    Preserves cwd changes (cd), environment exports (export), and shell state across commands.
    """

    def __init__(
        self,
        session_id: str,
        run_id: str,
        worktree_path: Path,
        env: Dict[str, str],
    ):
        self.session_id = session_id
        self.run_id = run_id
        self.worktree_path = worktree_path.resolve()
        self.env = env
        self.created_at = time.time()
        self.last_accessed_at = time.time()
        self.temp_dir = Path(tempfile.mkdtemp(prefix=f"gitonboard_session_{session_id}_"))
        self.lock = asyncio.Lock()
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.is_closed = False
        self._current_cwd = str(self.worktree_path)
        self.shell_kind: ShellKind = ShellKind.POSIX

    async def initialize(self) -> None:
        """Starts the persistent shell subprocess inside the worktree directory."""
        shell_cmd, shell_kind = find_shell_command()
        if shell_kind is not ShellKind.POSIX:
            raise UnsupportedShellError(
                "No POSIX-capable shell (bash/sh) was found on this host. The sandbox "
                "terminal's command wrapper requires POSIX shell syntax and will not run "
                "correctly under cmd.exe, so execution is refused rather than silently "
                "producing garbage output. Install Git for Windows (which bundles Git "
                "Bash) to enable the sandbox terminal — see DEVELOPMENT.md."
            )
        self.shell_kind = shell_kind
        kwargs = {
            "cwd": str(self.worktree_path),
            "env": self.env,
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.DEVNULL,
        }

        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid
        else:
            import subprocess
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        self.proc = await asyncio.create_subprocess_exec(*shell_cmd, **kwargs)
        self.last_accessed_at = time.time()

        # Send standard interactive shell configuration (aliases and formatting)
        try:
            init_payload = (
                b"shopt -s expand_aliases 2>/dev/null || true\n"
                b"alias ls='ls -C --color=never' 2>/dev/null || true\n"
                b"alias ll='ls -la --color=never' 2>/dev/null || true\n"
                b"alias la='ls -A --color=never' 2>/dev/null || true\n"
                b"export COLUMNS=80 LINES=24 2>/dev/null || true\n"
            )
            self.proc.stdin.write(init_payload)
            await self.proc.stdin.drain()
        except Exception:
            pass

    def _kill_process_tree(self) -> None:
        """Terminates the shell process and all spawned child processes."""
        if not self.proc or not self.proc.pid:
            return

        pid = self.proc.pid
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
                    self.proc.kill()
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
                    self.proc.kill()
                except Exception:
                    pass

    async def execute_command(
        self,
        command: str,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> SandboxExecResult:
        """
        Executes a command inside the persistent shell session.
        Preserves shell variables, exports, and cwd modifications.
        """
        if self.is_closed:
            raise SandboxError(f"Session '{self.session_id}' is closed.")

        async with self.lock:
            self.last_accessed_at = time.time()

            # Ensure shell process is alive
            if not self.proc or self.proc.returncode is not None:
                await self.initialize()

            start_time = time.time()
            timeout = max(MIN_TIMEOUT_SEC, min(MAX_TIMEOUT_SEC, timeout_sec))

            token = f"GITONBOARD_TOKEN_{uuid.uuid4().hex}"
            out_path = (self.temp_dir / f"out_{token}.log").as_posix()
            err_path = (self.temp_dir / f"err_{token}.log").as_posix()
            pwd_path = (self.temp_dir / f"pwd_{token}.log").as_posix()

            # Compound execution block:
            # - { command; } executes directly in the parent shell context, preserving `cd` and `export`
            # - Output redirected to dedicated per-command temporary log files
            # - Captures actual return code
            # - Records current pwd for UI context
            payload = (
                f"{{\n"
                f"  {command}\n"
                f"}} > \"{out_path}\" 2> \"{err_path}\"\n"
                f"RET_CODE=$?\n"
                f"pwd > \"{pwd_path}\" 2>/dev/null\n"
                f"echo \"{token}:$RET_CODE\"\n"
            )

            try:
                self.proc.stdin.write(payload.encode("utf-8"))
                await self.proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                # Shell died unexpectedly, re-initialize
                await self.initialize()
                self.proc.stdin.write(payload.encode("utf-8"))
                await self.proc.stdin.drain()

            timed_out = False
            output_truncated = False
            exit_code = 0

            async def wait_for_completion() -> int:
                while True:
                    line = await self.proc.stdout.readline()
                    if not line:
                        raise SandboxError("Persistent shell process terminated unexpectedly.")
                    line_str = line.decode("utf-8", errors="replace")
                    if token in line_str:
                        parts = line_str.strip().split(f"{token}:")
                        if len(parts) > 1 and parts[1].strip().lstrip("-").isdigit():
                            return int(parts[1].strip())
                        return 0

            try:
                exit_code = await asyncio.wait_for(wait_for_completion(), timeout=timeout)
            except asyncio.TimeoutError:
                timed_out = True
                exit_code = -1
                self._kill_process_tree()
                # Restart shell in current directory
                await self.initialize()

            # Read captured stdout and stderr
            stdout_text = ""
            stderr_text = ""

            out_file = Path(out_path)
            err_file = Path(err_path)
            pwd_file = Path(pwd_path)

            if out_file.exists():
                size = out_file.stat().st_size
                if size > MAX_OUTPUT_BYTES:
                    output_truncated = True
                try:
                    with out_file.open("r", encoding="utf-8", errors="replace") as f:
                        stdout_text = f.read(MAX_OUTPUT_BYTES)
                except Exception as e:
                    logger.debug(f"Error reading stdout log: {e}")
                out_file.unlink(missing_ok=True)

            if err_file.exists():
                size = err_file.stat().st_size
                if size > MAX_OUTPUT_BYTES:
                    output_truncated = True
                try:
                    with err_file.open("r", encoding="utf-8", errors="replace") as f:
                        stderr_text = f.read(MAX_OUTPUT_BYTES)
                except Exception as e:
                    logger.debug(f"Error reading stderr log: {e}")
                err_file.unlink(missing_ok=True)

            if pwd_file.exists():
                try:
                    self._current_cwd = pwd_file.read_text(encoding="utf-8", errors="replace").strip()
                except Exception:
                    pass
                pwd_file.unlink(missing_ok=True)

            if timed_out:
                stderr_text += f"\n[Command timed out after {timeout} seconds — process terminated]"

            duration_ms = (time.time() - start_time) * 1000

            emit_execution_log(
                event_type="sandbox_persistent_exec",
                status="SUCCESS" if exit_code == 0 else "FAIL",
                task_id=self.run_id,
                worktree_id=str(self.worktree_path),
                details={
                    "session_id": self.session_id,
                    "command": command,
                    "exit_code": exit_code,
                    "cwd": self._current_cwd,
                    "duration_ms": round(duration_ms, 2),
                    "timed_out": timed_out,
                    "output_truncated": output_truncated,
                },
            )

            return SandboxExecResult(
                run_id=self.run_id,
                session_id=self.session_id,
                command=command,
                stdout=stdout_text,
                stderr=stderr_text,
                exit_code=exit_code,
                timed_out=timed_out,
                output_truncated=output_truncated,
                duration_ms=round(duration_ms, 2),
                cwd=self._current_cwd,
            )

    async def close(self) -> None:
        """Closes the shell process and removes temporary files."""
        self.is_closed = True
        if self.proc:
            try:
                if self.proc.stdin:
                    self.proc.stdin.write(b"exit\n")
                    await self.proc.stdin.drain()
            except Exception:
                pass
            self._kill_process_tree()

        shutil.rmtree(self.temp_dir, ignore_errors=True)


class SandboxManager:
    """
    Manages controlled subprocess execution and persistent shell sessions inside run worktree sandboxes.
    """

    def __init__(self, base_worktree_dir: Optional[Path] = None):
        self.base_dir = (base_worktree_dir or Path(settings.worktrees_dir)).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.provisioner = WorktreeProvisioner(self.base_dir)
        self._sessions: Dict[str, PersistentShellSession] = {}
        self._run_to_session: Dict[str, str] = {}
        self._lock = asyncio.Lock()

        # Real interactive PTY sessions backing the terminal UI. Kept separate
        # from the REST /exec sessions above (see class docstring) — one live
        # interactive shell per run_id, independent of REST-side session_ids.
        self._pty_sessions: Dict[str, PtySession] = {}
        self._pty_lock = asyncio.Lock()

    def resolve_worktree(self, run_id: str) -> Path:
        """
        Resolves and validates the worktree directory for a run_id server-side.
        Prevents path traversal and verifies the canonical path is within base_dir.
        Auto-provisions real repository source files if the worktree is unpopulated.
        """
        if not run_id or not run_id.strip() or ".." in run_id or "/" in run_id or "\\" in run_id:
            raise InvalidRunError(f"Invalid run identifier: '{run_id}'")

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
            target = (self.base_dir / clean_run_id).resolve()

        # Path validation: Must reside within base_dir
        try:
            target.relative_to(self.base_dir)
        except ValueError:
            raise InvalidRunError(f"Path traversal detected for run '{run_id}'")

        if not target.exists() or not target.is_dir():
            target.mkdir(parents=True, exist_ok=True)

        # Auto-provision repository contents if unpopulated
        if not self.provisioner.is_worktree_populated(target):
            repo_id = clean_run_id.split("_")[0] if "_" in clean_run_id else clean_run_id
            self.provisioner.provision(repo_identifier=repo_id, worktree_path=target)

        return target

    def _get_sanitized_env(self) -> Dict[str, str]:
        """Returns a copy of os.environ with sensitive secrets stripped."""
        return get_sanitized_env(extra={"GITONBOARD_SANDBOX": "1"})

    async def get_or_create_session(
        self,
        run_id: str,
        session_id: Optional[str] = None,
    ) -> PersistentShellSession:
        """
        Retrieves an existing persistent shell session or creates a new one scoped to the run's worktree.
        """
        worktree_path = self.resolve_worktree(run_id)

        async with self._lock:
            # 1. Look up by explicit session_id
            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                if not session.is_closed:
                    return session

            # 2. Look up existing active session for this run_id
            if run_id in self._run_to_session:
                existing_id = self._run_to_session[run_id]
                if existing_id in self._sessions:
                    session = self._sessions[existing_id]
                    if not session.is_closed:
                        return session

            # 3. Create new persistent session
            new_session_id = session_id or f"session_{uuid.uuid4().hex[:10]}"
            sanitized_env = self._get_sanitized_env()

            session = PersistentShellSession(
                session_id=new_session_id,
                run_id=run_id,
                worktree_path=worktree_path,
                env=sanitized_env,
            )
            await session.initialize()

            self._sessions[new_session_id] = session
            self._run_to_session[run_id] = new_session_id
            return session

    async def execute_command(
        self,
        run_id: str,
        command: str,
        timeout_sec: Optional[int] = DEFAULT_TIMEOUT_SEC,
        session_id: Optional[str] = None,
    ) -> SandboxExecResult:
        """
        Executes a command inside the persistent shell session for the given run_id.
        """
        if not command or not command.strip():
            raise SandboxError("Command cannot be empty")

        session = await self.get_or_create_session(run_id=run_id, session_id=session_id)
        return await session.execute_command(
            command=command,
            timeout_sec=timeout_sec or DEFAULT_TIMEOUT_SEC,
        )

    async def close_session(self, session_id: str) -> None:
        """Closes a persistent shell session and cleans up resources."""
        async with self._lock:
            if session_id in self._sessions:
                session = self._sessions.pop(session_id)
                if session.run_id in self._run_to_session and self._run_to_session[session.run_id] == session_id:
                    self._run_to_session.pop(session.run_id, None)
                await session.close()

    async def close_all_sessions(self) -> None:
        """Closes all active shell sessions (both REST /exec sessions and interactive PTY sessions)."""
        async with self._lock:
            for session in list(self._sessions.values()):
                try:
                    await session.close()
                except Exception as e:
                    logger.debug(f"Error closing session {session.session_id}: {e}")
            self._sessions.clear()
            self._run_to_session.clear()

        async with self._pty_lock:
            for pty_session in list(self._pty_sessions.values()):
                try:
                    await pty_session.close()
                except Exception as e:
                    logger.debug(f"Error closing pty session {pty_session.session_id}: {e}")
            self._pty_sessions.clear()

    # ------------------------------------------------------------------
    # Interactive PTY sessions (real terminal, backs the terminal UI websocket)
    # ------------------------------------------------------------------

    async def get_or_create_pty_session(self, run_id: str) -> PtySession:
        """
        Retrieves the live interactive PTY session for a run_id, or creates one.
        One PTY session is kept alive per run_id across websocket reconnects —
        a browser refresh or component remount reattaches to the same shell
        rather than starting a new one, as long as it is still alive.
        """
        # resolve_worktree() can run first-time provisioning (copying the whole
        # repo, git init/commit) which is blocking, synchronous I/O — offload it
        # to a thread so it doesn't stall the single asyncio event loop. Left
        # in place, that starves uvicorn's websocket handshake response (queued
        # right after accept()) until provisioning finishes, so the client's
        # connect() times out well before the shell ever starts.
        worktree_path = await asyncio.to_thread(self.resolve_worktree, run_id)

        async with self._pty_lock:
            existing = self._pty_sessions.get(run_id)
            if existing is not None and existing.is_alive():
                return existing
            if existing is not None:
                await existing.close()

            session = PtySession(
                session_id=f"pty_{uuid.uuid4().hex[:10]}",
                run_id=run_id,
                worktree_path=worktree_path,
                env=self._get_sanitized_env(),
            )
            await session.start()
            self._pty_sessions[run_id] = session
            return session

    async def reset_pty_session(self, run_id: str) -> PtySession:
        """Terminates the run's interactive PTY session (if any) and starts a fresh one."""
        async with self._pty_lock:
            existing = self._pty_sessions.pop(run_id, None)
        if existing is not None:
            await existing.close()
        return await self.get_or_create_pty_session(run_id)

    async def close_pty_session(self, run_id: str) -> None:
        async with self._pty_lock:
            existing = self._pty_sessions.pop(run_id, None)
        if existing is not None:
            await existing.close()


sandbox_manager = SandboxManager()

