"""
Phase 2 Integration & Security Test Suite: Sandbox Terminal Real Execution.

Verifies:
1. Real subprocess command execution (no simulation)
2. `pwd` returns the exact canonical run worktree directory
3. `echo` and `ls` return real stdout and exit code 0
4. `cat missing-file` and `false` return real stderr and non-zero exit codes (exit 1)
5. Execution timeout enforcement and process group termination
6. Real-time streaming output limit truncation (1MB cap) without memory accumulation
7. Path traversal rejection (400 Bad Request)
8. Environment secret stripping (sensitive variables removed from subprocess)
"""
from __future__ import annotations

import os
import sys
import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.services.sandbox_manager import SandboxManager


@pytest.fixture(scope="module")
def client():
    """TestClient instance for API tests."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def sandbox_run_fixture():
    """Creates a temporary isolated worktree directory for testing sandbox execution."""
    run_id = f"test-run-{uuid.uuid4().hex[:8]}"
    worktrees_root = Path(settings.worktrees_dir).resolve()
    worktrees_root.mkdir(parents=True, exist_ok=True)

    wt_dir = worktrees_root / run_id
    wt_dir.mkdir(parents=True, exist_ok=True)

    # Seed files inside the worktree
    (wt_dir / "sample_file.txt").write_text("Hello from worktree sample file!\n", encoding="utf-8")
    (wt_dir / "app.py").write_text("print('App inside worktree')\n", encoding="utf-8")

    yield {
        "run_id": run_id,
        "worktree_path": wt_dir,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1. Real Command Execution & PWD Assertion
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_pwd_returns_real_worktree(client: TestClient, sandbox_run_fixture):
    """
    Verifies that running 'pwd' or python getcwd returns the exact canonical worktree directory.
    """
    run_id = sandbox_run_fixture["run_id"]
    expected_wt = sandbox_run_fixture["worktree_path"].resolve()

    cmd = 'python -c "import os; print(os.getcwd())"'
    res = client.post(f"/api/v1/sandbox/{run_id}/exec", json={"command": cmd})
    assert res.status_code == 200
    data = res.json()
    assert data["exit_code"] == 0
    assert data["timed_out"] is False

    # Assert stdout matches canonical worktree path
    actual_cwd = Path(data["stdout"].strip()).resolve()
    assert actual_cwd == expected_wt


# ──────────────────────────────────────────────────────────────────────────────
# 2. Real Stdout and Directory Listing
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_echo_and_ls(client: TestClient, sandbox_run_fixture):
    """
    Verifies real stdout capture and listing of actual worktree files.
    """
    run_id = sandbox_run_fixture["run_id"]

    # Test Echo
    echo_msg = f"hello_sandbox_{uuid.uuid4().hex[:6]}"
    cmd_echo = f'python -c "print(\'{echo_msg}\')"'
    res_echo = client.post(f"/api/v1/sandbox/{run_id}/exec", json={"command": cmd_echo})
    assert res_echo.status_code == 200
    assert echo_msg in res_echo.json()["stdout"]
    assert res_echo.json()["exit_code"] == 0

    # Test Directory Listing
    cmd_ls = 'python -c "import os; print(\',\'.join(sorted(os.listdir(\'.\'))))"'
    res_ls = client.post(f"/api/v1/sandbox/{run_id}/exec", json={"command": cmd_ls})
    assert res_ls.status_code == 200
    files_list = res_ls.json()["stdout"].strip().split(",")
    assert "sample_file.txt" in files_list
    assert "app.py" in files_list


# ──────────────────────────────────────────────────────────────────────────────
# 3. Failed Command & Non-Zero Exit Code Assertion (Anti-Simulation Rule)
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_failed_command_returns_nonzero_exit(client: TestClient, sandbox_run_fixture):
    """
    CRITICAL MANDATORY TEST:
    Failed commands and exit 1 MUST return exit_code=1, NEVER 0.
    """
    run_id = sandbox_run_fixture["run_id"]

    # 1. Explicit exit 1
    cmd_false = 'python -c "import sys; sys.exit(1)"'
    res_false = client.post(f"/api/v1/sandbox/{run_id}/exec", json={"command": cmd_false})
    assert res_false.status_code == 200
    data_false = res_false.json()
    assert data_false["exit_code"] == 1
    assert data_false["exit_code"] != 0

    # 2. Missing file read with stderr capture
    cmd_missing = 'python -c "open(\'non_existent_file_xyz_123.txt\').read()"'
    res_missing = client.post(f"/api/v1/sandbox/{run_id}/exec", json={"command": cmd_missing})
    assert res_missing.status_code == 200
    data_missing = res_missing.json()
    assert data_missing["exit_code"] != 0
    assert "FileNotFoundError" in data_missing["stderr"] or "No such file" in data_missing["stderr"]


# ──────────────────────────────────────────────────────────────────────────────
# 4. Timeout Enforcement & Process Group Termination
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_timeout_enforcement(client: TestClient, sandbox_run_fixture):
    """
    Verifies that commands exceeding timeout are terminated and flagged timed_out=True.
    """
    run_id = sandbox_run_fixture["run_id"]

    cmd_sleep = 'python -c "import time; time.sleep(10)"'
    res = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": cmd_sleep, "timeout_sec": 2},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["timed_out"] is True
    assert data["exit_code"] != 0
    assert "timed out" in data["stderr"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# 5. Real-Time Streaming Output Limit
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_streaming_output_limit(client: TestClient, sandbox_run_fixture):
    """
    Verifies that high-output commands are killed when exceeding 1MB stream limit.
    """
    run_id = sandbox_run_fixture["run_id"]

    # Generates continuous stream of lines
    cmd_flood = 'python -c "while True: print(\'X\' * 10000)"'
    res = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": cmd_flood, "timeout_sec": 5},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["output_truncated"] is True
    # Verify memory is bounded (captured length <= 1.1MB)
    assert len(data["stdout"].encode("utf-8")) <= 1024 * 1024 + 4096


# ──────────────────────────────────────────────────────────────────────────────
# 6. Path Traversal Rejection
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_path_traversal_rejection(client: TestClient):
    """
    Verifies that client cannot specify a run_id containing traversal paths.
    """
    res = client.post("/api/v1/sandbox/..%2F..%2Fescape/exec", json={"command": "pwd"})
    assert res.status_code in [400, 404]


# ──────────────────────────────────────────────────────────────────────────────
# 7. Environment Secret Stripping
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_environment_secret_stripping(client: TestClient, sandbox_run_fixture):
    """
    Verifies that sensitive environment variables are stripped before command execution.
    """
    run_id = sandbox_run_fixture["run_id"]

    # Temporarily set dummy secrets in host environment
    os.environ["JWT_SECRET"] = "super_secret_jwt_key_123"
    os.environ["GITHUB_CLIENT_SECRET"] = "github_oauth_secret_abc"
    os.environ["AZURE_STORAGE_ACCOUNT_KEY"] = "azure_storage_key_xyz"

    cmd = 'python -c "import os; print(\\\"JWT=\\\" + str(os.environ.get(\\\"JWT_SECRET\\\", \\\"CLEAN\\\")))"'
    res = client.post(f"/api/v1/sandbox/{run_id}/exec", json={"command": cmd})
    assert res.status_code == 200
    data = res.json()
    stdout = data["stdout"]
    assert "super_secret_jwt_key_123" not in stdout
    assert "CLEAN" in stdout


# ──────────────────────────────────────────────────────────────────────────────
# 8. Recovery After Failure
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_recovery_after_failure(client: TestClient, sandbox_run_fixture):
    """
    Verifies that a subsequent command executes cleanly and succeeds after a failure.
    """
    run_id = sandbox_run_fixture["run_id"]

    # 1. First command fails
    res_fail = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": 'python -c "import sys; sys.exit(1)"'},
    )
    assert res_fail.status_code == 200
    assert res_fail.json()["exit_code"] == 1

    # 2. Second command succeeds and returns exit code 0
    res_success = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": 'python -c "print(\'recovered_state\')"', "timeout_sec": 30},
    )
    assert res_success.status_code == 200
    assert res_success.json()["exit_code"] == 0
    assert "recovered_state" in res_success.json()["stdout"]


# ──────────────────────────────────────────────────────────────────────────────
# 9. Timeout Range and Empty Command Validation
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_timeout_and_empty_command_validation(client: TestClient, sandbox_run_fixture):
    """
    Verifies that empty commands and out-of-range timeouts (<=0 or >120) are rejected.
    """
    run_id = sandbox_run_fixture["run_id"]

    # Empty command
    res_empty = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": "   "},
    )
    assert res_empty.status_code in [400, 422]

    # Timeout > 120
    res_too_long = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": "pwd", "timeout_sec": 121},
    )
    assert res_too_long.status_code == 422

    # Timeout <= 0
    res_zero = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": "pwd", "timeout_sec": 0},
    )
    assert res_zero.status_code == 422

