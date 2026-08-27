"""
Phase 5 Automated Test Suite: IMPLEMENT Mode & Server-Enforced Approval Gate.

Verifies:
  1. Intent.IMPLEMENT triggers repository-aware planning and enters AWAITING_APPROVAL state.
  2. Durable ApprovalRequest is created in PENDING status, bound to exact plan_id and version.
  3. Strict read-only invariant: Zero mutations, zero task executions before explicit approval.
  4. Server-enforced central execution authorization gate blocks:
     - Unapproved runs (PENDING approval)
     - Rejected plans (REJECTED approval)
     - Stale approvals (version mismatch v1 vs v2)
     - Plan ID mismatches
     - Direct execution API bypasses (/runs/{id}/execute)
  5. Valid approval transitions ApprovalRequest -> APPROVED, Plan -> APPROVED, Run -> EXECUTING.
  6. Controlled task execution succeeds only after valid server-verified approval.
  7. Approval idempotency and cancellation safety invariants.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship, FactRoute
from backend.agent.graph.builder import build_agent_graph
from backend.agent.graph.state import AgentGraphState
from backend.agent.intent import Intent
from backend.agent.modes import execute_plan, execute_implement
from backend.agent.planning.contracts import Plan, PlanStatus, PlanTaskStatus
from backend.agent.engineering_agent import EngineeringAgent, EngineeringAgentError
from backend.agent.safety.approval import ApprovalController
from backend.models.implementation import (
    AgentRun,
    AgentRunStatus,
    AgentState,
    AgentEventType,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalActionType,
)


from sqlalchemy.pool import StaticPool

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed User & Repository
    user = User(id=1, github_id="gh123", email="test@example.com", username="testuser")
    session.add(user)
    session.commit()

    repo = Repository(id=1, url="https://github.com/org/repo1", user_id=1)
    session.add(repo)
    session.commit()

    analysis = Analysis(id=101, repository_id=1, status="COMPLETED")
    session.add(analysis)
    session.commit()

    # Seed FactFile and FactSymbol
    f1 = FactFile(id="101:f1", analysis_id=101, path="backend/auth/service.py", size=350, language="python")
    session.add(f1)
    session.commit()

    s1 = FactSymbol(
        id="101:s1",
        analysis_id=101,
        name="AuthService",
        qualified_name="backend.auth.service.AuthService",
        symbol_type="class",
        file_id="101:f1",
        line_start=10,
        line_end=80,
    )
    session.add(s1)
    session.commit()

    yield session
    session.close()


def test_implement_creates_awaiting_approval_and_approval_request(db_session):
    """
    Test 1: Intent.IMPLEMENT creates plan, sets run to AWAITING_APPROVAL,
    and creates a durable ApprovalRequest bound to the plan.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )

    plan = service.create_plan(db=db_session, run_id=run.id)

    db_session.refresh(run)
    assert run.current_state == AgentState.AWAITING_APPROVAL
    assert plan is not None
    assert plan.status == PlanStatus.READY_FOR_APPROVAL
    assert len(plan.tasks) > 0

    # Verify durable ApprovalRequest
    approvals = db_session.query(ApprovalRequest).filter(
        ApprovalRequest.agent_run_id == run.id,
        ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
    ).all()

    assert len(approvals) == 1
    approval = approvals[0]
    assert approval.status == ApprovalStatus.PENDING
    assert approval.requested_operation.get("plan_id") == plan.plan_id
    assert approval.requested_operation.get("version") == plan.version


def test_unapproved_run_execution_blocked_by_central_gate(db_session):
    """
    Test 2: Unapproved run (PENDING approval) cannot execute.
    Central gate throws EngineeringAgentError on start_plan_execution and execute_next_task.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    # Attempting to start execution without approval must raise error
    with pytest.raises(EngineeringAgentError, match="Execution not authorized"):
        service.start_plan_execution(db=db_session, run_id=run.id)

    # Attempting to execute next task without approval must raise error
    with pytest.raises(EngineeringAgentError, match="Run must be in 'EXECUTING' state"):
        service.execute_next_task(db=db_session, run_id=run.id)


def test_plan_rejection_blocks_execution(db_session):
    """
    Test 3: Rejecting a plan marks ApprovalRequest as REJECTED and transitions
    run to CANCELLED. Subsequent execution attempts are blocked.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    # Reject plan
    run = service.reject_plan(db=db_session, run_id=run.id, reason="Scope too large", resolved_by="testuser")

    db_session.refresh(run)
    assert run.current_state == AgentState.CANCELLED

    # Check ApprovalRequest is REJECTED
    approval = db_session.query(ApprovalRequest).filter(
        ApprovalRequest.agent_run_id == run.id,
        ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
    ).first()
    assert approval.status == ApprovalStatus.REJECTED

    # Execution is blocked
    with pytest.raises(EngineeringAgentError):
        service.start_plan_execution(db=db_session, run_id=run.id)


def test_plan_approval_and_execution_lifecycle(db_session):
    """
    Test 4: Full happy path:
    IMPLEMENT -> PLAN -> AWAITING_APPROVAL -> APPROVE -> EXECUTING -> TASK EXECUTION.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    # Approve plan
    run = service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")
    db_session.refresh(run)
    assert run.current_state == AgentState.AWAITING_APPROVAL  # Approval alone does not change run state

    approval = db_session.query(ApprovalRequest).filter(
        ApprovalRequest.agent_run_id == run.id,
        ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
    ).first()
    assert approval.status == ApprovalStatus.APPROVED

    # Start execution
    run = service.start_plan_execution(db=db_session, run_id=run.id)
    db_session.refresh(run)
    assert run.current_state == AgentState.EXECUTING

    # Execute first task
    task, result = service.execute_next_task(db=db_session, run_id=run.id)
    assert task is not None
    assert result is not None
    assert result.success is True


def test_stale_plan_version_invalidation(db_session):
    """
    Test 5: Approving plan v1 does not authorize execution if the plan was updated to v2.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan_v1 = service.create_plan(db=db_session, run_id=run.id)
    assert plan_v1.version == 1

    # Approve v1
    service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")

    # Manually trigger re-planning (transition to PLANNING then synthesize v2)
    service.transition_state(db_session, run.id, to_state=AgentState.PLANNING, reason="User requested revision")
    plan_v2 = service.create_plan(db=db_session, run_id=run.id)
    assert plan_v2.version == 2

    # Verify old v1 approval was marked EXPIRED
    old_approvals = db_session.query(ApprovalRequest).filter(
        ApprovalRequest.agent_run_id == run.id,
        ApprovalRequest.status == ApprovalStatus.EXPIRED,
    ).all()
    assert len(old_approvals) >= 1

    # Attempting to start execution without approving v2 must fail
    with pytest.raises(EngineeringAgentError, match="Execution not authorized"):
        service.start_plan_execution(db=db_session, run_id=run.id)


def test_wrong_plan_id_rejected_by_gate(db_session):
    """
    Test 6: Gate rejects execution if target plan_id differs from active plan.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan = service.create_plan(db=db_session, run_id=run.id)
    service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")

    with pytest.raises(EngineeringAgentError, match="Target plan ID mismatch"):
        service.assert_execution_authorized(db=db_session, run_id=run.id, plan_id="different_plan_id")


def test_langgraph_implement_terminal_pauses_at_awaiting_approval(db_session):
    """
    Test 7: In LangGraph, implement_terminal runs planning and pauses at AWAITING_APPROVAL.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login",
    )

    with patch("backend.agent.graph.builder.SessionLocal", return_value=db_session):
        graph = build_agent_graph(agent_service=service)
        initial_state: AgentGraphState = {
            "run_id": run.id,
            "user_requirement": "Add Google OAuth login",
            "repository_id": "1",
            "intent": Intent.IMPLEMENT.value,
            "intent_confidence": 0.95,
            "intent_reason": "Implementation request",
            "classification_method": "deterministic_keyword",
            "current_state": AgentState.UNDERSTANDING.value,
            "status": "UNDERSTANDING",
            "node_history": ["entry_node", "intent_router_node"],
            "metadata": {},
            "tasks": [],
            "events": [],
            "error": None,
            "retry_count": 0,
            "interrupt_reason": None,
            "plan": None,
            "active_task_id": None,
        }
        res = graph.invoke(initial_state)

    assert "implement_terminal" in res["node_history"]
    assert res["status"] == "AWAITING_APPROVAL"
    assert res["current_state"] == AgentState.AWAITING_APPROVAL.value
    assert "plan" in res["metadata"]
    assert res["metadata"]["plan"] is not None


def test_execute_implement_mode_returns_ready_for_approval(db_session):
    """
    Test 8: execute_implement handler returns structured plan with READY_FOR_APPROVAL status.
    """
    res = execute_implement(
        user_requirement="Add Google OAuth support",
        repository_id="1",
        db=db_session,
    )
    assert res["intent"] == "implement"
    assert res["status"] == "READY_FOR_APPROVAL"
    assert "plan" in res
    assert res["plan"] is not None
    assert res["is_valid"] is True


def test_plan_mode_does_not_create_approval_request(db_session):
    """
    Test 9: Semantic difference: PLAN mode generates a plan for inquiry without creating
    an approval request or requiring user approval.
    """
    res = execute_plan(
        user_requirement="How would I add Google OAuth?",
        repository_id="1",
        db=db_session,
    )
    assert res["intent"] == "plan"
    assert "plan" in res

    # No approval request should exist in database for plan query
    approvals = db_session.query(ApprovalRequest).all()
    assert len(approvals) == 0


def test_cancellation_blocks_execution(db_session):
    """
    Test 10: Cancelling a run in AWAITING_APPROVAL blocks execution.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    # Cancel run
    service.cancel_run(db=db_session, run_id=run.id, reason="User cancelled")
    db_session.refresh(run)
    assert run.current_state == AgentState.CANCELLED

    # Attempting to approve must fail
    with pytest.raises(EngineeringAgentError, match="Run must be in 'AWAITING_APPROVAL' state"):
        service.approve_plan(db=db_session, run_id=run.id)


def test_repository_revision_binding_matches_and_mismatch_safety(db_session):
    """
    Test 11: Repository revision binding invariant:
      - Plan records repository revision snapshot at creation time.
      - Approved plan with same repository revision executes successfully.
      - If repository revision changes before execution, execution is strictly blocked.
      - Replanning creates a new approval context bound to updated revision.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    assert plan.repository_revision is not None
    approval = db_session.query(ApprovalRequest).filter(
        ApprovalRequest.agent_run_id == run.id,
        ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
    ).first()
    assert approval.requested_operation.get("repository_revision") == plan.repository_revision

    # Approve plan
    service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")

    # Case A: Same revision -> Execution authorized
    service.assert_execution_authorized(db=db_session, run_id=run.id)

    # Case B: Repository changes revision to R2 -> Execution blocked
    with patch.object(service, "get_repository_revision", return_value="rev:commit_sha_r2_modified"):
        with pytest.raises(EngineeringAgentError, match="Repository revision mismatch"):
            service.assert_execution_authorized(db=db_session, run_id=run.id)

        with pytest.raises(EngineeringAgentError, match="Repository revision mismatch"):
            service.start_plan_execution(db=db_session, run_id=run.id)


def test_run_ownership_requester_authorization(db_session):
    """
    Test 12: Run Ownership / Requester Authorization invariant:
      - Requester must own the AgentRun to approve, reject, or execute.
      - Unauthorized user B attempts are rejected server-side without state change or mutation.
    """
    service = EngineeringAgent()

    # User A (id=1) creates run
    user_a = db_session.query(User).filter(User.id == 1).first()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
        user_id=user_a.id,
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    # User B (id=2) exists
    user_b = User(id=2, github_id="gh456", email="attacker@example.com", username="attacker")
    db_session.add(user_b)
    db_session.commit()

    # User B attempts approve -> Rejected
    with pytest.raises(EngineeringAgentError, match="Approval not authorized"):
        service.approve_plan(db=db_session, run_id=run.id, resolved_by="attacker", user_id=user_b.id)

    # User B attempts reject -> Rejected
    with pytest.raises(EngineeringAgentError, match="Rejection not authorized"):
        service.reject_plan(db=db_session, run_id=run.id, reason="Malicious reject", resolved_by="attacker", user_id=user_b.id)

    # User B attempts execute -> Rejected
    with pytest.raises(EngineeringAgentError, match="Execution not authorized"):
        service.start_plan_execution(db=db_session, run_id=run.id, user_id=user_b.id)

    # Verify state remains untouched in AWAITING_APPROVAL with PENDING approval
    db_session.refresh(run)
    assert run.current_state == AgentState.AWAITING_APPROVAL
    app_req = db_session.query(ApprovalRequest).filter(ApprovalRequest.agent_run_id == run.id).first()
    assert app_req.status == ApprovalStatus.PENDING


def test_concurrent_and_duplicate_approval_safety(db_session):
    """
    Test 13: Concurrent and Duplicate Approval Safety:
      - Double approval calls return idempotently without duplicate workers or errors.
      - Double execute calls return idempotently.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    # First approval
    run_app1 = service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")
    # Second approval (double click)
    run_app2 = service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")
    assert run_app1.id == run_app2.id

    # Start execution
    run_exec1 = service.start_plan_execution(db=db_session, run_id=run.id)
    assert run_exec1.current_state == AgentState.EXECUTING

    # Second start execution (double click)
    run_exec2 = service.start_plan_execution(db=db_session, run_id=run.id)
    assert run_exec2.current_state == AgentState.EXECUTING

    # Approval while executing is idempotent
    run_app3 = service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")
    assert run_app3.current_state == AgentState.EXECUTING


def test_direct_execute_api_bypass_cases(db_session):
    """
    Test 14: Direct /execute API bypass prevention across full router HTTP path:
      Case A: No approval (PENDING) -> 400 Bad Request
      Case B: Rejected plan -> 400 Bad Request
      Case C: Stale approval (v1 approved, replanned to v2) -> 400 Bad Request
      Case D: Valid approved plan -> 200 OK
      Case E: Unauthorized user -> 403 Forbidden
    """
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.database import get_db
    from backend.dependencies.auth import get_current_user

    service = EngineeringAgent()
    user1 = db_session.query(User).filter(User.id == 1).first()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user1

    client = TestClient(app)

    with patch("backend.routers.agent._background_execute_approved_plan"):
        try:
            # --- Case A: No approval ---
            run_a = service.create_run(db=db_session, repository_id="1", user_requirement="Feature A", user_id=user1.id)
            service.create_plan(db=db_session, run_id=run_a.id)

            resp_a = client.post(f"/api/v1/agent/runs/{run_a.id}/execute")
            assert resp_a.status_code == 400
            assert "Execution not authorized" in resp_a.text

            # --- Case B: Rejected plan ---
            run_b = service.create_run(db=db_session, repository_id="1", user_requirement="Feature B", user_id=user1.id)
            service.create_plan(db=db_session, run_id=run_b.id)
            service.reject_plan(db=db_session, run_id=run_b.id, reason="No", resolved_by="testuser", user_id=user1.id)

            resp_b = client.post(f"/api/v1/agent/runs/{run_b.id}/execute")
            assert resp_b.status_code in (400, 409)

            # --- Case C: Stale approval (v1 approved, replanned to v2) ---
            run_c = service.create_run(db=db_session, repository_id="1", user_requirement="Feature C", user_id=user1.id)
            service.create_plan(db=db_session, run_id=run_c.id)
            service.approve_plan(db=db_session, run_id=run_c.id, resolved_by="testuser", user_id=user1.id)
            service.transition_state(db_session, run_c.id, to_state=AgentState.PLANNING, reason="Replan")
            service.create_plan(db=db_session, run_id=run_c.id)  # v2

            resp_c = client.post(f"/api/v1/agent/runs/{run_c.id}/execute")
            assert resp_c.status_code == 400
            assert "Execution not authorized" in resp_c.text

            # --- Case D: Valid approved plan ---
            run_d = service.create_run(db=db_session, repository_id="1", user_requirement="Feature D", user_id=user1.id)
            service.create_plan(db=db_session, run_id=run_d.id)
            service.approve_plan(db=db_session, run_id=run_d.id, resolved_by="testuser", user_id=user1.id)

            resp_d = client.post(f"/api/v1/agent/runs/{run_d.id}/execute")
            assert resp_d.status_code == 200
            data_d = resp_d.json()
            assert data_d["current_state"] == AgentState.EXECUTING.value

            # --- Case E: Unauthorized user (User 2 attempts to execute User 1's run) ---
            user2 = User(id=2, github_id="gh999", email="other@example.com", username="otheruser")
            db_session.add(user2)
            db_session.commit()

            app.dependency_overrides[get_current_user] = lambda: user2
            resp_e = client.post(f"/api/v1/agent/runs/{run_d.id}/execute")
            assert resp_e.status_code == 403

        finally:
            app.dependency_overrides.clear()


def test_duplicate_approval_request_deduplication(db_session):
    """
    Test 15: Repeated planning requests for the same plan maintain exactly ONE active ApprovalRequest.
    """
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="1",
        user_requirement="Add Google OAuth login support",
    )
    plan1 = service.create_plan(db=db_session, run_id=run.id)
    plan2 = service.create_plan(db=db_session, run_id=run.id)

    assert plan1.plan_id == plan2.plan_id

    pending_approvals = db_session.query(ApprovalRequest).filter(
        ApprovalRequest.agent_run_id == run.id,
        ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
        ApprovalRequest.status == ApprovalStatus.PENDING,
    ).all()

    assert len(pending_approvals) == 1


def test_implement_planning_zero_repository_mutation(db_session, tmp_path):
    """
    Test 16: Proves zero pre-approval repository mutation:
      - Real Git repository initialized with clean working tree.
      - Before planning: records HEAD commit SHA, file hashes, and porcelain status.
      - Runs IMPLEMENT mode planning.
      - After planning: proves HEAD commit, working tree, and file hashes are 100% identical.
      - Proves zero file writes, creations, deletions, or git modifications.
    """
    import subprocess
    import hashlib

    # 1. Initialize real Git repo in tmp_path
    repo_dir = tmp_path / "target_repo"
    repo_dir.mkdir()
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "index.ts").write_text("console.log('hello');\n", encoding="utf-8")
    (repo_dir / "src" / "auth.ts").write_text("export function login() { return true; }\n", encoding="utf-8")

    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

    # Record baseline state before planning
    head_sha_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True).stdout.strip()
    status_before = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True).stdout.strip()
    assert status_before == ""

    def hash_files(root: Path) -> dict[str, str]:
        hashes = {}
        for p in root.rglob("*"):
            if ".git" not in p.parts and p.is_file():
                hashes[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
        return hashes

    file_hashes_before = hash_files(repo_dir)

    # 2. Execute IMPLEMENT planning
    service = EngineeringAgent()
    run = service.create_run(
        db=db_session,
        repository_id="test_repo",
        user_requirement="Add OAuth2 authentication provider to src/auth.ts",
        worktree_path=str(repo_dir),
    )
    plan = service.create_plan(db=db_session, run_id=run.id)

    res_implement = execute_implement(
        user_requirement="Add OAuth2 authentication provider to src/auth.ts",
        repository_id="test_repo",
        agent_run_id=run.id,
        db=db_session,
    )

    # 3. Verify zero repository mutation after planning
    head_sha_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True).stdout.strip()
    status_after = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True).stdout.strip()
    file_hashes_after = hash_files(repo_dir)

    assert head_sha_after == head_sha_before
    assert status_after == ""
    assert file_hashes_after == file_hashes_before

    # Durable database workflow state exists and is in AWAITING_APPROVAL
    db_session.refresh(run)
    assert run.current_state == AgentState.AWAITING_APPROVAL
    app_req = db_session.query(ApprovalRequest).filter(ApprovalRequest.agent_run_id == run.id).first()
    assert app_req is not None
    assert app_req.status == ApprovalStatus.PENDING

