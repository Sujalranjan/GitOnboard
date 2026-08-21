"""
Integration tests for Phase 4: Planning Orchestrator & Human Approval Boundary.
"""
from __future__ import annotations

import tempfile
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import Base, SessionLocal, engine
from backend.agent.engineering_agent import EngineeringAgent, EngineeringAgentError
from backend.agent.planning.contracts import PlanStatus
from backend.models.implementation import AgentEvent, AgentEventType, AgentRun, AgentState


@pytest.fixture(autouse=True)
def init_db():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_worktree():
    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        subprocess.run(["git", "init"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=wt_path, capture_output=True, check=True)
        
        main_file = wt_path / "app.py"
        main_file.write_text("def run():\n    print('Hello World')\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=wt_path, capture_output=True, check=True)
        
        yield str(wt_path)


def test_e2e_planning_and_approval_flow(db, sample_worktree):
    agent = EngineeringAgent()

    # 1. Create run
    run = agent.create_run(
        db,
        repository_id="test_repo",
        user_requirement="Add user authentication and authorization module",
    )
    run.worktree_path = sample_worktree
    db.add(run)
    db.commit()

    assert run.current_state == AgentState.UNDERSTANDING

    # 2. Create Plan
    plan = agent.create_plan(db, run_id=run.id)

    assert plan is not None
    assert plan.status == PlanStatus.READY_FOR_APPROVAL
    assert plan.validation.valid is True
    assert len(plan.tasks) >= 2

    # Verify run transitioned to AWAITING_APPROVAL (Human Review Boundary)
    assert run.current_state == AgentState.AWAITING_APPROVAL

    # Invariant: Planning must not modify workspace or create commits
    git_proc = subprocess.run(["git", "status", "--porcelain"], cwd=sample_worktree, capture_output=True, text=True)
    assert git_proc.stdout.strip() == ""

    # 3. Approve Plan
    approved_run = agent.approve_plan(db, run_id=run.id)
    assert approved_run.current_state == AgentState.AWAITING_APPROVAL  # Remains in AWAITING_APPROVAL until Phase 5 consumes it

    # Verify plan status in metadata
    retrieved_plan = agent.get_plan(db, run_id=run.id)
    assert retrieved_plan.status == PlanStatus.APPROVED

    # Verify events
    event_types = [e.event_type for e in run.events]
    assert AgentEventType.PLANNING_STARTED in event_types
    assert AgentEventType.PLANNING_COMPLETED in event_types
    assert AgentEventType.PLAN_READY_FOR_APPROVAL in event_types
    assert AgentEventType.PLAN_APPROVED in event_types


def test_plan_rejection_and_revision_flow(db, sample_worktree):
    agent = EngineeringAgent()

    # 1. Create run and plan v1
    run = agent.create_run(
        db,
        repository_id="test_repo",
        user_requirement="Add payment checkout gateway",
    )
    run.worktree_path = sample_worktree
    db.add(run)
    db.commit()

    plan_v1 = agent.create_plan(db, run_id=run.id)
    assert plan_v1.version == 1
    assert run.current_state == AgentState.AWAITING_APPROVAL

    # 2. Reject Plan v1
    agent.reject_plan(db, run_id=run.id, reason="Please split checkout into separate card and wallet tasks")
    
    # Verify state transitioned back to PLANNING for revision
    assert run.current_state == AgentState.PLANNING

    # Invariant: Rejection NEVER triggers task execution or files change
    git_proc = subprocess.run(["git", "status", "--porcelain"], cwd=sample_worktree, capture_output=True, text=True)
    assert git_proc.stdout.strip() == ""

    # 3. Create revised Plan v2
    plan_v2 = agent.create_plan(db, run_id=run.id)
    assert plan_v2.version == 2
    assert run.current_state == AgentState.AWAITING_APPROVAL



def test_plan_http_endpoints(client, sample_worktree):
    # 1. Create run
    res_create = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "api_test_repo", "user_requirement": "Add metrics export endpoint"},
    )
    assert res_create.status_code == 201
    run_id = res_create.json()["id"]

    # 2. Create Plan via POST
    res_plan = client.post(f"/api/v1/agent/runs/{run_id}/plan")
    assert res_plan.status_code == 200
    plan_data = res_plan.json()
    assert plan_data["status"] == "READY_FOR_APPROVAL"
    assert len(plan_data["tasks"]) >= 2

    # 3. Get Plan via GET
    res_get = client.get(f"/api/v1/agent/runs/{run_id}/plan")
    assert res_get.status_code == 200
    assert res_get.json()["plan_id"] == plan_data["plan_id"]

    # 4. Approve Plan via POST
    res_approve = client.post(f"/api/v1/agent/runs/{run_id}/plan/approve")
    assert res_approve.status_code == 200
    assert res_approve.json()["current_state"] == "AWAITING_APPROVAL"

    # Verify approved status in plan
    res_get_approved = client.get(f"/api/v1/agent/runs/{run_id}/plan")
    assert res_get_approved.json()["status"] == "APPROVED"
