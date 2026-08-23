"""
Graph integration and safety tests for Intent Routing in LangGraph (Phase 2).

Proves the fundamental safety invariant:
  - Non-mutating requests (CHAT, EXPLORE, EXPLAIN, CLARIFY) NEVER invoke create_plan
  - Only PLAN and IMPLEMENT reach legacy_agent_node
"""
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.graph.builder import build_agent_graph
from backend.agent.graph.engine import AgentGraphOrchestrator
from backend.agent.graph.state import AgentGraphState
from backend.agent.engineering_agent import EngineeringAgent
from backend.agent.intent import IntentRouter
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


def test_greeting_hi_routes_to_chat_terminal_no_create_plan(db_session, monkeypatch):
    """
    Critical Phase 0 Regression Test:
    'hi' must land in chat_terminal and MUST NOT invoke create_plan.
    """
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

    # Asserts exact path
    assert "entry_node" in final_state["node_history"]
    assert "intent_router_node" in final_state["node_history"]
    assert "chat_terminal" in final_state["node_history"]
    assert "legacy_agent_node" not in final_state["node_history"]
    assert final_state["intent"] == "chat"
    assert final_state["current_state"] == AgentState.COMPLETED.value

    # Invariant: create_plan was NEVER called
    mock_service.create_plan.assert_not_called()


def test_explore_routes_to_explore_terminal_no_create_plan(db_session, monkeypatch):
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
    assert "legacy_agent_node" not in final_state["node_history"]
    assert final_state["intent"] == "explore"
    mock_service.create_plan.assert_not_called()


def test_explain_routes_to_explain_terminal_no_create_plan(db_session, monkeypatch):
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
    assert "legacy_agent_node" not in final_state["node_history"]
    assert final_state["intent"] == "explain"
    mock_service.create_plan.assert_not_called()


def test_clarify_routes_to_clarify_terminal_no_create_plan(db_session, monkeypatch):
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
    assert "legacy_agent_node" not in final_state["node_history"]
    assert final_state["intent"] == "clarify"
    mock_service.create_plan.assert_not_called()


def test_implement_routes_to_legacy_agent_node_invokes_create_plan(db_session, monkeypatch):
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    dummy_plan = Plan(
        plan_id="plan-impl-1",
        agent_run_id="run-impl-1",
        repository_id="repo-impl-1",
        requirement="add Google OAuth",
        status=PlanStatus.READY_FOR_APPROVAL,
    )
    mock_service.create_plan.return_value = dummy_plan

    run = AgentRun(
        id="run-impl-1",
        task_id="task-impl-1",
        repository_id="repo-impl-1",
        user_requirement="add Google OAuth",
        current_state=AgentState.AWAITING_APPROVAL,
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
    assert "legacy_agent_node" in final_state["node_history"]
    assert final_state["intent"] == "implement"
    mock_service.create_plan.assert_called_once()
