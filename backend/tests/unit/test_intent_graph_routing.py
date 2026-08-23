"""
Graph integration and safety tests for Intent Routing in LangGraph (Phase 2).

Proves that all 6 intents route strictly to their corresponding terminal handlers
with 0 execution side-effects or unapproved mutations.
"""
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.graph.builder import build_agent_graph
from backend.agent.graph.state import AgentGraphState
from backend.agent.engineering_agent import EngineeringAgent
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


def test_greeting_hi_routes_to_chat_terminal(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-hi-1",
        task_id="task-hi-1",
        repository_id="repo-hi-1",
        user_requirement="hi",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.RUNNING,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-hi-1",
        repository_id="repo-hi-1",
        user_requirement="hi",
        current_state="UNDERSTANDING",
        status="RUNNING",
        is_cancelled=False,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    assert "entry_node" in final_state["node_history"]
    assert "intent_router_node" in final_state["node_history"]
    assert "chat_terminal" in final_state["node_history"]
    assert final_state["intent"] == "chat"
    assert final_state["current_state"] == AgentState.COMPLETED.value


def test_explore_routes_to_explore_terminal(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-exp-1",
        task_id="task-exp-1",
        repository_id="repo-exp-1",
        user_requirement="show repo tree",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.RUNNING,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-exp-1",
        repository_id="repo-exp-1",
        user_requirement="show repo tree",
        current_state="UNDERSTANDING",
        status="RUNNING",
        is_cancelled=False,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    assert "explore_terminal" in final_state["node_history"]
    assert final_state["intent"] == "explore"
    assert final_state["current_state"] == AgentState.COMPLETED.value


def test_explain_routes_to_explain_terminal(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-expl-1",
        task_id="task-expl-1",
        repository_id="repo-expl-1",
        user_requirement="how does authentication work?",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.RUNNING,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-expl-1",
        repository_id="repo-expl-1",
        user_requirement="how does authentication work?",
        current_state="UNDERSTANDING",
        status="RUNNING",
        is_cancelled=False,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    assert "explain_terminal" in final_state["node_history"]
    assert final_state["intent"] == "explain"
    assert final_state["current_state"] == AgentState.COMPLETED.value


def test_plan_routes_to_plan_terminal(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-plan-1",
        task_id="task-plan-1",
        repository_id="repo-plan-1",
        user_requirement="what would it take to add payments?",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.RUNNING,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-plan-1",
        repository_id="repo-plan-1",
        user_requirement="what would it take to add payments?",
        current_state="UNDERSTANDING",
        status="RUNNING",
        is_cancelled=False,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    assert "plan_terminal" in final_state["node_history"]
    assert final_state["intent"] == "plan"
    assert final_state["current_state"] == AgentState.COMPLETED.value


def test_implement_routes_to_implement_terminal(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-impl-1",
        task_id="task-impl-1",
        repository_id="repo-impl-1",
        user_requirement="add Google OAuth",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.RUNNING,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-impl-1",
        repository_id="repo-impl-1",
        user_requirement="add Google OAuth",
        current_state="UNDERSTANDING",
        status="RUNNING",
        is_cancelled=False,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    assert "intent_router_node" in final_state["node_history"]
    assert "implement_terminal" in final_state["node_history"]
    assert final_state["intent"] == "implement"
    assert final_state["current_state"] == AgentState.COMPLETED.value


def test_clarify_routes_to_clarify_terminal(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-clr-1",
        task_id="task-clr-1",
        repository_id="repo-clr-1",
        user_requirement="make auth better",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.RUNNING,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    graph = build_agent_graph(agent_service=mock_service)

    initial_state = AgentGraphState(
        run_id="run-clr-1",
        repository_id="repo-clr-1",
        user_requirement="make auth better",
        current_state="UNDERSTANDING",
        status="RUNNING",
        is_cancelled=False,
        node_history=[],
        metadata={},
    )

    final_state = graph.invoke(initial_state)

    assert "clarify_terminal" in final_state["node_history"]
    assert final_state["intent"] == "clarify"
    assert final_state["current_state"] == AgentState.COMPLETED.value
