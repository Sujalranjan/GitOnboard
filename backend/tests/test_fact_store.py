import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
from backend.intelligence.store.fact_store import save_rim_to_fact_store, load_rim_from_fact_store

from sqlalchemy import event
from sqlalchemy.engine import Engine

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

def build_mock_rim():
    file_entity = Entity(
        id="file_main_py",
        type=EntityType.FILE,
        name="main.py",
        location=SourceLocation(repository_path="src/main.py", start_line=1, end_line=100, language="Python"),
        metadata={"language": "Python", "content_hash": "abc123hash"},
    )

    func_entity = Entity(
        id="func_login",
        type=EntityType.FUNCTION,
        name="login_user",
        qualified_name="src.main.login_user",
        location=SourceLocation(repository_path="src/main.py", start_line=10, end_line=25, language="Python"),
        metadata={"file_id": "file_main_py"},
    )

    route_entity = Entity(
        id="route_auth_login",
        type=EntityType.ROUTE,
        name="post_login",
        location=SourceLocation(repository_path="src/main.py", start_line=9, end_line=9, language="Python"),
        metadata={"http_method": "POST", "route_path": "/api/login", "handler_symbol_id": "func_login"},
    )

    rel_calls = Relationship(
        id="rel_route_calls_func",
        type=RelationshipType.CALLS,
        source_id="route_auth_login",
        target_id="func_login",
        metadata={"line": 9, "snippet": "@app.post('/api/login')", "status": "CONFIRMED"},
    )

    cap_auth = Capability(
        id="cap_auth_01",
        purpose="User Authentication",
        category=CapabilityCategory.AUTHENTICATION,
        responsibilities=["Handles login token verification"],
        keywords=["login", "auth", "password"],
        representative_sources=["src/main.py"],
        confidence=0.95,
        evidence=[
            {
                "symbol_id": "func_login",
                "role": "entry_point",
                "type": "decorator_match",
                "location": "src/main.py:10",
            }
        ],
    )

    return RepositoryModel(
        metadata=RepositoryMetadata(name="TestRepo", path="/test", languages=["Python"]),
        entities={
            file_entity.id: file_entity,
            func_entity.id: func_entity,
            route_entity.id: route_entity,
        },
        relationships={rel_calls.id: rel_calls},
        capabilities={cap_auth.id: cap_auth},
    )

def test_fact_store_persistence_and_reconstruction(db_session):
    # 1. Create Repository and Analysis records
    user = User(id=1, github_id="gh_1", username="testuser", email="test@example.com")
    db_session.add(user)
    db_session.flush()

    repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(id=1, repository_id=repo.id, status="Analyzing")
    db_session.add(analysis)
    db_session.commit()

    # 2. Save mock RIM to Fact Store
    model = build_mock_rim()
    save_rim_to_fact_store(db_session, analysis_id=1, model=model)

    # 3. Assert facts created in SQL tables
    files_in_db = db_session.query(FactFile).filter_by(analysis_id=1).all()
    symbols_in_db = db_session.query(FactSymbol).filter_by(analysis_id=1).all()
    rels_in_db = db_session.query(FactRelationship).filter_by(analysis_id=1).all()
    routes_in_db = db_session.query(FactRoute).filter_by(analysis_id=1).all()
    caps_in_db = db_session.query(FactCapability).filter_by(analysis_id=1).all()

    assert len(files_in_db) == 1
    assert files_in_db[0].path == "src/main.py"

    assert len(symbols_in_db) == 2
    symbol_names = {s.name for s in symbols_in_db}
    assert "login_user" in symbol_names
    assert "post_login" in symbol_names

    assert len(rels_in_db) == 1
    assert rels_in_db[0].rel_type == "CALLS"
    assert "route_auth_login" in rels_in_db[0].from_symbol_id
    assert "func_login" in rels_in_db[0].to_symbol_id

    assert len(routes_in_db) == 1
    assert routes_in_db[0].method == "POST"
    assert routes_in_db[0].path == "/api/login"

    assert len(caps_in_db) == 1
    assert caps_in_db[0].capability_type == "AUTHENTICATION"

    # 4. Test reconstruction back to RepositoryModel
    reconstructed_model = load_rim_from_fact_store(db_session, analysis_id=1)
    assert "file_main_py" in reconstructed_model.entities
    assert "func_login" in reconstructed_model.entities
    assert "rel_route_calls_func" in reconstructed_model.relationships
    assert "cap_auth_01" in reconstructed_model.capabilities

def test_fact_store_cascade_delete(db_session):
    user = User(id=2, github_id="gh_2", username="testuser2", email="test2@example.com")
    db_session.add(user)
    db_session.flush()

    repo = Repository(id=2, url="https://github.com/test/repo2", user_id=user.id)
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(id=2, repository_id=repo.id, status="Completed")
    db_session.add(analysis)
    db_session.commit()

    model = build_mock_rim()
    save_rim_to_fact_store(db_session, analysis_id=2, model=model)

    # Verify rows exist
    assert db_session.query(FactSymbol).filter_by(analysis_id=2).count() > 0

    # Delete Analysis
    db_session.delete(analysis)
    db_session.commit()

    # Verify facts cleared
    assert db_session.query(FactSymbol).filter_by(analysis_id=2).count() == 0
    assert db_session.query(FactFile).filter_by(analysis_id=2).count() == 0
    assert db_session.query(FactSymbol).filter_by(analysis_id=2).count() == 0
    assert db_session.query(FactRelationship).filter_by(analysis_id=2).count() == 0
