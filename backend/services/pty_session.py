"""
PtySession: Real pseudo-terminal-backed interactive shell session.

Unlike PersistentShellSession (sandbox_manager.py), which pipes commands into a
script-mode (`bash -s`) shell and waits for a completion token, PtySession attaches
an actual pseudo-terminal to an *interactive* shell (`bash -i` / Git Bash under
ConPTY on Windows). The shell owns line editing, job control, readline history,
ANSI/color output, and signal delivery (Ctrl+C, Ctrl+D, Ctrl+Z) exactly as a real
terminal would — none of that is reimplemented here.

Platform backends:
- POSIX (Linux/macOS, including the Docker backend container): `os.openpty()` +
  `subprocess.Popen` with the slave fd as stdin/stdout/stderr, non-blocking reads
  wired into the asyncio event loop via `add_reader`.
- Windows (native host dev): `pywinpty`, which wraps ConPTY. Its read/write API is
  blocking, so it is driven from a background thread via `run_in_executor`.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

if not IS_WINDOWS:
    import fcntl
    import pty
    import signal
    import struct
    import termios
else:
    try:
        import winpty
    except ImportError:  # pragma: no cover - exercised only when pywinpty is missing
        winpty = None

DEFAULT_ROWS = 24
DEFAULT_COLS = 80
SCROLLBACK_CAP_BYTES = 64 * 1024
READ_CHUNK_SIZE = 65536


class PtyUnavailableError(Exception):
    """Raised when no PTY-capable interactive shell backend is available on this host."""


def find_interactive_shell_argv() -> List[str]:
    """
    Resolves the interactive shell argv for a PTY session. Reuses the same shell
    discovery as the REST /exec session (Git Bash on Windows, bash/sh on POSIX) but
    swaps the "-s" (read commands from stdin) flag for "-i" (force interactive) —
    a PTY session needs readline/job-control/prompt behavior, which "-s" mode never
    provides regardless of tty attachment.
    """
    from backend.services.sandbox_manager import find_shell_command, ShellKind

    argv, kind = find_shell_command()
    if kind is not ShellKind.POSIX:
        raise PtyUnavailableError(
            "No POSIX-capable shell (bash/sh) was found on this host. The interactive "
            "sandbox terminal requires Git Bash (Windows) or bash/sh (Linux/macOS). "
            "Install Git for Windows — see DEVELOPMENT.md."
        )
    return [argv[0], "-i"]


class PtySession:
    """
    A single real pseudo-terminal-backed interactive shell, scoped to one run's
    worktree. One PtySession is kept alive per run_id across browser reconnects —
    disconnecting the websocket does not kill the shell.
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
        self.worktree_path = worktree_path
        self.env = env
        self.created_at = time.time()
        self.last_active_at = time.time()
        self.is_closed = False

        self._rows = DEFAULT_ROWS
        self._cols = DEFAULT_COLS
        self._subscribers: set[asyncio.Queue[Optional[bytes]]] = set()
        self._scrollback: Deque[bytes] = collections.deque()
        self._scrollback_bytes = 0

        # POSIX backend state
        self._master_fd: Optional[int] = None
        self._proc: Optional[subprocess.Popen] = None
        # Windows backend state
        self._winpty_proc = None
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        shell_argv = find_interactive_shell_argv()
        term_env = dict(self.env)
        term_env["TERM"] = "xterm-256color"
        term_env["COLORTERM"] = "truecolor"
        term_env["COLUMNS"] = str(self._cols)
        term_env["LINES"] = str(self._rows)
        if "PS1" not in term_env:
            term_env["PS1"] = r"\u@gitonboard:\w\$ "

        if IS_WINDOWS:
            await self._start_windows(shell_argv, term_env)
        else:
            await self._start_posix(shell_argv, term_env)

    # ------------------------------------------------------------------
    # POSIX backend
    # ------------------------------------------------------------------

    async def _start_posix(self, shell_argv: List[str], term_env: Dict[str, str]) -> None:
        master_fd, slave_fd = pty.openpty()
        self._set_winsize_posix(master_fd, self._rows, self._cols)

        def _preexec() -> None:
            os.setsid()
            try:
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            except OSError:
                pass

        try:
            self._proc = subprocess.Popen(
                shell_argv,
                cwd=str(self.worktree_path),
                env=term_env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=_preexec,
                close_fds=True,
            )
        finally:
            os.close(slave_fd)

        os.set_blocking(master_fd, False)
        self._master_fd = master_fd

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        loop.add_reader(master_fd, self._on_posix_readable)

    def _on_posix_readable(self) -> None:
        assert self._master_fd is not None
        try:
            data = os.read(self._master_fd, READ_CHUNK_SIZE)
        except BlockingIOError:
            return
        except OSError:
            data = b""

        if not data:
            self._detach_posix_reader()
            self._broadcast(None)
            return

        self._broadcast(data)

    def _detach_posix_reader(self) -> None:
        if self._master_fd is None:
            return
        loop = asyncio.get_event_loop()
        try:
            loop.remove_reader(self._master_fd)
        except Exception:
            pass

    @staticmethod
    def _set_winsize_posix(fd: int, rows: int, cols: int) -> None:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    # ------------------------------------------------------------------
    # Windows backend (pywinpty / ConPTY)
    # ------------------------------------------------------------------

    async def _start_windows(self, shell_argv: List[str], term_env: Dict[str, str]) -> None:
        if winpty is None:
            raise PtyUnavailableError(
                "pywinpty is not installed. The interactive sandbox terminal on native "
                "Windows requires it for real ConPTY-backed terminal sessions."
            )
        loop = asyncio.get_event_loop()

        def _spawn():
            return winpty.PtyProcess.spawn(
                shell_argv,
                cwd=str(self.worktree_path),
                env=term_env,
                dimensions=(self._rows, self._cols),
            )

        self._winpty_proc = await loop.run_in_executor(None, _spawn)
        self._reader_task = loop.create_task(self._windows_reader_loop())

    async def _windows_reader_loop(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            try:
                text = await loop.run_in_executor(None, self._winpty_proc.read, READ_CHUNK_SIZE)
            except EOFError:
                self._broadcast(None)
                return
            except Exception as e:
                logger.debug(f"winpty read error for session {self.session_id}: {e}")
                self._broadcast(None)
                return

            if text:
                data = text.encode("utf-8", errors="replace")
                self._broadcast(data)

    # ------------------------------------------------------------------
    # Shared interface
    # ------------------------------------------------------------------

    def _record_scrollback(self, data: bytes) -> None:
        self._scrollback.append(data)
        self._scrollback_bytes += len(data)
        while self._scrollback_bytes > SCROLLBACK_CAP_BYTES and self._scrollback:
            popped = self._scrollback.popleft()
            self._scrollback_bytes -= len(popped)

    def _broadcast(self, data: Optional[bytes]) -> None:
        if data is not None:
            self._record_scrollback(data)
        for q in list(self._subscribers):
            try:
                q.put_nowait(data)
            except Exception:
                pass

    def subscribe(self) -> asyncio.Queue[Optional[bytes]]:
        """Subscribes to live output chunks."""
        q: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Optional[bytes]]) -> None:
        """Removes an active output subscription."""
        self._subscribers.discard(q)

    def get_scrollback(self) -> bytes:
        """Recent output, replayed to a newly (re)connecting client so a reconnect
        doesn't drop straight into a blank screen."""
        return b"".join(self._scrollback)

    def write(self, data: bytes) -> None:
        """Writes raw keystroke/control bytes to the pty exactly as a real terminal
        would — Ctrl+C (0x03), Ctrl+D (0x04), arrow keys, etc. are not special-cased
        here; the shell's own tty line discipline (POSIX) or ConPTY (Windows)
        interprets them."""
        if self.is_closed:
            return
        self.last_active_at = time.time()
        if IS_WINDOWS:
            if self._winpty_proc is None:
                return
            try:
                self._winpty_proc.write(data.decode("utf-8", errors="replace"))
            except EOFError:
                pass
        else:
            if self._master_fd is None:
                return
            try:
                os.write(self._master_fd, data)
            except OSError:
                pass

    def resize(self, rows: int, cols: int) -> None:
        rows = max(1, min(500, int(rows)))
        cols = max(1, min(500, int(cols)))
        self._rows, self._cols = rows, cols
        if IS_WINDOWS:
            if self._winpty_proc is not None:
                try:
                    self._winpty_proc.setwinsize(rows, cols)
                except Exception:
                    pass
        else:
            if self._master_fd is not None:
                try:
                    self._set_winsize_posix(self._master_fd, rows, cols)
                    if self._proc is not None:
                        try:
                            pgid = os.getpgid(self._proc.pid)
                            os.killpg(pgid, signal.SIGWINCH)
                        except (ProcessLookupError, PermissionError, OSError):
                            pass
                except Exception:
                    pass

    def is_alive(self) -> bool:
        if self.is_closed:
            return False
        if IS_WINDOWS:
            try:
                return bool(self._winpty_proc and self._winpty_proc.isalive())
            except Exception:
                return False
        return bool(self._proc and self._proc.poll() is None)

    async def close(self) -> None:
        if self.is_closed:
            return
        self.is_closed = True

        if IS_WINDOWS:
            if self._reader_task is not None:
                self._reader_task.cancel()
            if self._winpty_proc is not None:
                try:
                    self._winpty_proc.terminate(force=True)
                except Exception as e:
                    logger.debug(f"Error terminating winpty session {self.session_id}: {e}")
        else:
            self._detach_posix_reader()
            if self._proc is not None:
                try:
                    pgid = os.getpgid(self._proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except Exception as e:
                    logger.debug(f"Error killing pty process group for session {self.session_id}: {e}")
                try:
                    self._proc.wait(timeout=3)
                except Exception:
                    pass
            if self._master_fd is not None:
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass
                self._master_fd = None

        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
