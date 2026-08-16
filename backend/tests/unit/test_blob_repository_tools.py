import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile
from backend.repository_tools.tools import RepositoryToolLayer
from backend.storage import set_storage
from backend.tests.unit.test_object_storage import InMemoryMockStorage


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_read_file_from_blob_storage_without_local_clone(db_session):
    mock_storage = InMemoryMockStorage()
    set_storage(mock_storage)

    blob_key = "repositories/1/snapshots/snap1/src/auth/service.py"
    sample_code = """# Authentication Service
def login(username, password):
    if username == "admin" and password == "secret":
        return True
    return False

def logout():
    pass
"""
    mock_storage.put_object(blob_key, sample_code)

    user = User(id=1, github_id="gh1", username="dev", email="dev@example.com")
    db_session.add(user)
    db_session.flush()

    repo = Repository(id=1, url="https://github.com/org/auth-repo", user_id=1)
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(id=1, repository_id=1, status="Completed")
    db_session.add(analysis)
    db_session.flush()

    fact_file = FactFile(
        id="1:src/auth/service.py",
        analysis_id=1,
        path="src/auth/service.py",
        language="Python",
        size=len(sample_code),
        blob_name=blob_key,
        snapshot_id="snap1",
        is_binary=False,
    )
    db_session.add(fact_file)
    db_session.commit()

    tool_layer = RepositoryToolLayer(
        repo_name="auth-repo",
        analysis_id=1,
        db=db_session,
        repo_root=None,
    )

    result = tool_layer.read_file("src/auth/service.py", start_line=1, end_line=5)
    assert result["path"] == "src/auth/service.py"
    assert result["start_line"] == 1
    assert result["end_line"] == 5
    assert "login(username, password)" in result["content"]
    assert "   1 | # Authentication Service" in result["content"]

    result_slice = tool_layer.read_file("src/auth/service.py", start_line=7, end_line=8)
    assert "def logout():" in result_slice["raw_text"]


def test_search_code_from_blob_storage(db_session):
    mock_storage = InMemoryMockStorage()
    set_storage(mock_storage)

    user = User(id=1, github_id="gh1", username="dev", email="dev@example.com")
    db_session.add(user)
    db_session.flush()

    repo = Repository(id=1, url="https://github.com/org/auth-repo", user_id=1)
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(id=1, repository_id=1, status="Completed")
    db_session.add(analysis)
    db_session.flush()

    blob_key = "repositories/1/snapshots/snap1/app/routes.py"
    sample_code = """from fastapi import APIRouter
router = APIRouter()

@router.get("/users")
def list_users():
    return [{"id": 1, "name": "Alice"}]
"""
    mock_storage.put_object(blob_key, sample_code)

    fact_file = FactFile(
        id="1:app/routes.py",
        analysis_id=1,
        path="app/routes.py",
        language="Python",
        blob_name=blob_key,
        snapshot_id="snap1",
        is_binary=False,
    )
    db_session.add(fact_file)
    db_session.commit()

    tool_layer = RepositoryToolLayer(
        repo_name="auth-repo",
        analysis_id=1,
        db=db_session,
        repo_root=None,
    )

    matches = tool_layer.search_code("list_users")
    assert len(matches) == 1
    assert matches[0]["file"] == "app/routes.py"
    assert matches[0]["line"] == 5
    assert "def list_users():" in matches[0]["snippet"]
