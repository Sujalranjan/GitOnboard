import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.fact_store import (
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
from backend.intelligence.capabilities.engine import CapabilityBuilderEngine
from backend.intelligence.capabilities.model import CapabilityCategory, CapabilityMemberRole
from backend.intelligence.store.fact_store import save_rim_to_fact_store

from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def build_auth_mock_rim():
    loc = SourceLocation(repository_path="app/auth.py", start_line=1, end_line=50, language="Python")
    
    file_ent = Entity(id="f_auth", type=EntityType.FILE, name="auth.py", location=loc)
    route_ent = Entity(id="r_login", type=EntityType.ROUTE, name="POST /login", location=loc, metadata={"route_path": "/login", "http_method": "POST", "handler_symbol_id": "fn_login"})
    handler_ent = Entity(id="fn_login", type=EntityType.FUNCTION, name="login", location=loc)
    verifier_ent = Entity(id="fn_verify", type=EntityType.FUNCTION, name="verify_password", location=loc)
    table_ent = Entity(id="tbl_user", type=EntityType.TABLE, name="users", location=loc, metadata={"is_db_model": True})

    rel_handled = Relationship(id="rel1", type=RelationshipType.HANDLED_BY, source_id="r_login", target_id="fn_login")
    rel_calls = Relationship(id="rel2", type=RelationshipType.CALLS, source_id="fn_login", target_id="fn_verify")
    rel_queries = Relationship(id="rel3", type=RelationshipType.USES, source_id="fn_login", target_id="tbl_user")

    return RepositoryModel(
        metadata=RepositoryMetadata(name="AuthRepo", path="/auth", languages=["Python"]),
        entities={
            "f_auth": file_ent,
            "r_login": route_ent,
            "fn_login": handler_ent,
            "fn_verify": verifier_ent,
            "tbl_user": table_ent,
        },
        relationships={
            "rel1": rel_handled,
            "rel2": rel_calls,
            "rel3": rel_queries,
        }
    )

def test_authentication_detection_positive():
    rim = build_auth_mock_rim()
    engine = CapabilityBuilderEngine()
    model = engine.run(rim)

    assert len(model.capabilities) >= 1
    auth_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.AUTHENTICATION]
    assert len(auth_caps) == 1
    
    cap = auth_caps[0]
    assert cap.rule_id == "AUTH_CREDENTIAL_LOGIN"
    assert "r_login" in cap.representative_sources
    assert "fn_login" in cap.representative_sources

def test_authentication_false_positive_negative():
    loc = SourceLocation(repository_path="app/util.py", start_line=1, end_line=10, language="Python")
    file_ent = Entity(id="f_util", type=EntityType.FILE, name="util.py", location=loc)
    jwt_decode = Entity(id="fn_decode", type=EntityType.FUNCTION, name="jwt_decode", location=loc)

    rim = RepositoryModel(
        metadata=RepositoryMetadata(name="UtilRepo", path="/util", languages=["Python"]),
        entities={"f_util": file_ent, "fn_decode": jwt_decode},
        relationships={}
    )

    engine = CapabilityBuilderEngine()
    model = engine.run(rim)
    auth_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.AUTHENTICATION]
    assert len(auth_caps) == 0

def test_crud_resource_detection_positive():
    loc = SourceLocation(repository_path="app/users.py", start_line=1, end_line=100, language="Python")
    
    file_ent = Entity(id="f_users", type=EntityType.FILE, name="users.py", location=loc)
    r_post = Entity(id="r_create", type=EntityType.ROUTE, name="POST /users", location=loc, metadata={"route_path": "/users", "http_method": "POST", "handler_symbol_id": "fn_create"})
    r_get = Entity(id="r_read", type=EntityType.ROUTE, name="GET /users", location=loc, metadata={"route_path": "/users", "http_method": "GET", "handler_symbol_id": "fn_read"})
    fn_create = Entity(id="fn_create", type=EntityType.FUNCTION, name="create_user", location=loc)
    fn_read = Entity(id="fn_read", type=EntityType.FUNCTION, name="get_users", location=loc)
    tbl_user = Entity(id="tbl_user", type=EntityType.TABLE, name="UserModel", location=loc, metadata={"is_db_model": True})

    rel1 = Relationship(id="rel1", type=RelationshipType.HANDLED_BY, source_id="r_create", target_id="fn_create")
    rel2 = Relationship(id="rel2", type=RelationshipType.HANDLED_BY, source_id="r_read", target_id="fn_read")
    rel3 = Relationship(id="rel3", type=RelationshipType.USES, source_id="fn_create", target_id="tbl_user")
    rel4 = Relationship(id="rel4", type=RelationshipType.USES, source_id="fn_read", target_id="tbl_user")

    rim = RepositoryModel(
        metadata=RepositoryMetadata(name="CRUDRepo", path="/crud", languages=["Python"]),
        entities={
            "f_users": file_ent,
            "r_create": r_post,
            "r_read": r_get,
            "fn_create": fn_create,
            "fn_read": fn_read,
            "tbl_user": tbl_user,
        },
        relationships={"rel1": rel1, "rel2": rel2, "rel3": rel3, "rel4": rel4}
    )

    engine = CapabilityBuilderEngine()
    model = engine.run(rim)

    crud_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.CRUD]
    assert len(crud_caps) == 1
    assert "User" in crud_caps[0].purpose

def test_crud_health_exclusion_negative():
    loc = SourceLocation(repository_path="app/main.py", start_line=1, end_line=10, language="Python")
    r_health = Entity(id="r_health", type=EntityType.ROUTE, name="GET /health", location=loc, metadata={"route_path": "/health", "http_method": "GET"})
    
    rim = RepositoryModel(
        metadata=RepositoryMetadata(name="HealthRepo", path="/health", languages=["Python"]),
        entities={"r_health": r_health},
        relationships={}
    )

    engine = CapabilityBuilderEngine()
    model = engine.run(rim)
    crud_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.CRUD]
    assert len(crud_caps) == 0

def test_background_tasks_detection_positive():
    loc = SourceLocation(repository_path="app/tasks.py", start_line=1, end_line=40, language="Python")
    bg_func = Entity(id="fn_bg", type=EntityType.FUNCTION, name="send_welcome_email", location=loc, metadata={"parameters": ["BackgroundTasks"]})

    rim = RepositoryModel(
        metadata=RepositoryMetadata(name="BGRepo", path="/bg", languages=["Python"]),
        entities={"fn_bg": bg_func},
        relationships={}
    )

    engine = CapabilityBuilderEngine()
    model = engine.run(rim)

    bg_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.BACKGROUND_TASKS]
    assert len(bg_caps) == 1
    assert bg_caps[0].rule_id == "BACKGROUND_FASTAPI_TASK"

def test_async_def_false_positive_negative():
    loc = SourceLocation(repository_path="app/async_util.py", start_line=1, end_line=15, language="Python")
    async_fn = Entity(id="fn_fetch", type=EntityType.FUNCTION, name="fetch_external_data", location=loc, metadata={"parameters": ["url: str"]})

    rim = RepositoryModel(
        metadata=RepositoryMetadata(name="AsyncRepo", path="/async", languages=["Python"]),
        entities={"fn_fetch": async_fn},
        relationships={}
    )

    engine = CapabilityBuilderEngine()
    model = engine.run(rim)
    bg_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.BACKGROUND_TASKS]
    assert len(bg_caps) == 0

def test_file_upload_detection_positive():
    loc = SourceLocation(repository_path="app/upload.py", start_line=1, end_line=30, language="Python")
    r_upload = Entity(id="r_upload", type=EntityType.ROUTE, name="POST /upload", location=loc, metadata={"route_path": "/upload", "http_method": "POST", "handler_symbol_id": "fn_upload"})
    fn_upload = Entity(id="fn_upload", type=EntityType.FUNCTION, name="upload_avatar", location=loc, metadata={"parameters": ["file: UploadFile"]})

    rel = Relationship(id="rel1", type=RelationshipType.HANDLED_BY, source_id="r_upload", target_id="fn_upload")

    rim = RepositoryModel(
        metadata=RepositoryMetadata(name="UploadRepo", path="/upload", languages=["Python"]),
        entities={"r_upload": r_upload, "fn_upload": fn_upload},
        relationships={"rel1": rel}
    )

    engine = CapabilityBuilderEngine()
    model = engine.run(rim)

    upload_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.FILE_UPLOAD]
    assert len(upload_caps) == 1
    assert upload_caps[0].rule_id == "FILE_UPLOAD_UPLOADFILE"

def test_internal_file_write_negative():
    loc = SourceLocation(repository_path="app/log.py", start_line=1, end_line=10, language="Python")
    fn_write = Entity(id="fn_log", type=EntityType.FUNCTION, name="write_log", location=loc, metadata={"parameters": ["msg: str"]})

    rim = RepositoryModel(
        metadata=RepositoryMetadata(name="LogRepo", path="/log", languages=["Python"]),
        entities={"fn_log": fn_write},
        relationships={}
    )

    engine = CapabilityBuilderEngine()
    model = engine.run(rim)
    upload_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.FILE_UPLOAD]
    assert len(upload_caps) == 0

def test_capability_builder_idempotence():
    rim = build_auth_mock_rim()
    engine = CapabilityBuilderEngine()

    res1 = engine.run(rim)
    caps1 = {k: (v.purpose, v.category, v.representative_sources) for k, v in res1.capabilities.items()}

    res2 = engine.run(rim)
    caps2 = {k: (v.purpose, v.category, v.representative_sources) for k, v in res2.capabilities.items()}

    assert caps1 == caps2

def test_fact_store_capability_persistence(db_session):
    rim = build_auth_mock_rim()
    engine = CapabilityBuilderEngine()
    model = engine.run(rim)

    analysis_id = 999
    # Create mock user, repository, and analysis records with flush
    from backend.models.user import User
    from backend.models.repository import Repository, Analysis
    user = User(id=999, github_id="gh_999", username="testuser999", email="test999@example.com")
    db_session.add(user)
    db_session.flush()

    repo = Repository(id=999, url="https://github.com/test/test", default_branch="main", user_id=user.id)
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Analyzing")
    db_session.add(analysis)
    db_session.commit()

    save_rim_to_fact_store(db_session, analysis_id, model)

    db_caps = db_session.query(FactCapability).filter(FactCapability.analysis_id == analysis_id).all()
    assert len(db_caps) >= 1

    db_members = db_session.query(FactCapabilityMember).filter(FactCapabilityMember.capability_id == db_caps[0].id).all()
    assert len(db_members) >= 1
    roles = [m.role for m in db_members]
    assert "entry_point" in roles or "handler" in roles or "table" in roles

    db_ev = db_session.query(FactEvidence).filter(FactEvidence.analysis_id == analysis_id).all()
    assert len(db_ev) >= 1
