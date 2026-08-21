"""
Integration Test Suite for Task Orchestrator & Execution Control Layer (Phase 5).
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.agent.engineering_agent import EngineeringAgent, EngineeringAgentError
from backend.agent.planning.contracts import PlanStatus, PlanTaskStatus
from backend.agent.state_machine import AgentState
from backend.database import Base, SessionLocal, engine
from backend.main import app
from backend.models.implementation import AgentEvent, AgentEventType, AgentRun, AgentRunStatus


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


def test_e2e_plan_execution_and_task_lifecycle(db, sample_worktree):
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

    # 2. Create and Approve Plan
    plan = agent.create_plan(db, run_id=run.id)
    assert run.current_state == AgentState.AWAITING_APPROVAL
    agent.approve_plan(db, run_id=run.id)

    # 3. Start Plan Execution (AWAITING_APPROVAL -> EXECUTING)
    agent.start_plan_execution(db, run_id=run.id)
    assert run.current_state == AgentState.EXECUTING

    # 4. Sequentially execute tasks
    tasks = agent.get_plan_tasks(db, run_id=run.id)
    assert len(tasks) >= 2

    executed_count = 0
    while True:
        task, result = agent.execute_next_task(db, run_id=run.id)
        if not task:
            break
        executed_count += 1
        assert task.status == PlanTaskStatus.PASSED
        assert result is not None
        assert result.success is True

    assert executed_count == len(tasks)

    # Verify all tasks reached PASSED
    final_tasks = agent.get_plan_tasks(db, run_id=run.id)
    assert all(t.status == PlanTaskStatus.PASSED for t in final_tasks)

    # Verify event audit trail
    event_types = [e.event_type for e in run.events]
    assert AgentEventType.NEXT_TASK_SELECTED in event_types
    assert AgentEventType.TASK_STARTED in event_types
    assert AgentEventType.TASK_EXECUTION_COMPLETED in event_types
    assert AgentEventType.TASK_VERIFYING in event_types
    assert AgentEventType.TASK_PASSED in event_types


def test_unapproved_execution_rejected(db, sample_worktree):
    agent = EngineeringAgent()

    # Create run and plan, but DO NOT approve
    run = agent.create_run(
        db,
        repository_id="test_repo",
        user_requirement="Add payment module",
    )
    run.worktree_path = sample_worktree
    db.add(run)
    db.commit()

    plan = agent.create_plan(db, run_id=run.id)
    assert plan.status == PlanStatus.READY_FOR_APPROVAL

    # Execution must be rejected
    with pytest.raises(EngineeringAgentError, match="Plan must be explicitly APPROVED"):
        agent.start_plan_execution(db, run_id=run.id)


def test_run_cancellation_during_task_execution(db, sample_worktree):
    agent = EngineeringAgent()

    run = agent.create_run(
        db,
        repository_id="test_repo",
        user_requirement="Add payment module",
    )
    run.worktree_path = sample_worktree
    db.add(run)
    db.commit()

    agent.create_plan(db, run_id=run.id)
    agent.approve_plan(db, run_id=run.id)
    agent.start_plan_execution(db, run_id=run.id)

    # Execute first task
    t1, res1 = agent.execute_next_task(db, run_id=run.id)
    assert t1.status == PlanTaskStatus.PASSED

    # Cancel run before task 2
    agent.cancel_run(db, run_id=run.id, reason="User cancelled execution")
    assert run.current_state == AgentState.CANCELLED

    # Subsequent execution attempt must raise
    with pytest.raises(EngineeringAgentError):
        agent.execute_next_task(db, run_id=run.id)


def test_server_restart_preserves_truthful_task_state(db, sample_worktree):
    agent = EngineeringAgent()

    run = agent.create_run(
        db,
        repository_id="test_repo",
        user_requirement="Add reporting endpoint",
    )
    run.worktree_path = sample_worktree
    db.add(run)
    db.commit()

    agent.create_plan(db, run_id=run.id)
    agent.approve_plan(db, run_id=run.id)
    agent.start_plan_execution(db, run_id=run.id)

    # Manually mark task-1 as RUNNING in plan metadata to simulate crash during execution
    plan = agent.get_plan(db, run_id=run.id)
    plan.tasks[0].status = PlanTaskStatus.RUNNING
    meta = run.metadata_json or {}
    meta["plan"] = plan.model_dump(mode="json")
    run.metadata_json = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(run, "metadata_json")
    db.add(run)
    db.commit()

    # Simulate restart recovery
    recovered = agent.recover_in_flight_runs(db)
    assert run.id in recovered
    assert run.current_state == AgentState.FAILED

    # Verify task-1 was marked BLOCKED, never falsely marked PASSED
    recovered_plan = agent.get_plan(db, run_id=run.id)
    assert recovered_plan.tasks[0].status == PlanTaskStatus.BLOCKED
    assert "Server restart" in recovered_plan.tasks[0].blocked_reason


def test_task_http_endpoints(client, sample_worktree):
    # 1. Create run and plan
    res_create = client.post(
        "/api/v1/agent/runs",
        json={"repository_id": "api_test_repo", "user_requirement": "Add health metrics endpoint"},
    )
    run_id = res_create.json()["id"]

    res_plan = client.post(f"/api/v1/agent/runs/{run_id}/plan")
    assert res_plan.status_code == 200

    # 2. Attempt /execute before approval -> 400 Bad Request
    res_exec_unapproved = client.post(f"/api/v1/agent/runs/{run_id}/execute")
    assert res_exec_unapproved.status_code == 400

    # 3. Approve plan
    res_approve = client.post(f"/api/v1/agent/runs/{run_id}/plan/approve")
    assert res_approve.status_code == 200

    # 4. Start execution via POST /execute
    res_exec = client.post(f"/api/v1/agent/runs/{run_id}/execute")
    assert res_exec.status_code == 200
    assert res_exec.json()["current_state"] == "EXECUTING"

    # 5. Query tasks via GET /tasks
    res_tasks = client.get(f"/api/v1/agent/runs/{run_id}/tasks")
    assert res_tasks.status_code == 200
    tasks = res_tasks.json()
    assert len(tasks) >= 2

    # 6. Execute next task via POST /tasks/next
    res_next = client.post(f"/api/v1/agent/runs/{run_id}/tasks/next")
    assert res_next.status_code == 200
    next_task_data = res_next.json()
    assert next_task_data["task"]["status"] == "PASSED"
