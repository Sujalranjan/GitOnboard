"""
Phase 1 Security & Data Integrity Remediation Test Suite.

Verifies:
1. SEC-001: Sandbox HTTP endpoints and WebSocket terminal authentication & run ownership enforcement.
2. SEC-002: Verification and repair endpoints authentication, run ownership, and strict worktree containment.
3. Agent Authorization: Comprehensive multi-tenant isolation across all /api/v1/agent/* routes and legacy NULL checks.
4. DAT-001: Multi-tenant repository coexistence without global unique collision.
5. SEC-003: Cookie SameSite=Lax enforcement.
"""
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.database import Base, get_db
from backend.main import app
from backend.models.implementation import AgentRun, AgentRunStatus, AgentState
from backend.models.repository import Repository
from backend.models.user import User


# Helper to create auth cookies
def create_auth_cookie(user_id: int, username: str = "testuser") -> dict:
    payload = {
        "user_id": user_id,
        "sub": str(user_id),
        "username": username,
        "email": f"{username}@example.com",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"access_token": token}


@pytest.fixture(scope="module")
def test_env():
    """Sets up an isolated SQLite database and test client for Phase 1 verification."""
    test_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    test_db_file.close()
    
    engine = create_engine(
        f"sqlite:///{test_db_file.name}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    
    # Create test users
    with TestingSessionLocal() as db:
        user1 = User(id=1, github_id="gh_1", username="alice", email="alice@example.com")
        user2 = User(id=2, github_id="gh_2", username="bob", email="bob@example.com")
        db.add_all([user1, user2])
        db.commit()

    client = TestClient(app)
    
    yield {
        "client": client,
        "db_factory": TestingSessionLocal,
        "user1_cookies": create_auth_cookie(1, "alice"),
        "user2_cookies": create_auth_cookie(2, "bob"),
    }

    # Teardown
    app.dependency_overrides.clear()
    try:
        os.unlink(test_db_file.name)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# SEC-001: Sandbox Security Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_sandbox_unauthenticated_requests_rejected(test_env):
    client = test_env["client"]
    run_id = "run_unauth_test"

    # HTTP Session Create
    res = client.post(f"/api/v1/sandbox/{run_id}/session", json={})
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"

    # HTTP Exec
    res = client.post(f"/api/v1/sandbox/{run_id}/exec", json={"command": "whoami"})
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"

    # HTTP Terminal Reset
    res = client.post(f"/api/v1/sandbox/{run_id}/terminal/reset")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"


def test_sandbox_cross_user_isolation(test_env):
    client = test_env["client"]
    db_factory = test_env["db_factory"]

    # Create run owned by User 1 (Alice)
    run_id = "run_alice_sandbox_001"
    with db_factory() as db:
        run = AgentRun(
            id=run_id,
            task_id=run_id,
            user_id=1,
            user_requirement="Sandbox security check",
            current_state=AgentState.IDLE,
            status=AgentRunStatus.QUEUED,
        )
        db.add(run)
        db.commit()

    # User 2 (Bob) attempts to access Alice's sandbox session
    res = client.post(
        f"/api/v1/sandbox/{run_id}/session",
        json={},
        cookies=test_env["user2_cookies"],
    )
    assert res.status_code == 403, f"Bob should get 403 on Alice's run, got {res.status_code}"

    # User 2 (Bob) attempts to execute commands in Alice's sandbox
    res = client.post(
        f"/api/v1/sandbox/{run_id}/exec",
        json={"command": "id"},
        cookies=test_env["user2_cookies"],
    )
    assert res.status_code == 403, f"Bob should get 403 on Alice's exec, got {res.status_code}"


def test_sandbox_websocket_unauthenticated_and_cross_user(test_env):
    client = test_env["client"]
    db_factory = test_env["db_factory"]

    run_id = "run_alice_ws_001"
    with db_factory() as db:
        run = AgentRun(
            id=run_id,
            task_id=run_id,
            user_id=1,
            user_requirement="WS Security test",
            current_state=AgentState.IDLE,
            status=AgentRunStatus.QUEUED,
        )
        db.add(run)
        db.commit()

    # Unauthenticated WebSocket attempt
    try:
        with client.websocket_connect(f"/api/v1/sandbox/{run_id}/terminal") as ws:
            pass
        pytest.fail("Unauthenticated WebSocket connection should have been rejected")
    except Exception:
        pass  # Rejected before accept as expected

    # Cross-user WebSocket attempt (Bob connecting to Alice's terminal)
    try:
        with client.websocket_connect(
            f"/api/v1/sandbox/{run_id}/terminal",
            cookies=test_env["user2_cookies"],
        ) as ws:
            pass
        pytest.fail("Cross-user WebSocket connection should have been rejected")
    except Exception:
        pass  # Rejected before accept as expected


# ──────────────────────────────────────────────────────────────────────────────
# SEC-002: Verification & Path Containment Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_verify_unauthenticated_rejected(test_env):
    client = test_env["client"]
    res = client.post("/api/v1/verify/run", json={"run_id": "any_run"})
    assert res.status_code == 401

    res = client.post("/api/v1/repair/iterate", json={"run_id": "any_run"})
    assert res.status_code == 401


def test_verify_path_traversal_rejection(test_env):
    client = test_env["client"]
    db_factory = test_env["db_factory"]

    run_id = "run_alice_path_test"
    with db_factory() as db:
        run = AgentRun(
            id=run_id,
            task_id=run_id,
            user_id=1,
            user_requirement="Path traversal check",
            current_state=AgentState.IDLE,
            status=AgentRunStatus.QUEUED,
        )
        db.add(run)
        db.commit()

    # 1. Traversal outside worktrees dir (e.g. ../../)
    res = client.post(
        "/api/v1/verify/run",
        json={
            "run_id": run_id,
            "worktree_path": "../../etc/passwd",
        },
        cookies=test_env["user1_cookies"],
    )
    assert res.status_code in (400, 404), f"Traversal path must be rejected, got {res.status_code}"

    # 2. Absolute path outside worktrees dir
    outside_path = str(Path(tempfile.gettempdir()).resolve())
    res = client.post(
        "/api/v1/verify/run",
        json={
            "run_id": run_id,
            "worktree_path": outside_path,
        },
        cookies=test_env["user1_cookies"],
    )
    assert res.status_code in (400, 403), f"Absolute outside path must be rejected, got {res.status_code}"


def test_verify_cross_user_isolation(test_env):
    client = test_env["client"]
    db_factory = test_env["db_factory"]

    run_id = "run_alice_verif_001"
    with db_factory() as db:
        run = AgentRun(
            id=run_id,
            task_id=run_id,
            user_id=1,
            user_requirement="Verification test",
            current_state=AgentState.IDLE,
            status=AgentRunStatus.QUEUED,
        )
        db.add(run)
        db.commit()

    # Bob attempts to verify Alice's run
    res = client.post(
        "/api/v1/verify/run",
        json={"run_id": run_id},
        cookies=test_env["user2_cookies"],
    )
    assert res.status_code == 403, f"Bob verifying Alice's run should be 403, got {res.status_code}"


# ──────────────────────────────────────────────────────────────────────────────
# Agent Authorization & Legacy NULL Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_agent_unauthenticated_and_cross_user(test_env):
    client = test_env["client"]
    db_factory = test_env["db_factory"]

    # 1. Unauthenticated creation rejected
    res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "my_repo", "user_requirement": "Build auth"},
    )
    assert res.status_code == 401

    # 2. Alice creates run
    res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "alice_repo", "user_requirement": "Alice requirement"},
        cookies=test_env["user1_cookies"],
    )
    assert res.status_code == 201
    run_id = res.json()["id"]

    # 3. Bob attempts to read Alice's run
    res = client.get(f"/api/v1/agent/runs/{run_id}", cookies=test_env["user2_cookies"])
    assert res.status_code == 403, f"Bob reading Alice's run should be 403, got {res.status_code}"

    # 4. Bob attempts to cancel Alice's run
    res = client.post(f"/api/v1/agent/runs/{run_id}/cancel", cookies=test_env["user2_cookies"])
    assert res.status_code == 403, f"Bob cancelling Alice's run should be 403, got {res.status_code}"

    # 5. Alice cancels her own run -> succeeds
    res = client.post(f"/api/v1/agent/runs/{run_id}/cancel", cookies=test_env["user1_cookies"])
    assert res.status_code == 200
    assert res.json()["current_state"] == "CANCELLED"

    # 6. Duplicate cancel is idempotent (returns 200 OK)
    res = client.post(f"/api/v1/agent/runs/{run_id}/cancel", cookies=test_env["user1_cookies"])
    assert res.status_code == 200
    assert res.json()["current_state"] == "CANCELLED"


def test_agent_legacy_null_user_id_rejection(test_env):
    client = test_env["client"]
    db_factory = test_env["db_factory"]

    # Create legacy run with NULL user_id and unassociated repository
    legacy_run_id = "run_legacy_null_user_001"
    with db_factory() as db:
        run = AgentRun(
            id=legacy_run_id,
            task_id=legacy_run_id,
            user_id=None,
            repository_id="unrelated_legacy_repo",
            user_requirement="Legacy requirement",
            current_state=AgentState.IDLE,
            status=AgentRunStatus.QUEUED,
        )
        db.add(run)
        db.commit()

    # User 1 attempts to access legacy run without provable ownership -> 403
    res = client.get(f"/api/v1/agent/runs/{legacy_run_id}", cookies=test_env["user1_cookies"])
    assert res.status_code == 403, f"Unproven legacy run must return 403, got {res.status_code}"


# ──────────────────────────────────────────────────────────────────────────────
# DAT-001: Multi-Tenant Repository Coexistence
# ──────────────────────────────────────────────────────────────────────────────

def test_multi_tenant_repository_coexistence(test_env):
    db_factory = test_env["db_factory"]

    shared_repo_url = "https://github.com/pallets/flask"
    shared_github_id = "12345678"

    with db_factory() as db:
        # Alice imports flask
        repo_alice = Repository(
            url=shared_repo_url,
            github_repo_id=shared_github_id,
            default_branch="main",
            user_id=1,
        )
        db.add(repo_alice)
        db.commit()

        # Bob imports same flask repo
        repo_bob = Repository(
            url=shared_repo_url,
            github_repo_id=shared_github_id,
            default_branch="main",
            user_id=2,
        )
        db.add(repo_bob)
        db.commit()

        assert repo_alice.id != repo_bob.id
        assert repo_alice.user_id == 1
        assert repo_bob.user_id == 2


# ──────────────────────────────────────────────────────────────────────────────
# SEC-003: Cookie SameSite=Lax Enforcement
# ──────────────────────────────────────────────────────────────────────────────

def test_auth_logout_sets_samesite_lax(test_env):
    client = test_env["client"]
    res = client.post("/api/auth/github/logout")
    assert res.status_code == 200
    set_cookie = res.headers.get("set-cookie", "")
    assert "samesite=lax" in set_cookie.lower()
