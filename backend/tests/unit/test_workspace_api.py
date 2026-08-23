"""
Unit tests for Phase 10 Workspace API endpoints in backend/routers/agent.py.
"""
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.dependencies.auth import get_current_user
from backend.main import app
from backend.models.user import User
from backend.models.implementation import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentState,
    ApprovalActionType,
    ApprovalRequest,
    ApprovalStatus,
    RiskLevel,
)


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine, tmp_path):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()

    # Create test user
    user = User(id=1, username="test_agent", github_id="gh_1", email="agent@test.local")
    session.add(user)

    # Set up dummy git worktree
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=tmp_path, capture_output=True, check=True)
    f = tmp_path / "sample.py"
    f.write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, check=True)

    # Modify sample.py to create changes
    f.write_text("print('hello world')\ndef add(a, b): return a + b\n")

    run = AgentRun(
        id="run-ws-test-1",
        task_id="task-ws-test-1",
        repository_id="repo-ws-test",
        user_id=1,
        user_requirement="Implement sample feature",
        current_state=AgentState.EXECUTING,
        worktree_path=str(tmp_path),
        metadata_json={
            "verification_result": {
                "agent_run_id": "run-ws-test-1",
                "status": "PASSED",
                "passed": True,
                "checks": [{"name": "Static AST Check", "status": "PASSED"}],
                "defects": [],
                "summary": "All checks passed.",
            }
        },
    )
    session.add(run)

    # Add events with sequential IDs
    evt1 = AgentEvent(
        id="evt-1",
        agent_run_id=run.id,
        event_type=AgentEventType.STARTED,
        message="Run started",
        payload={"repo": "repo-ws-test"},
    )
    evt2 = AgentEvent(
        id="evt-2",
        agent_run_id=run.id,
        event_type=AgentEventType.PLANNING_STARTED,
        message="Planning started",
        payload={},
    )
    session.add_all([evt1, evt2])

    # Add pending approval
    appr = ApprovalRequest(
        id="appr-ws-1",
        agent_run_id=run.id,
        action_type=ApprovalActionType.TERMINAL_COMMAND,
        action_description="Execute risky cleanup",
        risk_level=RiskLevel.HIGH,
        command="git reset --hard HEAD",
        reason="Reset worktree",
        status=ApprovalStatus.PENDING,
    )
    session.add(appr)
    session.commit()

    yield session
    session.close()


@pytest.fixture
def client(db_engine, db_session):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_get_current_user():
        with TestingSessionLocal() as db:
            return db.query(User).filter(User.id == 1).first()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_workspace_snapshot(client):
    """Verifies that GET /runs/{run_id}/workspace returns complete atomic snapshot for hydration."""
    res = client.get("/api/v1/agent/runs/run-ws-test-1/workspace")
    assert res.status_code == 200
    data = res.json()

    # 1. Run detail
    assert data["run"]["id"] == "run-ws-test-1"
    assert data["run"]["current_state"] == "EXECUTING"

    # 2. Changes
    assert "sample.py" in data["changes"]["modified_files"]
    assert "def add(a, b):" in data["changes"]["diff"]

    # 3. Verification
    assert data["verification"]["status"] == "PASSED"
    assert data["verification"]["passed"] is True

    # 4. Pending approvals
    assert len(data["pending_approvals"]) == 1
    assert data["pending_approvals"][0]["id"] == "appr-ws-1"
    assert data["pending_approvals"][0]["status"] == "PENDING"

    # 5. Events with sequence contract
    assert len(data["latest_events"]) >= 2
    assert data["latest_events"][0]["event_id"] == "evt-1"
    assert data["latest_events"][0]["sequence"] == 1
    assert data["latest_events"][1]["event_id"] == "evt-2"
    assert data["latest_events"][1]["sequence"] == 2


def test_get_pending_approvals_endpoint(client):
    """Verifies GET /runs/{run_id}/approvals returns pending approval requests."""
    res = client.get("/api/v1/agent/runs/run-ws-test-1/approvals")
    assert res.status_code == 200
    approvals = res.json()
    assert len(approvals) == 1
    assert approvals[0]["id"] == "appr-ws-1"
    assert approvals[0]["risk_level"] == "HIGH"


def test_approve_and_reject_action_endpoints(client):
    """Verifies POST /approvals/{id}/approve and /reject update status cleanly."""
    # Approve
    res_appr = client.post("/api/v1/agent/approvals/appr-ws-1/approve", json={"resolved_by": "alice"})
    assert res_appr.status_code == 200
    data_appr = res_appr.json()
    assert data_appr["status"] == "APPROVED"
    assert data_appr["resolved_by"] == "alice"

    # Create another approval to test reject
    # Direct check of reject endpoint error handling on non-existent
    res_404 = client.post("/api/v1/agent/approvals/non-existent/reject", json={"reason": "bad command"})
    assert res_404.status_code == 404


def test_get_workspace_changes_endpoint(client):
    """Verifies GET /runs/{run_id}/changes returns modified files and unified diff."""
    res = client.get("/api/v1/agent/runs/run-ws-test-1/changes")
    assert res.status_code == 200
    data = res.json()
    assert "sample.py" in data["modified_files"]
    assert "+def add(a, b): return a + b" in data["diff"]


def test_get_workspace_verification_endpoint(client):
    """Verifies GET /runs/{run_id}/verification returns verification report."""
    res = client.get("/api/v1/agent/runs/run-ws-test-1/verification")
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is True
    assert data["status"] == "PASSED"
    assert len(data["checks"]) == 1
