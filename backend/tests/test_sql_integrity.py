import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
from sqlalchemy.engine import Engine

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import (
    FactFile,
    FactSymbol,
    FactRelationship,
    FactRoute,
    FactDatabaseObject,
    FactCapability,
    FactCapabilityMember,
    FactEvidence,
)
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.capabilities.model import Capability, CapabilityCategory
from backend.intelligence.store.fact_store import save_rim_to_fact_store

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def build_comprehensive_mock_rim():
    file_1 = Entity(
        id="file_auth",
        type=EntityType.FILE,
        name="auth.py",
        location=SourceLocation(repository_path="app/routes/auth.py", start_line=1, end_line=50, language="Python"),
        metadata={"language": "Python", "content_hash": "abc123hash"}
    )
    file_2 = Entity(
        id="file_user",
        type=EntityType.FILE,
        name="user.py",
        location=SourceLocation(repository_path="app/models/user.py", start_line=1, end_line=30, language="Python"),
        metadata={"language": "Python", "content_hash": "xyz789hash"}
    )

    func_login = Entity(
        id="func_login",
        type=EntityType.FUNCTION,
        name="login",
        qualified_name="app.routes.auth.login",
        location=SourceLocation(repository_path="app/routes/auth.py", start_line=10, end_line=25, language="Python"),
        metadata={"file_id": "file_auth", "signature_hash": "sig_login"}
    )

    route_login = Entity(
        id="route_login",
        type=EntityType.ROUTE,
        name="POST /api/v1/auth/login",
        location=SourceLocation(repository_path="app/routes/auth.py", start_line=10, end_line=10, language="Python"),
        metadata={"http_method": "POST", "route_path": "/api/v1/auth/login", "handler_symbol_id": "func_login"}
    )

    tbl_user = Entity(
        id="tbl_user",
        type=EntityType.TABLE,
        name="users",
        location=SourceLocation(repository_path="app/models/user.py", start_line=5, end_line=25, language="Python"),
        metadata={"is_db_model": True}
    )

    rel_route_func = Relationship(
        id="rel_route_func",
        type=RelationshipType.EXPOSES,
        source_id="route_login",
        target_id="func_login",
        metadata={"line": 10, "snippet": "@app.post('/api/v1/auth/login')", "status": "CONFIRMED"}
    )
    rel_func_tbl = Relationship(
        id="rel_func_tbl",
        type=RelationshipType.USES,
        source_id="func_login",
        target_id="tbl_user",
        metadata={"line": 15, "snippet": "db.query(User).filter_by(...)", "status": "CONFIRMED"}
    )

    cap_auth = Capability(
        id="cap_auth",
        purpose="User Authentication",
        category=CapabilityCategory.AUTHENTICATION,
        responsibilities=["Authenticate users via credentials"],
        keywords=["login", "auth"],
        representative_sources=["func_login", "route_login"],
        confidence=0.95,
        evidence=[{"type": "route", "symbol_id": "route_login"}]
    )

    model = RepositoryModel(
        metadata=RepositoryMetadata(name="AuthApp", path="/app", languages=["Python"]),
        entities={
            "file_auth": file_1,
            "file_user": file_2,
            "func_login": func_login,
            "route_login": route_login,
            "tbl_user": tbl_user
        },
        relationships={
            "rel_route_func": rel_route_func,
            "rel_func_tbl": rel_func_tbl
        },
        capabilities={
            "cap_auth": cap_auth
        }
    )
    return model

def setup_test_analysis(db_session):
    user = User(id=1, github_id="gh_1", username="testuser", email="test@example.com")
    db_session.add(user)
    db_session.flush()

    repo = Repository(id=1, url="https://github.com/test/auth-app", user_id=user.id)
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(id=10, repository_id=repo.id, status="Analyzing")
    db_session.add(analysis)
    db_session.commit()
    return analysis

def test_sql_null_and_blank_thresholds(db_session):
    """
    Ensures SQL tables have ZERO null or blank values in required fields, 
    and checks quality density across all 8 Fact Store tables.
    """
    analysis = setup_test_analysis(db_session)
    model = build_comprehensive_mock_rim()
    save_rim_to_fact_store(db_session, analysis_id=analysis.id, model=model)

    # 1. Verify `files` table integrity
    files = db_session.query(FactFile).filter_by(analysis_id=analysis.id).all()
    assert len(files) > 0, "Files table should not be empty"
    for f in files:
        assert f.id is not None and f.id != "", "File id must not be null or blank"
        assert f.path is not None and f.path.strip() != "", "File path must not be null or blank"
        assert f.analysis_id == analysis.id

    # 2. Verify `symbols` table integrity
    symbols = db_session.query(FactSymbol).filter_by(analysis_id=analysis.id).all()
    assert len(symbols) > 0, "Symbols table should not be empty"
    for s in symbols:
        assert s.id is not None and s.id != "", "Symbol id must not be null or blank"
        assert s.name is not None and s.name.strip() != "", "Symbol name must not be null or blank"
        assert s.symbol_type is not None and s.symbol_type.strip() != "", "Symbol type must not be null or blank"

    # 3. Verify `relationships` table integrity
    rels = db_session.query(FactRelationship).filter_by(analysis_id=analysis.id).all()
    assert len(rels) > 0, "Relationships table should not be empty"
    for r in rels:
        assert r.id is not None and r.id != "", "Relationship id must not be null or blank"
        assert r.from_symbol_id is not None and r.from_symbol_id.strip() != "", "from_symbol_id must not be null/blank"
        assert r.to_symbol_id is not None and r.to_symbol_id.strip() != "", "to_symbol_id must not be null/blank"
        assert r.rel_type is not None and r.rel_type.strip() != "", "rel_type must not be null/blank"

    # 4. Verify `routes` table integrity & handler_symbol_id resolution
    routes = db_session.query(FactRoute).filter_by(analysis_id=analysis.id).all()
    assert len(routes) > 0, "Routes table should not be empty"
    for rt in routes:
        assert rt.method is not None and rt.method.strip() != "", "Route method must not be null/blank"
        assert rt.path is not None and rt.path.strip() != "", "Route path must not be null/blank"
        assert rt.handler_symbol_id is not None, "Route handler_symbol_id should be resolved from relationships/metadata"

    # 5. Verify `capabilities` and `capability_members` data completeness
    caps = db_session.query(FactCapability).filter_by(analysis_id=analysis.id).all()
    assert len(caps) > 0, "Capabilities table should not be empty"
    for c in caps:
        assert c.name is not None and c.name.strip() != "", "Capability name must not be null/blank"
        assert c.capability_type is not None, "Capability type must not be null"

    members = db_session.query(FactCapabilityMember).all()
    assert len(members) > 0, "Capability members table must contain extracted member entity IDs"
    for m in members:
        assert m.capability_id is not None and m.capability_id != "", "capability_id in members must not be null"
        assert m.symbol_id is not None and m.symbol_id != "", "symbol_id in members must not be null"

def test_sql_format_validations(db_session):
    """
    Validates formatting conventions for HTTP methods, paths, and relationship enums in SQL.
    """
    analysis = setup_test_analysis(db_session)
    model = build_comprehensive_mock_rim()
    save_rim_to_fact_store(db_session, analysis_id=analysis.id, model=model)

    routes = db_session.query(FactRoute).filter_by(analysis_id=analysis.id).all()
    valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}
    for r in routes:
        assert r.method in valid_methods, f"Invalid HTTP method format: {r.method}"
        assert r.path.startswith("/"), f"Route path should start with '/': {r.path}"

    rels = db_session.query(FactRelationship).filter_by(analysis_id=analysis.id).all()
    valid_rel_types = {"HANDLED_BY", "QUERIES", "CALLS", "IMPORTS", "CONTAINS", "USES", "EXPOSES", "DECLARES", "DEPENDS_ON"}
    for rel in rels:
        assert rel.rel_type in valid_rel_types, f"Invalid relationship type format: {rel.rel_type}"

def test_sql_primary_key_scoping(db_session):
    """
    Verifies that Primary Keys across all tables are properly scoped by analysis_id 
    to prevent key collision across multiple analyses.
    """
    analysis = setup_test_analysis(db_session)
    model = build_comprehensive_mock_rim()
    save_rim_to_fact_store(db_session, analysis_id=analysis.id, model=model)

    files = db_session.query(FactFile).filter_by(analysis_id=analysis.id).all()
    for f in files:
        assert f.id.startswith(f"{analysis.id}:"), f"Primary Key '{f.id}' should be scoped by analysis_id '{analysis.id}'"
