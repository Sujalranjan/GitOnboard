"""Unit tests for Symbol/Function AI Explanation & Fact Store Caching."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship, FactRoute, FactDatabaseObject
from backend.ai.service import LLMService
from backend.ai.schemas import LLMRequest, LLMResponse, TokenUsage
from backend.routers.repo.symbols import explain_symbol, ExplainSymbolRequest


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    user = User(id=1, github_id="gh_1", username="testuser")
    session.add(user)
    session.flush()

    repo = Repository(
        id=1,
        user_id=1,
        url="https://github.com/testuser/test-repo",
        default_branch="main",
    )
    session.add(repo)
    session.flush()

    analysis = Analysis(
        id=1,
        repository_id=1,
        status="Completed",
    )
    session.add(analysis)
    session.flush()

    # FactFile
    f = FactFile(
        id="1:auth.py",
        analysis_id=1,
        path="auth.py",
        language="python",
    )
    session.add(f)
    session.flush()

    # FactSymbol
    sym = FactSymbol(
        id="1:sym_verify_token",
        analysis_id=1,
        file_id="1:auth.py",
        name="verify_token",
        qualified_name="auth.verify_token",
        symbol_type="function",
        line_start=10,
        line_end=25,
        signature_hash="sig_hash_123",
        metadata_json={
            "signature": "def verify_token(token: str) -> dict:",
            "snippet": "def verify_token(token: str):\n    return jwt.decode(token)",
        },
    )
    session.add(sym)

    # Route
    route = FactRoute(
        id="1:route_login",
        analysis_id=1,
        method="POST",
        path="/api/login",
        handler_symbol_id="1:sym_verify_token",
    )
    session.add(route)

    session.commit()
    yield session
    session.close()


@pytest.fixture
def mock_llm():
    llm = MagicMock(spec=LLMService)
    llm.generate = AsyncMock(return_value=LLMResponse(
        content="### 1. What it does\nDecodes and validates JWT authentication tokens.\n\n### 2. How it works\nParses bearer token header and verifies signature.",
        model="qwen2.5-coder:7b",
        provider="mock",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    ))
    return llm


@pytest.mark.asyncio
async def test_explain_symbol_cache_miss_then_hit(db, mock_llm):
    current_user = db.query(User).filter_by(id=1).first()

    # Call 1: Cache miss -> calls LLM & persists
    req1 = ExplainSymbolRequest(symbol_id="1:sym_verify_token")
    resp1 = await explain_symbol("test-repo", req1, db=db, current_user=current_user, llm=mock_llm)

    assert resp1.name == "verify_token"
    assert resp1.cached is False
    assert "Decodes and validates JWT" in resp1.explanation
    assert mock_llm.generate.call_count == 1

    # Verify cached in database
    sym_db = db.query(FactSymbol).filter_by(id="1:sym_verify_token").first()
    assert sym_db.metadata_json.get("ai_explanation") is not None
    assert sym_db.metadata_json["ai_explanation"]["signature_hash"] == "sig_hash_123"

    # Call 2: Cache hit -> returns cached immediately with 0 LLM calls
    req2 = ExplainSymbolRequest(symbol_id="1:sym_verify_token")
    resp2 = await explain_symbol("test-repo", req2, db=db, current_user=current_user, llm=mock_llm)

    assert resp2.name == "verify_token"
    assert resp2.cached is True
    assert resp2.explanation == resp1.explanation
    # LLM should NOT have been called a second time
    assert mock_llm.generate.call_count == 1


@pytest.mark.asyncio
async def test_explain_symbol_regenerate_forces_llm(db, mock_llm):
    current_user = db.query(User).filter_by(id=1).first()

    # Seed an existing cached explanation
    sym = db.query(FactSymbol).filter_by(id="1:sym_verify_token").first()
    sym.metadata_json = {
        "signature": "def verify_token(token: str) -> dict:",
        "ai_explanation": {
            "summary": "Old outdated explanation",
            "signature_hash": "sig_hash_123",
            "generated_at": "2026-01-01T00:00:00Z"
        }
    }
    db.commit()

    # Request with regenerate=True
    req = ExplainSymbolRequest(symbol_id="1:sym_verify_token", regenerate=True)
    resp = await explain_symbol("test-repo", req, db=db, current_user=current_user, llm=mock_llm)

    assert resp.cached is False
    assert "Decodes and validates JWT" in resp.explanation
    assert mock_llm.generate.call_count == 1


@pytest.mark.asyncio
async def test_explain_symbol_stale_hash_invalidates_cache(db, mock_llm):
    current_user = db.query(User).filter_by(id=1).first()

    # Seed cached explanation with an OLD signature hash
    sym = db.query(FactSymbol).filter_by(id="1:sym_verify_token").first()
    sym.signature_hash = "new_sig_hash_456"  # Current symbol hash is newer
    sym.metadata_json = {
        "signature": "def verify_token(token: str) -> dict:",
        "ai_explanation": {
            "summary": "Old explanation",
            "signature_hash": "old_sig_hash_123",  # Mismatched hash
            "generated_at": "2026-01-01T00:00:00Z"
        }
    }
    db.commit()

    # Call without regenerate=True -> Hash mismatch automatically forces regeneration
    req = ExplainSymbolRequest(symbol_id="1:sym_verify_token", regenerate=False)
    resp = await explain_symbol("test-repo", req, db=db, current_user=current_user, llm=mock_llm)

    assert resp.cached is False
    assert mock_llm.generate.call_count == 1


@pytest.mark.asyncio
async def test_explain_route_resolves_handler(db, mock_llm):
    current_user = db.query(User).filter_by(id=1).first()

    # Request using route path instead of symbol_id
    req = ExplainSymbolRequest(name="POST /api/login", match_type="route")
    resp = await explain_symbol("test-repo", req, db=db, current_user=current_user, llm=mock_llm)

    assert resp.symbol_id == "1:sym_verify_token"
    assert resp.name == "verify_token"
    assert "Decodes and validates JWT" in resp.explanation


@pytest.mark.asyncio
async def test_explain_symbol_extracts_multiline_implementation_when_lines_match_identifier(db, mock_llm):
    """
    Regression Test:
    When an AST extractor produces point line ranges (e.g. line_start=5, line_end=5)
    and unjoined file_ids (e.g. URN encoding), the system must resolve the file path,
    load the storage blob, and extract the full balanced multi-line block to the LLM.
    """
    current_user = db.query(User).filter_by(id=1).first()

    # Create FactFile with full Login component code
    login_full_code = """import React, { useState, useEffect } from 'react';

export const Login = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        await fetch('/api/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });
    };

    return (
        <form onSubmit={handleSubmit}>
            <input value={email} onChange={e => setEmail(e.target.value)} />
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
            <button type="submit">Sign In</button>
        </form>
    );
};
"""
    f = FactFile(
        id="1:src/components/Login.tsx",
        analysis_id=1,
        path="src/components/Login.tsx",
        blob_name="repos/1/src/components/Login.tsx",
        language="tsx"
    )
    db.add(f)
    db.flush()

    # FactSymbol has line_start=3, line_end=3 (just the declaration line)
    # and URN id
    sym_login = FactSymbol(
        id="1:urn:function:src/components/Login.tsx#src.components.Login.Login",
        analysis_id=1,
        file_id="1:src/components/Login.tsx",
        name="Login",
        qualified_name="src.components.Login.Login",
        symbol_type="function",
        line_start=3,
        line_end=3,
        metadata_json={}
    )
    db.add(sym_login)
    db.commit()

    # Mock storage to return the full component code
    from unittest.mock import patch
    mock_storage = MagicMock()
    mock_storage.get_object_text.return_value = login_full_code

    with patch("backend.routers.repo.symbols.get_storage", return_value=mock_storage):
        req = ExplainSymbolRequest(
            symbol_id="1:urn:function:src/components/Login.tsx#src.components.Login.Login",
            regenerate=True
        )
        resp = await explain_symbol("test-repo", req, db=db, current_user=current_user, llm=mock_llm)

    # Verify that mock_llm was called and user prompt received the full multi-line code block
    assert mock_llm.generate.call_count == 1
    call_args = mock_llm.generate.call_args[0][0]
    user_prompt_sent = call_args.messages[1].content

    # The prompt MUST contain the full component implementation, not just line 3
    assert "handleSubmit" in user_prompt_sent
    assert "useState" in user_prompt_sent
    assert "<form onSubmit={handleSubmit}>" in user_prompt_sent
    assert resp.file_path == "src/components/Login.tsx"

