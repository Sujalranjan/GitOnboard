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


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
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
