"""
Integration Test Suite for Repository Context Assembly (Phase 3).

Tests:
  - Scenario 1: Feature modification ("Add validation to login flow")
  - Scenario 2: Unmatched capability ("Add blockchain mining support") with explicit unknowns
  - Scenario 3: EngineeringAgent.assemble_repository_context execution and event emission
  - Scenario 4: HTTP API endpoint POST /api/v1/agent/runs/{run_id}/context
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.agent.context.contracts import CompletenessStatus
from backend.agent.engineering_agent import EngineeringAgent
from backend.database import Base, SessionLocal, engine
from backend.main import app
from backend.models.fact_store import FactCapability, FactRoute, FactSymbol
from backend.models.implementation import AgentEvent, AgentEventType


@pytest.fixture(autouse=True)
def init_db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_worktree():
    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        # Initialize git repository
        subprocess.run(["git", "init"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=wt_path, capture_output=True, check=True)
        
        # Add pyproject.toml
        (wt_path / "pyproject.toml").write_text('[project]\nname = "demo-app"\nversion = "0.1.0"\n', encoding="utf-8")
        
        # Add auth service and routes
        auth_dir = wt_path / "app"
        auth_dir.mkdir(parents=True, exist_ok=True)
        (auth_dir / "auth.py").write_text(
            "def login_user(username, password):\n"
            "    '''Authenticate user credentials'''\n"
            "    if not username: return False\n"
            "    return True\n",
            encoding="utf-8",
        )
        
        subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=wt_path, capture_output=True, check=True)
        
        yield str(wt_path)


def test_scenario_existing_feature_modification(init_db, sample_worktree):
    db = init_db

    # Seed Fact Store
    sym = FactSymbol(
        id="demo:sym:login_user",
        analysis_id=1,
        name="login_user",
        symbol_type="function",
        file_id="demo:file:app/auth.py",
        metadata_json={"signature": "def login_user(username, password)"},
    )

    cap = FactCapability(
        id="demo:cap:auth",
        analysis_id=1,
        name="Authentication",
        capability_type="AUTH",
        status="ACTIVE",
        evidence_summary="User login function in app/auth.py",
    )
    db.merge(sym)
    db.merge(cap)
    db.commit()

    agent = EngineeringAgent()
    run = agent.create_run(
        db,
        repository_id="demo-app",
        user_requirement="Add password complexity validation to login_user function",
    )
    run.worktree_path = sample_worktree
    db.add(run)
    db.commit()

    ctx = agent.assemble_repository_context(db, run_id=run.id)

    assert ctx.repository_id == "demo-app"
    assert len(ctx.evidence) > 0
    assert any("login_user" in s.get("name", "") for s in ctx.relevant_symbols) or len(ctx.relevant_files) > 0

    # Verify event emission
    events = db.query(AgentEvent).filter(AgentEvent.agent_run_id == run.id).all()
    event_types = [e.event_type for e in events]
    assert AgentEventType.CONTEXT_ASSEMBLY_STARTED in event_types
    assert AgentEventType.CONTEXT_ASSEMBLY_COMPLETED in event_types

    # Verify bounded summary persisted in metadata_json
    assert "repository_context" in run.metadata_json
    assert run.metadata_json["repository_context"]["version"] == "v1"


def test_scenario_unmatched_capability_unknowns(init_db, sample_worktree):
    db = init_db
    agent = EngineeringAgent()
    run = agent.create_run(
        db,
        repository_id="demo-app",
        user_requirement="Add blockchain mining support and proof of work verification",
    )
    run.worktree_path = sample_worktree
    db.add(run)
    db.commit()

    ctx = agent.assemble_repository_context(db, run_id=run.id)

    # Must NOT hallucinate non-existent capability
    assert len(ctx.capabilities) == 0
    assert len(ctx.unknowns) > 0
    assert any("No existing capability found" in u for u in ctx.unknowns)


def test_context_assembly_http_endpoint(client: TestClient, init_db, sample_worktree):
    db = init_db
    agent = EngineeringAgent()
    run = agent.create_run(
        db,
        repository_id="demo-app",
        user_requirement="Inspect repository dependencies and files",
    )
    run.worktree_path = sample_worktree
    db.add(run)
    db.commit()

    res = client.post(f"/api/v1/agent/runs/{run.id}/context")
    assert res.status_code == 200
    data = res.json()

    assert data["version"] == "v1"
    assert data["repository_id"] == "demo-app"
    assert "contract" in data
    assert "evidence" in data
    assert len(data["evidence"]) > 0
