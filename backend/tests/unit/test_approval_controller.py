"""
Unit tests for ApprovalController (Phase 9: Human Approval & Safety Control).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.safety.approval import (
    ApprovalController,
    ApprovalInvalidStateError,
    ApprovalNotFoundError,
)
from backend.agent.safety.contracts import PolicyDecision
from backend.database import Base
from backend.models.implementation import (
    AgentRun,
    AgentState,
    ApprovalActionType,
    ApprovalRequest,
    ApprovalStatus,
    PolicyAction,
    PolicyDecisionRecord,
    RiskLevel,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create dummy agent run
    run = AgentRun(
        id="run-appr-1",
        task_id="task-appr-1",
        repository_id="repo-appr-1",
        current_state=AgentState.EXECUTING,
    )
    session.add(run)
    session.commit()

    yield session
    session.close()


def test_create_and_approve_approval_request(db_session):
    controller = ApprovalController()
    req = controller.create_approval_request(
        db=db_session,
        agent_run_id="run-appr-1",
        action_type=ApprovalActionType.TOOL_EXECUTION,
        action_description="Execute destructive git clean",
        risk_level=RiskLevel.HIGH,
        command="git clean -fd",
        reason="Clean untracked files",
    )

    assert req.id is not None
    assert req.status == ApprovalStatus.PENDING
    assert req.action_description == "Execute destructive git clean"
    assert req.command == "git clean -fd"

    # Approve request
    approved_req = controller.approve_request(
        db=db_session, approval_id=req.id, resolved_by="test_reviewer"
    )
    assert approved_req.status == ApprovalStatus.APPROVED
    assert approved_req.resolved_by == "test_reviewer"
    assert approved_req.resolved_at is not None

    # Cannot approve already approved request
    with pytest.raises(ApprovalInvalidStateError):
        controller.approve_request(db=db_session, approval_id=req.id)


def test_create_and_reject_approval_request(db_session):
    controller = ApprovalController()
    req = controller.create_approval_request(
        db=db_session,
        agent_run_id="run-appr-1",
        action_type=ApprovalActionType.TERMINAL_COMMAND,
        action_description="Run database migration",
        risk_level=RiskLevel.CRITICAL,
        command="dropdb test_db",
    )

    assert req.status == ApprovalStatus.PENDING

    # Reject request
    rejected_req = controller.reject_request(
        db=db_session,
        approval_id=req.id,
        reason="Dropping test_db is forbidden in CI",
        resolved_by="security_admin",
    )
    assert rejected_req.status == ApprovalStatus.REJECTED
    assert rejected_req.resolved_by == "security_admin"
    assert rejected_req.rejection_reason == "Dropping test_db is forbidden in CI"

    # Cannot reject already rejected request
    with pytest.raises(ApprovalInvalidStateError):
        controller.reject_request(db=db_session, approval_id=req.id, reason="another reason")


def test_get_pending_approvals(db_session):
    controller = ApprovalController()
    req1 = controller.create_approval_request(
        db=db_session,
        agent_run_id="run-appr-1",
        action_type=ApprovalActionType.TOOL_EXECUTION,
        action_description="Action 1",
        risk_level=RiskLevel.MEDIUM,
    )
    req2 = controller.create_approval_request(
        db=db_session,
        agent_run_id="run-appr-1",
        action_type=ApprovalActionType.GIT_OPERATION,
        action_description="Action 2",
        risk_level=RiskLevel.HIGH,
    )

    pending = controller.get_pending_approvals(db=db_session, agent_run_id="run-appr-1")
    assert len(pending) == 2

    # Approve one
    controller.approve_request(db=db_session, approval_id=req1.id)
    pending_after = controller.get_pending_approvals(db=db_session, agent_run_id="run-appr-1")
    assert len(pending_after) == 1
    assert pending_after[0].id == req2.id


def test_record_policy_decision(db_session):
    controller = ApprovalController()
    decision = PolicyDecision(
        action=PolicyAction.BLOCKED,
        reason="Command contains sudo",
        risk_level=RiskLevel.CRITICAL,
    )
    rec = controller.record_policy_decision(
        db=db_session,
        agent_run_id="run-appr-1",
        tool_name="execute_command",
        decision=decision,
        arguments={"command": "sudo rm -rf /"},
    )
    assert rec.id is not None
    assert rec.decision == PolicyAction.BLOCKED
    assert rec.risk_level == RiskLevel.CRITICAL
    assert rec.tool_name == "execute_command"
