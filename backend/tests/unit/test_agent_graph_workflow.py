"""
Unit and integration tests for LangGraph workflow execution (Phase 1).
"""
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.graph.builder import build_agent_graph
from backend.agent.graph.engine import AgentGraphOrchestrator
from backend.agent.graph.state import AgentGraphState
from backend.agent.engineering_agent import EngineeringAgent
from backend.agent.planning.contracts import Plan, PlanStatus
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


def test_build_agent_graph_structure():
    graph = build_agent_graph()
    assert graph is not None
    # Graph can be invoked
    assert hasattr(graph, "invoke")


def test_nominal_graph_workflow_execution(db_session, monkeypatch):
    # Setup mock agent service
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    dummy_plan = Plan(
        plan_id="plan-123",
        agent_run_id="run-graph-1",
        repository_id="repo-graph-1",
        requirement="Build feature A",
        status=PlanStatus.READY_FOR_APPROVAL,
    )
    mock_service.create_plan.return_value = dummy_plan

    run = AgentRun(
        id="run-graph-1",
        task_id="task-graph-1",
        repository_id="repo-graph-1",
        user_requirement="Build feature A",
        current_state=AgentState.AWAITING_APPROVAL,
        status=AgentRunStatus.RUNNING,
    )
    mock_service.get_run.return_value = run

    # Monkeypatch SessionLocal in builder to return our db_session
    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-graph-1",
        repository_id="repo-graph-1",
        user_requirement="Build feature A",
        current_state="UNDERSTANDING",
        status="QUEUED",
        is_cancelled=False,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    assert "entry_node" in final_state["node_history"]
    assert "legacy_agent_node" in final_state["node_history"]
    assert final_state["current_state"] == AgentState.AWAITING_APPROVAL.value
    mock_service.create_plan.assert_called_once()


def test_graph_workflow_error_handling_observable(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    # Simulate an unhandled exception inside create_plan
    mock_service.create_plan.side_effect = RuntimeError("Context retrieval failure")

    run = AgentRun(
        id="run-graph-err",
        task_id="task-graph-err",
        repository_id="repo-graph-err",
        user_requirement="add fast feature",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.RUNNING,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-graph-err",
        repository_id="repo-graph-err",
        user_requirement="add fast feature",
        current_state="UNDERSTANDING",
        status="RUNNING",
        is_cancelled=False,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    # Asserts that failure was captured observably and marked FAILED without crashing
    assert "legacy_agent_node" in final_state["node_history"]
    assert final_state["current_state"] == AgentState.FAILED.value
    assert "Context retrieval failure" in final_state["error_message"]
    mock_service.transition_state.assert_called_once()


def test_graph_workflow_cancelled_state(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-graph-canc",
        repository_id="repo-graph-canc",
        user_requirement="add cancelled feature",
        current_state="CANCELLED",
        status="CANCELLED",
        is_cancelled=True,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    assert "entry_node" in final_state["node_history"]
    # Service create_plan should NOT be called on cancelled run
    mock_service.create_plan.assert_not_called()


def test_agent_graph_orchestrator_execution(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-orch-1",
        task_id="task-orch-1",
        repository_id="repo-orch-1",
        user_requirement="add orchestration feature",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.QUEUED,
    )
    mock_service.get_run.return_value = run
    mock_service.create_plan.return_value = MagicMock()

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    orchestrator = AgentGraphOrchestrator(agent_service=mock_service)
    final_state = orchestrator.run_graph(run_id="run-orch-1", db=db_session)

    assert final_state["run_id"] == "run-orch-1"
    assert "entry_node" in final_state["node_history"]
    assert "legacy_agent_node" in final_state["node_history"]
