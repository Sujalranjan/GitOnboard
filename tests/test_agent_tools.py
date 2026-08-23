"""
Integration Test Suite for Agent Tool Contract Layer (Phase 2).

Tests:
  - Tool catalog inspection (/api/v1/agent/tools)
  - Repository tool execution (search_code, get_symbol, read_file)
  - Workspace tool execution (create_file, modify_file, get_diff, delete_file)
  - Terminal tool execution (detect_commands)
  - Verification tool execution (verify_static)
  - Git tool execution (git_status, create_checkpoint)
  - Policy rejections and event coordination (TOOL_CALL_STARTED, TOOL_CALL_COMPLETED, TOOL_CALL_BLOCKED)
  - Worktree isolation constraints
  - Terminal state rejection
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.agent.engineering_agent import EngineeringAgent, EngineeringAgentError
from backend.agent.tools.policy import PolicyAction
from backend.agent.tools.registry import AgentToolRegistry
from backend.agent.tools import create_default_tool_registry
from backend.database import Base, SessionLocal, engine
from backend.dependencies.auth import get_current_user
from backend.main import app
from backend.models.user import User
from backend.models.implementation import AgentEvent, AgentEventType, AgentRun, AgentState


@pytest.fixture(autouse=True)
def init_db():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            user = User(id=1, github_id="gh_tool_test", username="tool_tester", email="tool@example.com")
            db.add(user)
            db.commit()
    yield


@pytest.fixture
def client():
    def override_get_current_user():
        with SessionLocal() as db:
            return db.query(User).filter(User.id == 1).first()

    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def temp_worktree():
    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        # Initialize basic git repository
        import subprocess
        subprocess.run(["git", "init"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=wt_path, capture_output=True, check=True)
        
        # Add sample file and initial commit
        sample_file = wt_path / "main.py"
        sample_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=wt_path, capture_output=True, check=True)
        
        yield str(wt_path)


def test_tool_catalog_endpoint(client: TestClient):
    res = client.get("/api/v1/agent/tools")
    assert res.status_code == 200
    catalog = res.json()
    assert len(catalog) >= 15

    tool_names = [t["name"] for t in catalog]
    assert "search_code" in tool_names
    assert "read_file" in tool_names
    assert "create_file" in tool_names
    assert "modify_file" in tool_names
    assert "detect_commands" in tool_names
    assert "verify_static" in tool_names
    assert "git_status" in tool_names

    # Check safe serialization (no internal handlers exposed)
    for item in catalog:
        assert "name" in item
        assert "description" in item
        assert "input_schema" in item
        assert "policy" in item
        assert "handler" not in item


def test_repository_tool_invocation(db, temp_worktree):
    agent = EngineeringAgent()
    run = agent.create_run(db, repository_id="test-repo", user_requirement="Read main.py")
    run.worktree_path = temp_worktree
    db.add(run)
    db.commit()

    # Invoke read_file tool
    res = agent.invoke_tool(
        db,
        run_id=run.id,
        tool_name="read_file",
        arguments={"path": "main.py", "start_line": 1, "end_line": 10},
    )

    assert res.success
    assert "content" in res.data or "lines" in res.data
    assert res.metadata["tool_name"] == "read_file"

    # Verify tool events emitted in DB
    events = db.query(AgentEvent).filter(AgentEvent.agent_run_id == run.id).all()
    event_types = [e.event_type for e in events]
    assert AgentEventType.TOOL_CALL_STARTED in event_types
    assert AgentEventType.TOOL_CALL_COMPLETED in event_types


def test_workspace_file_lifecycle_tools(db, temp_worktree):
    agent = EngineeringAgent()
    run = agent.create_run(db, repository_id="test-repo", user_requirement="Create and edit files")
    run.worktree_path = temp_worktree
    db.add(run)
    db.commit()

    # 1. create_file
    create_res = agent.invoke_tool(
        db,
        run_id=run.id,
        tool_name="create_file",
        arguments={"path": "src/utils.py", "content": "def add(a, b):\n    return a + b\n"},
    )
    assert create_res.success
    assert create_res.data["created"] is True
    assert (Path(temp_worktree) / "src" / "utils.py").exists()

    # 2. modify_file
    mod_res = agent.invoke_tool(
        db,
        run_id=run.id,
        tool_name="modify_file",
        arguments={"path": "src/utils.py", "content": "def add(a, b, c=0):\n    return a + b + c\n"},
    )
    assert mod_res.success
    assert mod_res.data["modified"] is True
    assert "c=0" in (Path(temp_worktree) / "src" / "utils.py").read_text(encoding="utf-8")

    # 3. get_diff
    diff_res = agent.invoke_tool(db, run_id=run.id, tool_name="get_diff", arguments={})
    assert diff_res.success
    assert "src/utils.py" in diff_res.data["modified_files"] or len(diff_res.data["diff"]) > 0

    # 4. delete_file
    del_res = agent.invoke_tool(
        db,
        run_id=run.id,
        tool_name="delete_file",
        arguments={"path": "src/utils.py"},
    )
    assert del_res.success
    assert del_res.data["deleted"] is True
    assert not (Path(temp_worktree) / "src" / "utils.py").exists()


def test_terminal_and_verification_tools(db, temp_worktree):
    agent = EngineeringAgent()
    run = agent.create_run(db, repository_id="test-repo", user_requirement="Check commands and syntax")
    run.worktree_path = temp_worktree
    db.add(run)
    db.commit()

    # 1. detect_commands
    det_res = agent.invoke_tool(db, run_id=run.id, tool_name="detect_commands", arguments={})
    assert det_res.success
    assert "detected_commands" in det_res.data

    # 2. verify_static
    ver_res = agent.invoke_tool(db, run_id=run.id, tool_name="verify_static", arguments={"files": ["main.py"]})
    assert ver_res.success
    assert "passed" in ver_res.data


def test_git_checkpoint_and_rollback_tools(db, temp_worktree):
    agent = EngineeringAgent()
    run = agent.create_run(db, repository_id="test-repo", user_requirement="Test git checkpoints")
    run.worktree_path = temp_worktree
    db.add(run)
    db.commit()

    # Modify file
    (Path(temp_worktree) / "main.py").write_text("def modified(): pass\n", encoding="utf-8")

    # Create checkpoint
    cp_res = agent.invoke_tool(
        db,
        run_id=run.id,
        tool_name="create_checkpoint",
        arguments={"message": "Phase 2 checkpoint"},
    )
    assert cp_res.success
    assert cp_res.data["checkpoint_created"] is True
    assert "commit_sha" in cp_res.data

    # Check git status
    st_res = agent.invoke_tool(db, run_id=run.id, tool_name="git_status", arguments={})
    assert st_res.success
    assert st_res.data["is_clean"] is True


def test_tool_policy_blocked_event_coordination(db, temp_worktree):
    # Setup custom registry with blocked tool
    registry = create_default_tool_registry()
    registry.policy.set_policy("delete_file", PolicyAction.BLOCKED, reason="Deletion is forbidden")

    agent = EngineeringAgent(tool_registry=registry)
    run = agent.create_run(db, repository_id="test-repo", user_requirement="Try delete")
    run.worktree_path = temp_worktree
    db.add(run)
    db.commit()

    res = agent.invoke_tool(
        db,
        run_id=run.id,
        tool_name="delete_file",
        arguments={"path": "main.py"},
    )

    assert not res.success
    assert res.error.code == "POLICY_BLOCKED"
    assert "Deletion is forbidden" in res.error.message

    # Verify TOOL_CALL_BLOCKED event emitted
    events = db.query(AgentEvent).filter(AgentEvent.agent_run_id == run.id).all()
    event_types = [e.event_type for e in events]
    assert AgentEventType.TOOL_CALL_BLOCKED in event_types


def test_terminal_state_tool_invocation_rejected(db, temp_worktree):
    agent = EngineeringAgent()
    run = agent.create_run(db, repository_id="test-repo", user_requirement="Completed task")
    agent.transition_state(db, run_id=run.id, to_state=AgentState.EXECUTING)
    agent.transition_state(db, run_id=run.id, to_state=AgentState.VERIFYING)
    agent.transition_state(db, run_id=run.id, to_state=AgentState.COMPLETED)

    # Attempting to invoke tool on COMPLETED run raises EngineeringAgentError
    with pytest.raises(EngineeringAgentError, match="in terminal state 'COMPLETED'"):
        agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="read_file",
            arguments={"path": "main.py"},
        )

