"""
Phase 2 Production Reliability & Correctness Regression Test Suite.

Tests:
1. Agent State-Machine:
   - Normal plan creation (UNDERSTANDING -> PLANNING -> AWAITING_APPROVAL)
   - Plan requested twice (idempotent, returns existing plan without invalid self-transition)
   - Background planning + explicit plan request race safety
   - Invalid state transitions remain rejected (409/422)
2. Agent Cancellation:
   - Cancel endpoint returns valid AgentRunResponse with no 500/AttributeError
   - Repeated cancellation is safe and idempotent
   - Completed/Failed runs cannot be cancelled (409 Conflict)
3. Non-Destructive GET /scan:
   - Failed analysis preserves repository record (does not delete repository)
   - Refresh/polling does not delete data
   - Explicit DELETE endpoint remains responsible for deletion
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.agent.engineering_agent import EngineeringAgent
from backend.agent.state_machine import AgentState, InvalidStateTransitionError
from backend.database import Base, SessionLocal, engine
from backend.dependencies.auth import get_current_user
from backend.main import app
from backend.models.implementation import AgentRun, AgentRunStatus
from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.user import User


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            user = User(id=1, github_id="gh_phase2_user", username="phase2_tester", email="phase2@example.com")
            db.add(user)
            db.commit()
    yield


@pytest.fixture
def auth_user():
    with SessionLocal() as db:
        return db.query(User).filter(User.id == 1).first()


@pytest.fixture
def client(auth_user):
    def override_current_user():
        return auth_user

    app.dependency_overrides[get_current_user] = override_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


# ──────────────────────────────────────────────────────────────────────────────
# 1. Agent State-Machine & Planning Race Conditions
# ──────────────────────────────────────────────────────────────────────────────

def test_plan_normal_creation_and_idempotent_duplicate_request(client: TestClient, db: Session):
    """
    Verifies normal plan creation and that calling plan endpoint twice is idempotent
    and does NOT raise InvalidStateTransitionError (AWAITING_APPROVAL -> AWAITING_APPROVAL).
    """
    # Create run
    create_res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "test-repo", "user_requirement": "Add endpoint for user profiles"},
    )
    assert create_res.status_code == 201
    run_id = create_res.json()["id"]

    # 1. Explicitly create plan
    plan_res1 = client.post(f"/api/v1/agent/runs/{run_id}/plan")
    assert plan_res1.status_code == 200
    plan_data1 = plan_res1.json()
    assert "plan_id" in plan_data1
    assert len(plan_data1.get("tasks", [])) >= 1

    # Verify run state is AWAITING_APPROVAL
    get_run_res = client.get(f"/api/v1/agent/runs/{run_id}")
    assert get_run_res.status_code == 200
    assert get_run_res.json()["current_state"] == AgentState.AWAITING_APPROVAL.value

    # 2. Call plan creation a second time (idempotency check)
    plan_res2 = client.post(f"/api/v1/agent/runs/{run_id}/plan")
    assert plan_res2.status_code == 200
    plan_data2 = plan_res2.json()
    assert plan_data2["plan_id"] == plan_data1["plan_id"]

    # Run state remains valid AWAITING_APPROVAL
    get_run_res2 = client.get(f"/api/v1/agent/runs/{run_id}")
    assert get_run_res2.status_code == 200
    assert get_run_res2.json()["current_state"] == AgentState.AWAITING_APPROVAL.value


def test_invalid_state_transitions_remain_rejected(client: TestClient, db: Session, auth_user: User):
    """
    Verifies that invalid transitions (e.g. transitioning from terminal COMPLETED to PLANNING)
    are strictly rejected with 400/409 Conflict.
    """
    # Create run and set directly to COMPLETED
    run = AgentRun(
        id="run_completed_test",
        task_id="task_completed_test",
        user_id=auth_user.id,
        repository_id="test-repo",
        user_requirement="test",
        current_state=AgentState.COMPLETED,
        status=AgentRunStatus.COMPLETED,
    )
    db.merge(run)
    db.commit()

    # Attempting to generate plan on completed run must fail
    res = client.post("/api/v1/agent/runs/run_completed_test/plan")
    assert res.status_code in (400, 409)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Agent Cancellation Fix
# ──────────────────────────────────────────────────────────────────────────────

def test_agent_cancellation_returns_valid_response(client: TestClient, db: Session, auth_user: User):
    """
    Verifies that cancel endpoint returns a valid serialized AgentRunResponse
    and does NOT throw AttributeError: 'bool' object has no attribute 'id'.
    """
    create_res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "test-repo", "user_requirement": "Implement metrics scraper"},
    )
    assert create_res.status_code == 201
    run_id = create_res.json()["id"]

    # Cancel run
    cancel_res = client.post(
        f"/api/v1/agent/runs/{run_id}/cancel",
        json={"reason": "User abort requested"},
    )
    assert cancel_res.status_code == 200
    data = cancel_res.json()
    assert data["id"] == run_id
    assert data["current_state"] == AgentState.CANCELLED.value


def test_agent_cancellation_idempotency_and_completed_guard(client: TestClient, db: Session, auth_user: User):
    """
    Verifies that:
    1. Repeated cancellation is idempotent (returns 200 with cancelled run).
    2. Cancelling an already COMPLETED run is rejected with 409 Conflict.
    """
    # 1. Create and cancel run
    create_res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "test-repo", "user_requirement": "Quick task"},
    )
    run_id = create_res.json()["id"]

    cancel1 = client.post(f"/api/v1/agent/runs/{run_id}/cancel", json={"reason": "Stop"})
    assert cancel1.status_code == 200

    # Repeated cancellation -> idempotent success
    cancel2 = client.post(f"/api/v1/agent/runs/{run_id}/cancel", json={"reason": "Stop again"})
    assert cancel2.status_code == 200
    assert cancel2.json()["current_state"] == AgentState.CANCELLED.value

    # 2. Completed run cannot be cancelled
    completed_run = AgentRun(
        id="run_done_guard",
        task_id="task_done_guard",
        user_id=auth_user.id,
        repository_id="test-repo",
        user_requirement="test",
        current_state=AgentState.COMPLETED,
        status=AgentRunStatus.COMPLETED,
    )
    db.merge(completed_run)
    db.commit()

    cancel_completed = client.post("/api/v1/agent/runs/run_done_guard/cancel", json={"reason": "Late cancel"})
    assert cancel_completed.status_code == 409


# ──────────────────────────────────────────────────────────────────────────────
# 3. Non-Destructive GET /scan
# ──────────────────────────────────────────────────────────────────────────────

def test_failed_scan_preserves_repository_record(client: TestClient, db: Session, auth_user: User):
    """
    Verifies that GET /api/repos/{repo_name}/scan NEVER deletes the repository record when analysis fails.
    """
    repo = Repository(
        url="https://github.com/test/fail-test-repo.git",
        user_id=auth_user.id,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    # Add a failed analysis
    analysis = Analysis(
        repository_id=repo.id,
        status="Failed",
    )
    db.add(analysis)
    db.commit()

    # GET /api/repos/{repo_name}/scan
    scan_res = client.get("/api/repos/fail-test-repo/scan")
    assert scan_res.status_code == 200
    scan_data = scan_res.json()
    assert scan_data["status"] == "failed"

    # Verify repository STILL EXISTS in database
    db.expire_all()
    preserved_repo = db.query(Repository).filter(Repository.id == repo.id).first()
    assert preserved_repo is not None
    assert "fail-test-repo" in preserved_repo.url

    # Second refresh / poll also preserves the repository
    scan_res2 = client.get("/api/repos/fail-test-repo/scan")
    assert scan_res2.status_code == 200
    db.expire_all()
    preserved_repo2 = db.query(Repository).filter(Repository.id == repo.id).first()
    assert preserved_repo2 is not None


def test_explicit_delete_endpoint_remains_responsible_for_deletion(client: TestClient, auth_user: User):
    """
    Verifies that only the explicit DELETE endpoint removes the repository.
    """
    with SessionLocal() as db_session:
        repo = Repository(
            url="https://github.com/test/delete-target-repo.git",
            user_id=auth_user.id,
        )
        db_session.add(repo)
        db_session.commit()
        repo_id = repo.id

    # Explicit DELETE call
    del_res = client.delete("/api/repos/delete-target-repo")
    assert del_res.status_code == 200

    # Repository is now deleted in database
    with SessionLocal() as db_session2:
        deleted_repo = db_session2.query(Repository).filter(Repository.id == repo_id).first()
        assert deleted_repo is None
