"""
Unit tests for CancellationController (Phase 9: Human Approval & Safety Control).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.safety.cancellation import (
    CancellationController,
    CancellationToken,
    OperationCancelledError,
)
from backend.database import Base
from backend.models.implementation import AgentRun, AgentState


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    run = AgentRun(
        id="run-cancel-1",
        task_id="task-cancel-1",
        repository_id="repo-cancel-1",
        current_state=AgentState.EXECUTING,
    )
    session.add(run)
    session.commit()

    yield session
    session.close()


def test_cancellation_token():
    token = CancellationToken(run_id="run-1")
    assert token.is_cancelled is False
    assert token.reason is None

    # Cancel
    token.cancel(reason="User clicked Stop")
    assert token.is_cancelled is True
    assert token.reason == "User clicked Stop"
    assert token.cancelled_at is not None

    with pytest.raises(OperationCancelledError) as exc_info:
        token.throw_if_cancelled()
    assert "User clicked Stop" in str(exc_info.value)


def test_cancellation_controller_cancel_run(db_session):
    controller = CancellationController()
    token = controller.get_or_create_token("run-cancel-1")
    assert token.is_cancelled is False

    cancelled_run = controller.cancel_run(
        db=db_session, run_id="run-cancel-1", reason="Operator aborted execution"
    )
    assert cancelled_run is not None
    assert cancelled_run.current_state == AgentState.CANCELLED
    assert token.is_cancelled is True

    # Verify run updated in DB
    run = db_session.query(AgentRun).filter(AgentRun.id == "run-cancel-1").first()
    assert run.current_state == AgentState.CANCELLED
    assert run.cancellation_reason == "Operator aborted execution"
    assert run.completed_at is not None

    # Clean up
    CancellationController.unregister_token("run-cancel-1")
    assert CancellationController.get_token("run-cancel-1") is None
