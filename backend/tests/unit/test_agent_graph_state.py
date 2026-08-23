"""
Unit tests for AgentGraphState and synchronization helpers (Phase 1).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.graph.state import (
    AgentGraphState,
    agent_run_to_graph_state,
    sync_graph_state_to_run,
)
from backend.database import Base
from backend.models.implementation import AgentRun, AgentState, AgentRunStatus


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_agent_graph_state_creation():
    state = AgentGraphState(
        run_id="run-test-1",
        repository_id="repo-test",
        user_requirement="Add oauth login",
        current_state="UNDERSTANDING",
        status="QUEUED",
        is_cancelled=False,
        error_message=None,
        node_history=["entry_node"],
        metadata={"custom_key": "custom_val"},
    )

    assert state["run_id"] == "run-test-1"
    assert state["repository_id"] == "repo-test"
    assert state["current_state"] == "UNDERSTANDING"
    assert state["is_cancelled"] is False
    assert state["node_history"] == ["entry_node"]
    assert state["metadata"]["custom_key"] == "custom_val"


def test_agent_run_to_graph_state_conversion(db_session):
    run = AgentRun(
        id="run-test-conv",
        task_id="task-test-conv",
        repository_id="repo-test-conv",
        user_requirement="Implement feature X",
        current_state=AgentState.PLANNING,
        status=AgentRunStatus.RUNNING,
        metadata_json={"budget": 100},
    )
    db_session.add(run)
    db_session.commit()

    state = agent_run_to_graph_state(run)

    assert state["run_id"] == "run-test-conv"
    assert state["repository_id"] == "repo-test-conv"
    assert state["user_requirement"] == "Implement feature X"
    assert state["current_state"] == "PLANNING"
    assert state["status"] == "RUNNING"
    assert state["is_cancelled"] is False
    assert state["node_history"] == []
    assert state["metadata"] == {"budget": 100}


def test_sync_graph_state_to_run(db_session):
    run = AgentRun(
        id="run-test-sync",
        task_id="task-test-sync",
        repository_id="repo-test-sync",
        user_requirement="Test sync",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.QUEUED,
        metadata_json={"initial": True},
    )
    db_session.add(run)
    db_session.commit()

    updated_state = AgentGraphState(
        run_id="run-test-sync",
        error_message="Observed execution error",
        metadata={"graph_run": "completed"},
    )

    synced_run = sync_graph_state_to_run(db_session, "run-test-sync", updated_state)

    assert synced_run.error_message == "Observed execution error"
    assert synced_run.metadata_json["initial"] is True
    assert synced_run.metadata_json["graph_run"] == "completed"
