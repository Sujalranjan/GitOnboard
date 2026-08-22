"""
Unit tests for ContextAssembler engine.
"""
import tempfile
from pathlib import Path
import pytest

from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import (
    CompletenessStatus,
    ContextAssemblyRequest,
    ContextBudget,
)
from backend.database import Base, SessionLocal, engine
from backend.models.fact_store import FactCapability, FactFile, FactRoute, FactSymbol


from backend.models.user import User
from backend.models.repository import Analysis, Repository


@pytest.fixture(autouse=True)
def init_db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_context_assembler_basic_flow(init_db):
    db = init_db

    # Seed parent User, Repository, Analysis to satisfy FK constraints
    user = User(id=1, github_id="1", username="testuser", email="test@example.com")
    db.merge(user)
    db.commit()
    repo = Repository(id=1, user_id=1, url="https://github.com/test/repo")
    db.merge(repo)
    db.commit()
    analysis = Analysis(id=1, repository_id=1, status="Completed")
    db.merge(analysis)
    db.commit()

    # Seed sample fact store data
    ff = FactFile(
        id="test:file:auth.py",
        analysis_id=1,
        path="auth.py",
        size=100,
        is_binary=False,
    )
    db.merge(ff)
    db.commit()

    cap = FactCapability(
        id="test:cap:auth",
        analysis_id=1,
        name="Authentication",
        capability_type="AUTH",
        status="ACTIVE",
        evidence_summary="User login and JWT validation",
    )
    sym = FactSymbol(
        id="test:sym:authenticate_user",
        analysis_id=1,
        name="authenticate_user",
        symbol_type="function",
        file_id="test:file:auth.py",
        metadata_json={"signature": "def authenticate_user(username, password)"},
    )

    route = FactRoute(
        id="test:route:login",
        analysis_id=1,
        method="POST",
        path="/api/auth/login",
        handler_symbol_id="test:sym:authenticate_user",
    )
    db.merge(cap)
    db.merge(sym)
    db.merge(route)
    db.commit()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create dummy repo file
        auth_file = Path(tmpdir) / "auth.py"
        auth_file.write_text("def authenticate_user(username, password):\n    return True\n", encoding="utf-8")

        assembler = ContextAssembler()
        req = ContextAssemblyRequest(
            repository_id="test_repo",
            requirement="Add validation to authenticate_user login flow",
            worktree_path=tmpdir,
            analysis_id=1,
        )

        ctx = assembler.assemble(req, db=db)

        assert ctx.repository_id == "test_repo"
        assert len(ctx.evidence) > 0
        assert any("authenticate_user" in s.get("name", "") for s in ctx.relevant_symbols)
        assert ctx.contract.completeness in (CompletenessStatus.COMPLETE, CompletenessStatus.PARTIAL)


def test_context_assembler_unknown_capability_representation(init_db):
    db = init_db
    assembler = ContextAssembler()

    req = ContextAssemblyRequest(
        repository_id="test_repo",
        requirement="Implement quantum blockchain mining algorithm",
    )

    ctx = assembler.assemble(req, db=db)

    # Must explicitly register missing capability in unknowns without hallucination
    assert len(ctx.unknowns) > 0
    assert any("No existing capability found" in u for u in ctx.unknowns)
    assert len(ctx.capabilities) == 0


def test_context_assembler_budget_enforcement(init_db):
    db = init_db
    assembler = ContextAssembler()

    budget = ContextBudget(
        max_files=1,
        max_symbols=2,
        max_routes=1,
    )

    req = ContextAssemblyRequest(
        repository_id="test_repo",
        requirement="Search database symbols",
        context_budget=budget,
    )

    ctx = assembler.assemble(req, db=db)
    assert len(ctx.relevant_files) <= budget.max_files
    assert len(ctx.relevant_symbols) <= budget.max_symbols
    assert len(ctx.relevant_routes) <= budget.max_routes
