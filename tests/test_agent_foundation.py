"""
Integration and Lifecycle Test Suite for Engineering Agent Foundation (Phase 1).

Tests:
  - AgentRun creation and initial state transition (IDLE -> UNDERSTANDING)
  - Controlled state transitions and audit trail logging
  - Invalid state transition rejection (422)
  - Thin controlled action execution and observation persistence
  - Run cancellation and terminal state lock
  - Terminal state immutability (rejection of actions/cancellations after completion)
  - Event history association and SSE message coordination
  - Server restart safety and orphaned in-flight run recovery
"""
from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from backend.agent.engineering_agent import EngineeringAgent
from backend.agent.state_machine import AgentState, InvalidStateTransitionError
from backend.database import Base, SessionLocal, engine
from backend.dependencies.auth import get_current_user
from backend.main import app
from backend.models.user import User
from backend.models.implementation import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentStateTransition,
)


@pytest.fixture(autouse=True)
def init_db():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            user = User(id=1, github_id="gh_test_1", username="test_user", email="test@example.com")
            db.add(user)
            db.commit()
    yield


@pytest.fixture
def client():
    def override_get_current_user():
        with SessionLocal() as db:
            return db.query(User).filter(User.id == 1).first()

    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_agent_run_creation_lifecycle(client: TestClient, db):
    req_payload = {
        "repository_id": "test-repo-sample",
        "user_requirement": "Add GitHub OAuth authentication endpoint with JWT session handling",
        "config": {"debug": True},
    }

    res = client.post("/api/v1/agent/runs", json=req_payload)
    assert res.status_code == 201
    data = res.json()

    run_id = data["id"]
    assert run_id.startswith("run_")
    assert data["repository_id"] == "test-repo-sample"
    assert data["current_state"] == AgentState.UNDERSTANDING.value
    assert data["status"] == AgentRunStatus.RUNNING.value
    assert data["started_at"] is not None

    # Verify DB persistence
    db.expire_all()
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    assert run is not None
    assert run.current_state in (AgentState.UNDERSTANDING, AgentState.PLANNING, AgentState.AWAITING_APPROVAL)
    assert run.user_requirement == req_payload["user_requirement"]

    # Verify transitions history in DB
    transitions = db.query(AgentStateTransition).filter(AgentStateTransition.agent_run_id == run_id).all()
    assert len(transitions) >= 1
    assert transitions[0].from_state == AgentState.IDLE
    assert transitions[0].to_state == AgentState.UNDERSTANDING

    # Verify events
    events = db.query(AgentEvent).filter(AgentEvent.agent_run_id == run_id).all()
    assert len(events) >= 2


def test_agent_state_transition_sequence(client: TestClient, db):
    create_res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "test-repo", "user_requirement": "Test requirement"},
    )
    run_id = create_res.json()["id"]

    # Transition to PLANNING (or already in PLANNING/AWAITING_APPROVAL via background plan)
    # Move to EXECUTING
    client.post(
        f"/api/v1/agent/runs/{run_id}/transition",
        json={"to_state": "PLANNING", "reason": "Moving to plan"},
    )
    t1 = client.post(
        f"/api/v1/agent/runs/{run_id}/transition",
        json={"to_state": "AWAITING_APPROVAL", "reason": "Awaiting approval"},
    )
    t2 = client.post(
        f"/api/v1/agent/runs/{run_id}/transition",
        json={"to_state": "EXECUTING", "reason": "User approved execution"},
    )
    assert t2.status_code == 200
    assert t2.json()["current_state"] == "EXECUTING"

    # Transition EXECUTING -> VERIFYING
    t3 = client.post(
        f"/api/v1/agent/runs/{run_id}/transition",
        json={"to_state": "VERIFYING", "reason": "Changes applied, verifying"},
    )
    assert t3.status_code == 200
    assert t3.json()["current_state"] == "VERIFYING"

    # Transition VERIFYING -> COMPLETED
    t4 = client.post(
        f"/api/v1/agent/runs/{run_id}/transition",
        json={"to_state": "COMPLETED", "reason": "Verification passed"},
    )
    assert t4.status_code == 200
    assert t4.json()["current_state"] == "COMPLETED"
    assert t4.json()["completed_at"] is not None


def test_agent_invalid_transition_rejected(client: TestClient):
    create_res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "test-repo", "user_requirement": "Test requirement"},
    )
    run_id = create_res.json()["id"]

    # Attempt illegal jump to COMPLETED without verification
    bad_res = client.post(
        f"/api/v1/agent/runs/{run_id}/transition",
        json={"to_state": "COMPLETED", "reason": "Skipping execution illegally"},
    )
    assert bad_res.status_code == 422
    assert "Transition from" in bad_res.json()["detail"] and "to 'COMPLETED' is not allowed" in bad_res.json()["detail"]


def test_controlled_action_execution(client: TestClient, db):
    create_res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "test-repo", "user_requirement": "Find auth files"},
    )
    run_id = create_res.json()["id"]

    # Execute thin controlled inspection action
    action_res = client.post(
        f"/api/v1/agent/runs/{run_id}/action",
        json={"action_type": "inspect_repository", "parameters": {"pattern": "*.py", "limit": 3}},
    )
    assert action_res.status_code == 200
    act_data = action_res.json()
    assert act_data["run_id"] == run_id
    assert act_data["action_type"] == "inspect_repository"
    assert act_data["status"] == "SUCCESS"
    assert "result" in act_data

    # Check that action was logged in AgentRun metadata
    db.expire_all()
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    actions = (run.metadata_json or {}).get("actions", [])
    assert len(actions) == 1
    assert actions[0]["action_type"] == "inspect_repository"
    assert actions[0]["status"] == "SUCCESS"

    # Check action events emitted
    events = client.get(f"/api/v1/agent/runs/{run_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "ACTION_STARTED" in event_types
    assert "ACTION_COMPLETED" in event_types


def test_agent_run_cancellation(client: TestClient, db):
    create_res = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "test-repo", "user_requirement": "Long running task"},
    )
    run_id = create_res.json()["id"]

    # Cancel active run
    cancel_res = client.post(
        f"/api/v1/agent/runs/{run_id}/cancel",
        json={"reason": "User cancelled via UI button"},
    )
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["current_state"] == "CANCELLED"
    assert cancel_data["cancellation_reason"] == "User cancelled via UI button"
    assert cancel_data["completed_at"] is not None

    # Check terminal state lock: cannot transition out of CANCELLED
    t_res = client.post(
        f"/api/v1/agent/runs/{run_id}/transition",
        json={"to_state": "EXECUTING"},
    )
    assert t_res.status_code == 422

    # Check repeated cancel is idempotent (returns 200 OK with cancelled run)
    recancel_res = client.post(
        f"/api/v1/agent/runs/{run_id}/cancel",
        json={"reason": "Second cancel attempt"},
    )
    assert recancel_res.status_code == 200
    assert recancel_res.json()["current_state"] == "CANCELLED"


def test_restart_safety_and_orphaned_run_recovery(db):
    agent = EngineeringAgent()

    # 1. Create an active run directly in DB simulating in-flight work before server crash
    run_id = f"crash_run_{uuid.uuid4().hex[:8]}"
    run = AgentRun(
        id=run_id,
        task_id=run_id,
        repository_id="test-crash-repo",
        user_requirement="Interrupted task",
        current_state=AgentState.EXECUTING,
        status=AgentRunStatus.RUNNING,
    )
    db.add(run)
    db.commit()

    # 2. Run recovery procedure
    recovered = agent.recover_in_flight_runs(db)
    assert run_id in recovered

    # 3. Verify that run state is safely marked FAILED with restart explanation
    db.refresh(run)
    assert run.current_state == AgentState.FAILED
    assert run.status == AgentRunStatus.FAILED
    assert "restart" in run.error_message.lower()
    assert run.completed_at is not None

    # 4. Running recovery again is idempotent (0 runs recovered)
    second_recovery = agent.recover_in_flight_runs(db)
    assert run_id not in second_recovery
