"""
Phase 2.1 Integration & Security Test Suite: Repository Worktree Population & File Consistency.

Verifies:
1. Worktree exists and is a directory.
2. Worktree is populated with real repository files (never an empty .git skeleton).
3. Git repository is valid (clean working tree, valid git rev-parse).
4. Terminal sees real repository files via `ls -la` and `pwd`.
5. File explorer / editor consistency (`cat file` in terminal matches real repository source).
6. Repository isolation between independent runs.
"""
from __future__ import annotations

import os
import shutil
import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.services.worktree_provisioner import WorktreeProvisioner
from backend.services.sandbox_manager import SandboxManager


@pytest.fixture(scope="module")
def client():
    """TestClient instance for API tests."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def sample_repo_fixture():
    """Creates an isolated fixture repository in local repos directory."""
    repo_name = f"sample-repo-{uuid.uuid4().hex[:6]}"
    repos_dir = Path(settings.storage_path) / "repos" / repo_name
    repos_dir.mkdir(parents=True, exist_ok=True)

    # Populate fixture repository
    (repos_dir / "README.md").write_text("# Sample Repository\nReal repository content.", encoding="utf-8")
    (repos_dir / "package.json").write_text('{"name": "sample-pkg", "version": "1.0.0"}', encoding="utf-8")
    (repos_dir / "src").mkdir(parents=True, exist_ok=True)
    (repos_dir / "src" / "index.js").write_text("console.log('Hello from sample repo');", encoding="utf-8")

    yield {
        "repo_name": repo_name,
        "repo_dir": repos_dir,
    }

    # Teardown
    shutil.rmtree(repos_dir, ignore_errors=True)


# ──────────────────────────────────────────────────────────────────────────────
# Test A: Worktree Exists
# ──────────────────────────────────────────────────────────────────────────────

def test_worktree_exists_and_is_dir(client: TestClient, sample_repo_fixture):
    """
    Verifies that resolving a run worktree creates and validates the directory.
    """
    repo_name = sample_repo_fixture["repo_name"]
    run_id = f"{repo_name}_run_{uuid.uuid4().hex[:6]}"

    sm = SandboxManager()
    wt = sm.resolve_worktree(run_id)
    assert wt.exists()
    assert wt.is_dir()


# ──────────────────────────────────────────────────────────────────────────────
# Test B: Worktree is Populated with Real Repository Files (Anti-Skeleton Rule)
# ──────────────────────────────────────────────────────────────────────────────

def test_worktree_is_populated_with_real_files(client: TestClient, sample_repo_fixture):
    """
    Verifies that the worktree contains real repository files and is NOT merely an empty .git directory.
    """
    repo_name = sample_repo_fixture["repo_name"]
    run_id = f"{repo_name}_run_{uuid.uuid4().hex[:6]}"

    sm = SandboxManager()
    wt = sm.resolve_worktree(run_id)

    # Assert real files are present in the worktree
    assert (wt / "README.md").exists()
    assert (wt / "package.json").exists()
    assert (wt / "src" / "index.js").exists()

    # Assert content matches fixture
    readme_text = (wt / "README.md").read_text(encoding="utf-8")
    assert "Real repository content" in readme_text


# ──────────────────────────────────────────────────────────────────────────────
# Test C: Git Repository is Valid
# ──────────────────────────────────────────────────────────────────────────────

def test_worktree_git_repository_is_valid(client: TestClient, sample_repo_fixture):
    """
    Verifies git status and git rev-parse succeed with a clean working tree.
    """
    repo_name = sample_repo_fixture["repo_name"]
    run_id = f"{repo_name}_run_{uuid.uuid4().hex[:6]}"

    # Execute git status in sandbox
    res_status = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": "git status"},
    )
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["exit_code"] == 0
    assert "nothing to commit" in data_status["stdout"] or "working tree clean" in data_status["stdout"]

    # Execute git rev-parse --show-toplevel
    res_toplevel = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": "git rev-parse --show-toplevel"},
    )
    assert res_toplevel.status_code == 200
    assert res_toplevel.json()["exit_code"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Test D: Terminal Sees Real Repository Files via ls -la
# ──────────────────────────────────────────────────────────────────────────────

def test_terminal_sees_real_files_via_ls(client: TestClient, sample_repo_fixture):
    """
    Verifies that running 'ls' or 'ls -la' in the sandbox returns real repository files.
    """
    repo_name = sample_repo_fixture["repo_name"]
    run_id = f"{repo_name}_run_{uuid.uuid4().hex[:6]}"

    res_ls = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": "ls -la"},
    )
    assert res_ls.status_code == 200
    data_ls = res_ls.json()
    assert data_ls["exit_code"] == 0
    stdout = data_ls["stdout"]
    assert "README.md" in stdout
    assert "package.json" in stdout
    assert "src" in stdout


# ──────────────────────────────────────────────────────────────────────────────
# Test E: File Explorer / Code Editor Consistency
# ──────────────────────────────────────────────────────────────────────────────

def test_terminal_editor_content_consistency(client: TestClient, sample_repo_fixture):
    """
    Verifies that reading a file in the terminal via 'cat' returns identical content
    to the source repository file.
    """
    repo_name = sample_repo_fixture["repo_name"]
    run_id = f"{repo_name}_run_{uuid.uuid4().hex[:6]}"

    # Read package.json via sandbox terminal
    res_cat = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": "cat package.json"},
    )
    assert res_cat.status_code == 200
    assert res_cat.json()["exit_code"] == 0
    assert '"name": "sample-pkg"' in res_cat.json()["stdout"]


# ──────────────────────────────────────────────────────────────────────────────
# Test F: Repository Isolation Between Independent Runs
# ──────────────────────────────────────────────────────────────────────────────

def test_repository_isolation_between_runs(client: TestClient):
    """
    Verifies that Run A (for Repo A) and Run B (for Repo B) have distinct files and cannot leak.
    """
    repo_a = f"isolated-a-{uuid.uuid4().hex[:6]}"
    repo_b = f"isolated-b-{uuid.uuid4().hex[:6]}"

    # Setup Repo A
    dir_a = Path(settings.storage_path) / "repos" / repo_a
    dir_a.mkdir(parents=True, exist_ok=True)
    (dir_a / "file_a.txt").write_text("THIS_IS_FILE_A", encoding="utf-8")

    # Setup Repo B
    dir_b = Path(settings.storage_path) / "repos" / repo_b
    dir_b.mkdir(parents=True, exist_ok=True)
    (dir_b / "file_b.txt").write_text("THIS_IS_FILE_B", encoding="utf-8")

    try:
        run_a = f"{repo_a}_run"
        run_b = f"{repo_b}_run"

        # Check Run A
        res_a = client.post(f"/api/v1/sandbox/{run_a}/exec", json={"command": "ls"})
        assert res_a.status_code == 200
        assert "file_a.txt" in res_a.json()["stdout"]
        assert "file_b.txt" not in res_a.json()["stdout"]

        # Check Run B
        res_b = client.post(f"/api/v1/sandbox/{run_b}/exec", json={"command": "ls"})
        assert res_b.status_code == 200
        assert "file_b.txt" in res_b.json()["stdout"]
        assert "file_a.txt" not in res_b.json()["stdout"]
    finally:
        shutil.rmtree(dir_a, ignore_errors=True)
        shutil.rmtree(dir_b, ignore_errors=True)
