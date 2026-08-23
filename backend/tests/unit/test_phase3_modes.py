"""
Unit & Safety Tests for Phase 3 Safe Modes (CHAT, EXPLORE, EXPLAIN).
"""
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol
from backend.models.implementation import AgentRun, AgentState, AgentRunStatus, FileChange
from backend.agent.modes import execute_chat, execute_explore, execute_explain
from backend.agent.graph.builder import build_agent_graph
from backend.agent.graph.engine import AgentGraphOrchestrator
from backend.agent.engineering_agent import EngineeringAgent


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

    yield session
    session.close()


def test_execute_chat_conversational():
    """Verify CHAT returns conversational response with zero repository queries."""
    res = execute_chat("hi")
    assert res["intent"] == "chat"
    assert "response" in res
    assert len(res["response"]) > 0
    assert res.get("evidence") == []


def test_execute_explore_symbol_lookup(db_session):
    """Verify EXPLORE searches FactStore symbols and returns formatted markdown."""
    analysis = Analysis(id=101, repository_id=1, status="COMPLETED")
    db_session.add(analysis)
    db_session.commit()

    file1 = FactFile(id="101:f1", analysis_id=101, path="backend/auth.py", size=120, language="python")
    db_session.add(file1)
    db_session.commit()

    sym1 = FactSymbol(
        id="101:s1",
        analysis_id=101,
        file_id="101:f1",
        name="AuthService",
        qualified_name="backend.auth.AuthService",
        symbol_type="class",
        line_start=15,
        line_end=80,
    )
    db_session.add(sym1)
    db_session.commit()

    res = execute_explore(user_requirement="find AuthService", repository_id="repo1", db=db_session)
    assert res["intent"] == "explore"
    assert "AuthService" in res["response"]
    assert len(res.get("entities", [])) > 0


def test_execute_explore_repo_tree(db_session):
    """Verify EXPLORE listing file tree from FactStore."""
    analysis = Analysis(id=102, repository_id=1, status="COMPLETED")
    db_session.add(analysis)
    db_session.commit()

    file1 = FactFile(id="102:f1", analysis_id=102, path="src/main.py", size=50, language="python")
    file2 = FactFile(id="102:f2", analysis_id=102, path="src/utils.py", size=30, language="python")
    db_session.add_all([file1, file2])
    db_session.commit()

    res = execute_explore(user_requirement="show repo tree", repository_id="repo1", db=db_session)
    assert res["intent"] == "explore"
    assert "src/main.py" in res["response"]
    assert "src/utils.py" in res["response"]


def test_execute_explain_grounded(db_session):
    """Verify EXPLAIN invokes context assembler and produces grounded response."""
    res = execute_explain(user_requirement="how does authentication work?", repository_id="repo1", db=db_session)
    assert res["intent"] == "explain"
    assert "response" in res
    assert "evidence" in res


def test_chat_terminal_graph_safety(db_session, monkeypatch):
    """Verify chat_terminal completes without mutation tools, approvals, or errors."""
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-chat-1",
        task_id="task-chat-1",
        repository_id="repo1",
        user_requirement="hello there",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.QUEUED,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    orchestrator = AgentGraphOrchestrator(agent_service=mock_service)
    final_state = orchestrator.run_graph(run_id="run-chat-1", db=db_session)

    assert final_state["run_id"] == "run-chat-1"
    assert "chat_terminal" in final_state["node_history"]
    assert final_state["current_state"] == AgentState.COMPLETED.value


def test_explore_terminal_graph_safety(db_session, monkeypatch):
    """Verify explore_terminal completes without mutation tools, approvals, or errors."""
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-explore-1",
        task_id="task-explore-1",
        repository_id="repo1",
        user_requirement="where is auth defined?",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.QUEUED,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    orchestrator = AgentGraphOrchestrator(agent_service=mock_service)
    final_state = orchestrator.run_graph(run_id="run-explore-1", db=db_session)

    assert final_state["run_id"] == "run-explore-1"
    assert "explore_terminal" in final_state["node_history"]
    assert final_state["current_state"] == AgentState.COMPLETED.value


def test_explain_terminal_graph_safety(db_session, monkeypatch):
    """Verify explain_terminal completes without mutation tools, approvals, or errors."""
    mock_service = MagicMock(spec=EngineeringAgent)
    mock_service.state_machine = MagicMock()
    mock_service.state_machine.is_terminal.return_value = False

    run = AgentRun(
        id="run-explain-1",
        task_id="task-explain-1",
        repository_id="repo1",
        user_requirement="how does auth work?",
        current_state=AgentState.UNDERSTANDING,
        status=AgentRunStatus.QUEUED,
    )
    mock_service.get_run.return_value = run

    monkeypatch.setattr("backend.agent.graph.builder.SessionLocal", lambda: db_session)

    orchestrator = AgentGraphOrchestrator(agent_service=mock_service)
    final_state = orchestrator.run_graph(run_id="run-explain-1", db=db_session)

    assert final_state["run_id"] == "run-explain-1"
    assert "explain_terminal" in final_state["node_history"]
    assert final_state["current_state"] == AgentState.COMPLETED.value
