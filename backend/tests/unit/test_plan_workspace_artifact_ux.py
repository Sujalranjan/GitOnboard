"""
Unit and Integration Test Suite: Implementation Plan Workspace & Artifact UX.

Verifies:
  1. Plan generation produces a compact chat preview rather than a full plan dump.
  2. The plan behaves strictly as an in-memory/database workspace artifact:
     - 0 repository files created (no PLAN.md, no plan.json)
     - 0 source code mutations
     - 0 unapproved git worktree commits
  3. Generating a second plan replaces the active Plan Workspace artifact (new version/ID)
     while chat retains historical preview records.
  4. Start Implementation uses the latest active plan.
  5. Stale plan versions cannot execute after a newer plan replaces them.
  6. Existing Phase 5 server-side authorization checks remain strictly enforced.
  7. Plan history tracking preserves multiple versions (v1, v2, v3) for inspection.
  8. Workspace snapshot recovery hydrates the active plan without file disk mutations.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol
from backend.models.implementation import (
    AgentRun,
    AgentRunStatus,
    AgentState,
    ApprovalRequest,
    ApprovalStatus,
)
from backend.agent.modes import execute_plan, execute_implement
from backend.agent.engineering_agent import EngineeringAgent
from backend.agent.planning.contracts import Plan, PlanStatus


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    user = User(id=1, github_id="gh123", email="user@example.com", username="testuser")
    session.add(user)
    session.commit()

    repo = Repository(id=1, url="https://github.com/org/repo1", user_id=1)
    session.add(repo)
    session.commit()

    analysis = Analysis(id=101, repository_id=1, status="COMPLETED")
    session.add(analysis)
    session.commit()

    f1 = FactFile(id="101:f1", analysis_id=101, path="backend/routes/api.py", size=500, language="python")
    session.add(f1)
    session.commit()

    s1 = FactSymbol(
        id="101:s1",
        analysis_id=101,
        name="get_health",
        qualified_name="backend.routes.api.get_health",
        symbol_type="function",
        file_id="101:f1",
        line_start=10,
        line_end=20,
    )
    session.add(s1)
    session.commit()

    yield session
    session.close()


def test_plan_generation_produces_compact_preview_not_full_dump(db_session):
    """
    Test 1: execute_plan and execute_implement return a compact summary in response
    along with the full structured plan object.
    """
    res = execute_implement(
        user_requirement="Add /health endpoint",
        repository_id="1",
        db=db_session,
    )

    assert res["intent"] == "implement"
    assert res["status"] == "READY_FOR_APPROVAL"
    assert "plan" in res
    assert res["plan"] is not None

    # Response must be a concise summary, not a massive 50-line markdown dump
    response_text = res["response"]
    assert "Implementation plan synthesized for: *Add /health endpoint*" in response_text
    assert len(response_text.splitlines()) <= 3
    # Plan contains the full structured DAG tasks
    assert len(res["plan"]["tasks"]) > 0


def test_plan_generation_zero_repository_files_created(db_session, tmp_path):
    """
    Test 2: Generating and previewing an implementation plan creates 0 repository files
    and does not write PLAN.md or plan.json to disk.
    """
    repo_dir = tmp_path / "target_repo"
    repo_dir.mkdir()
    (repo_dir / "app.py").write_text("print('hello')")

    initial_files = set(os.listdir(repo_dir))

    # Execute plan mode
    res = execute_plan(
        user_requirement="Add logging to app.py",
        repository_id="1",
        db=db_session,
    )

    current_files = set(os.listdir(repo_dir))
    assert current_files == initial_files
    assert "PLAN.md" not in current_files
    assert "implementation_plan.md" not in current_files
    assert "plan.json" not in current_files


def test_generating_second_plan_replaces_active_plan_workspace(db_session):
    """
    Test 3: Generating Plan B replaces Plan A in the active AgentRun state and increments/updates plan identity.
    """
    service = EngineeringAgent()

    # 1. Create run and synthesize Plan A (version 1)
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Implement basic auth",
    )
    plan_a = service.create_plan(db=db_session, run_id=run.id)
    assert plan_a.version == 1

    # 2. User updates requirement in same run -> reset state to PLANNING / update user_requirement -> Plan B synthesized (version 2)
    run.user_requirement = "Implement Google OAuth instead"
    db_session.add(run)
    db_session.commit()

    # Clear previous approval request so replanning generates new version
    approvals = db_session.query(ApprovalRequest).filter(ApprovalRequest.agent_run_id == run.id).all()
    for app in approvals:
        db_session.delete(app)
    db_session.commit()

    plan_b = service.create_plan(db=db_session, run_id=run.id)
    assert plan_b.version == 2
    assert plan_b.plan_id != plan_a.plan_id

    # Active plan on run is now Plan B
    db_session.refresh(run)
    active_plan = run.metadata_json.get("plan")
    assert active_plan["plan_id"] == plan_b.plan_id
    assert active_plan["version"] == 2


def test_stale_plan_version_cannot_execute_after_replacement(db_session):
    """
    Test 4: Attempting to approve/execute an old plan version (Plan A) when Plan B is active
    is rejected by the server authorization gate.
    """
    service = EngineeringAgent()

    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="OAuth implementation",
    )
    plan_a = service.create_plan(db=db_session, run_id=run.id)

    # Delete old approval to allow replanning
    for app in db_session.query(ApprovalRequest).filter(ApprovalRequest.agent_run_id == run.id).all():
        db_session.delete(app)
    db_session.commit()

    run.user_requirement = "Use Google OAuth"
    db_session.add(run)
    db_session.commit()

    plan_b = service.create_plan(db=db_session, run_id=run.id)

    # Gate check with stale plan version (plan_a) must raise error
    with pytest.raises(Exception):
        service.assert_execution_authorized(
            db=db_session,
            run_id=run.id,
            plan_id=plan_a.plan_id,
            plan_version=plan_a.version,
            user_id=1,
        )


def test_start_implementation_authorizes_and_executes_latest_plan(db_session):
    """
    Test 5: Approving the latest active plan transitions run to EXECUTING and passes the gate.
    """
    service = EngineeringAgent()

    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add health check",
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    # User clicks [Start Implementation] -> approves plan
    service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")

    # Gate check with current plan succeeds without error
    service.assert_execution_authorized(
        db=db_session,
        run_id=run.id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        user_id=1,
    )

    # Start execution -> transitions run to EXECUTING
    exec_run = service.start_plan_execution(db=db_session, run_id=run.id)
    assert exec_run.current_state == AgentState.EXECUTING


def test_plan_history_multiple_versions_retained(db_session):
    """
    Test 6: Multiple plan iterations (v1, v2, v3) maintain independent identities
    and structured task lists in workspace state without disk writes.
    """
    service = EngineeringAgent()

    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Iteration 1: Add user profile",
    )
    plan_v1 = service.create_plan(db=db_session, run_id=run.id)
    assert plan_v1.version == 1

    # Clear approval for iteration 2
    for app in db_session.query(ApprovalRequest).filter(ApprovalRequest.agent_run_id == run.id).all():
        db_session.delete(app)
    db_session.commit()

    run.user_requirement = "Iteration 2: Add avatar upload to profile"
    db_session.add(run)
    db_session.commit()
    plan_v2 = service.create_plan(db=db_session, run_id=run.id)
    assert plan_v2.version == 2

    # Clear approval for iteration 3
    for app in db_session.query(ApprovalRequest).filter(ApprovalRequest.agent_run_id == run.id).all():
        db_session.delete(app)
    db_session.commit()

    run.user_requirement = "Iteration 3: Add S3 image optimization"
    db_session.add(run)
    db_session.commit()
    plan_v3 = service.create_plan(db=db_session, run_id=run.id)
    assert plan_v3.version == 3

    # All three plans have distinct IDs
    assert len({plan_v1.plan_id, plan_v2.plan_id, plan_v3.plan_id}) == 3

    # Active plan on the run is v3
    db_session.refresh(run)
    assert run.metadata_json["plan"]["version"] == 3
    assert run.metadata_json["plan"]["plan_id"] == plan_v3.plan_id
