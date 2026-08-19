"""
Interactive PTY Terminal Test Suite.

Verifies backend/services/pty_session.py + the `/api/v1/sandbox/{run_id}/terminal`
websocket, distinct from the REST /exec "command-execution" model covered by
tests/test_phase2_sandbox_terminal.py:

1. A real interactive shell starts and streams its prompt unprompted.
2. cd / export persist within the pty session, the same as a real terminal.
3. Terminal resize (`COLUMNS`) takes effect.
4. Ctrl+C delivers a real SIGINT to the foreground process (not the shell) and
   the shell survives it.
5. Reconnecting to the same run_id reattaches to the same still-running shell
   (real session persistence across websocket disconnects) and replays recent
   scrollback.
6. The REST /terminal/reset endpoint tears down and restarts the shell.

POSIX-only: PtySession's Windows backend (pywinpty/ConPTY) has a materially
different, thread-driven implementation validated separately by hand (see the
PR description) — these tests target the `os.openpty()` backend that runs in
this project's actual deployment target (the Linux backend container).
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Exercises the POSIX os.openpty() backend used in the real (Linux) deployment target.",
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def seeded_run_id():
    """Pre-seeds a populated worktree directly, mirroring sandbox_run_fixture in
    test_phase2_sandbox_terminal.py, so tests don't pay for full-repo auto-provisioning."""
    run_id = f"pty-test-{uuid.uuid4().hex[:8]}"
    wt_dir = Path(settings.worktrees_dir).resolve() / run_id
    wt_dir.mkdir(parents=True, exist_ok=True)
    (wt_dir / "sample.txt").write_text("hello\n", encoding="utf-8")
    yield run_id


class _Drainer:
    """Reads websocket frames with a bounded per-call timeout.

    WebSocketTestSession.receive() has no native timeout, so a single
    dedicated background thread continuously pumps it into a FIFO queue;
    drain() only ever reads from that queue with a timeout. This is
    deliberately NOT "submit a receive() to a pool and abandon it on
    timeout" — with a synchronous, single-consumer channel like this one,
    multiple independent threads each calling receive() race each other for
    whichever message arrives next, so an abandoned call from a previous
    drain() can silently steal the message a later drain() call was waiting
    for. One pump thread per connection avoids that race entirely.
    """

    def __init__(self, ws):
        self.ws = ws
        self._q: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        while True:
            try:
                message = self.ws.receive()
            except Exception:
                self._q.put(None)
                return
            self._q.put(message)
            if message is None or message.get("type") == "websocket.disconnect":
                return

    def drain(self, gap: float = 1.0, hard_cap: float = 8.0) -> bytes:
        out = b""
        start = time.monotonic()
        while True:
            remaining = hard_cap - (time.monotonic() - start)
            if remaining <= 0:
                break
            try:
                message = self._q.get(timeout=min(gap, remaining))
            except queue.Empty:
                break
            if message is None or message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                out += message["bytes"]
            elif message.get("text") is not None:
                pass  # control frames (exit/error) aren't asserted on here
        return out


def test_pty_terminal_real_shell_and_cwd(client: TestClient, seeded_run_id: str):
    """A fresh connection gets a real shell prompt, and cd/pwd/export/echo behave
    exactly like an interactive terminal (state owned by the shell, not the API)."""
    with client.websocket_connect(f"/api/v1/sandbox/{seeded_run_id}/terminal") as ws:
        drainer = _Drainer(ws)
        initial = drainer.drain(gap=1.0, hard_cap=8.0)
        assert initial, "expected the shell to greet with a prompt on connect"

        ws.send_bytes(b"mkdir -p sub_pty && cd sub_pty && pwd\n")
        out = drainer.drain().decode(errors="replace")
        assert "sub_pty" in out

        ws.send_bytes(b"export PTY_TEST_VAR=hello_pty_123 && echo $PTY_TEST_VAR\n")
        out = drainer.drain().decode(errors="replace")
        assert "hello_pty_123" in out


def test_pty_terminal_resize(client: TestClient, seeded_run_id: str):
    with client.websocket_connect(f"/api/v1/sandbox/{seeded_run_id}/terminal") as ws:
        drainer = _Drainer(ws)
        drainer.drain(gap=1.0, hard_cap=8.0)

        ws.send_text(json.dumps({"type": "resize", "rows": 40, "cols": 111}))
        ws.send_bytes(b"echo cols=$COLUMNS\n")
        out = drainer.drain().decode(errors="replace")
        assert "cols=111" in out


def test_pty_terminal_ctrl_c_interrupts_foreground_process_not_shell(
    client: TestClient, seeded_run_id: str
):
    """Ctrl+C (0x03) must interrupt the running foreground process (real SIGINT
    via the tty's job control), while the shell itself survives to run the next
    command — it must NOT kill the whole session."""
    with client.websocket_connect(f"/api/v1/sandbox/{seeded_run_id}/terminal") as ws:
        drainer = _Drainer(ws)
        drainer.drain(gap=1.0, hard_cap=8.0)

        ws.send_bytes(
            b"python3 -u -c 'import time\nwhile True:\n print(\"tick\")\n time.sleep(0.2)'\n"
        )
        # Let a few ticks land before interrupting, proving it was really running.
        loop_output = drainer.drain(gap=0.6, hard_cap=3.0).decode(errors="replace")
        assert "tick" in loop_output

        ws.send_bytes(b"\x03")
        after_ctrlc = drainer.drain(gap=1.0, hard_cap=5.0).decode(errors="replace")
        assert "KeyboardInterrupt" in after_ctrlc

        ws.send_bytes(b"echo SHELL_SURVIVED_CTRLC\n")
        survival = drainer.drain().decode(errors="replace")
        assert "SHELL_SURVIVED_CTRLC" in survival


def test_pty_terminal_reconnect_reattaches_and_replays_scrollback(
    client: TestClient, seeded_run_id: str
):
    """A second connection to the same run_id must reattach to the SAME still-running
    shell (cwd from the first connection persists) rather than starting a new one,
    and should replay recent scrollback instead of dropping into a blank screen."""
    with client.websocket_connect(f"/api/v1/sandbox/{seeded_run_id}/terminal") as ws:
        drainer = _Drainer(ws)
        drainer.drain(gap=1.0, hard_cap=8.0)
        ws.send_bytes(b"mkdir -p reconnect_dir && cd reconnect_dir\n")
        drainer.drain()

    with client.websocket_connect(f"/api/v1/sandbox/{seeded_run_id}/terminal") as ws2:
        drainer2 = _Drainer(ws2)
        replay = drainer2.drain(gap=1.0, hard_cap=5.0).decode(errors="replace")
        assert "reconnect_dir" in replay  # scrollback from the first connection

        ws2.send_bytes(b"pwd\n")
        out = drainer2.drain().decode(errors="replace")
        assert "reconnect_dir" in out  # same shell, same cwd — not a fresh session


def test_sandbox_terminal_reset_restarts_shell(client: TestClient, seeded_run_id: str):
    """POST /terminal/reset must kill the old shell and its children (no orphans)
    and start a fresh one back at the worktree root."""
    with client.websocket_connect(f"/api/v1/sandbox/{seeded_run_id}/terminal") as ws:
        drainer = _Drainer(ws)
        drainer.drain(gap=1.0, hard_cap=8.0)
        ws.send_bytes(b"cd sub_pty 2>/dev/null || mkdir -p sub_pty && cd sub_pty\n")
        drainer.drain()

    res = client.post(f"/api/v1/sandbox/{seeded_run_id}/terminal/reset")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "RESET"
    assert data["cwd"].rstrip("/").endswith(seeded_run_id)

    with client.websocket_connect(f"/api/v1/sandbox/{seeded_run_id}/terminal") as ws3:
        drainer3 = _Drainer(ws3)
        drainer3.drain(gap=1.0, hard_cap=8.0)
        ws3.send_bytes(b"pwd\n")
        out = drainer3.drain().decode(errors="replace")
        assert "sub_pty" not in out  # back at the worktree root, not the old cwd
