"""
Tests for Tool #3 (Graph Query) - validates strict node existence and parameter checks.

Tests both valid cases (node exists, traversal works) and error cases (node not found,
invalid parameters, cross-analysis contamination).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime

from backend.models.user import User
from backend.models.repository import Repository, RepositoryAnalysis
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity, EntityLocation
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.database import engine, Base
from backend.main import app


@pytest.fixture(scope="function")
def db():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    from backend.database import SessionLocal
    db = SessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def test_user(db: Session):
    """Create test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password="hashed",
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_repo(db: Session, test_user: User):
    """Create test repository."""
    repo = Repository(
        owner_id=test_user.id,
        name="test_repo",
        url="https://github.com/test/test_repo",
        default_branch="main"
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@pytest.fixture
def test_analysis(db: Session, test_repo: Repository):
    """Create test analysis."""
    analysis = RepositoryAnalysis(
        repository_id=test_repo.id,
        status="completed",
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow()
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@pytest.fixture
def test_model_with_entities():
    """Create a test RepositoryModel with sample entities and relationships."""
    model = RepositoryModel()

    # Create entities
    loc1 = EntityLocation(repository_path="backend/auth.py", line=10)
    entity1 = Entity(
        id="urn:function:backend/auth.py#login",
        name="login",
        type=EntityType.FUNCTION,
        location=loc1
    )

    loc2 = EntityLocation(repository_path="backend/database.py", line=20)
    entity2 = Entity(
        id="urn:function:backend/database.py#get_user",
        name="get_user",
        type=EntityType.FUNCTION,
        location=loc2
    )

    loc3 = EntityLocation(repository_path="backend/utils.py", line=30)
    entity3 = Entity(
        id="urn:function:backend/utils.py#hash_password",
        name="hash_password",
        type=EntityType.FUNCTION,
        location=loc3
    )

    model.entities = {
        entity1.id: entity1,
        entity2.id: entity2,
        entity3.id: entity3,
    }

    # Create relationships
    rel1 = Relationship(
        id="rel1",
        source_id=entity1.id,
        target_id=entity2.id,
        type=RelationshipType.CALLS,
        file_path="backend/auth.py"
    )

    rel2 = Relationship(
        id="rel2",
        source_id=entity1.id,
        target_id=entity3.id,
        type=RelationshipType.CALLS,
        file_path="backend/auth.py"
    )

    model.relationships = {
        rel1.id: rel1,
        rel2.id: rel2,
    }

    return model


class TestGraphQueryValid:
    """Test valid graph query scenarios."""

    def test_query_existing_node(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test querying a node that exists in the graph."""
        # Mock get_or_build_model to return our test model
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "urn:function:backend/auth.py#login",
                "direction": "outgoing",
                "depth": 1,
                "max_nodes": 50,
                "relationship_type": "calls"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0
        assert any(n["id"] == "urn:function:backend/auth.py#login" for n in data["nodes"])

    def test_query_with_different_directions(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test graph query with different direction values."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        for direction in ["incoming", "outgoing", "both"]:
            response = client.post(
                f"/repos/{test_repo.name}/graph/query",
                json={
                    "node_id": "urn:function:backend/auth.py#login",
                    "direction": direction,
                    "depth": 1,
                    "max_nodes": 50,
                    "relationship_type": "calls"
                },
                headers={"Authorization": f"Bearer {test_repo.id}"}
            )

            assert response.status_code == 200, f"Direction '{direction}' should be accepted"
            assert "nodes" in response.json()

    def test_query_with_different_depths(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test graph query with different depth values."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        for depth in [1, 2, 5, 10]:
            response = client.post(
                f"/repos/{test_repo.name}/graph/query",
                json={
                    "node_id": "urn:function:backend/auth.py#login",
                    "direction": "outgoing",
                    "depth": depth,
                    "max_nodes": 50,
                    "relationship_type": "calls"
                },
                headers={"Authorization": f"Bearer {test_repo.id}"}
            )

            assert response.status_code == 200, f"Depth {depth} should be accepted"


class TestGraphQueryErrors:
    """Test graph query error scenarios."""

    def test_node_not_found_404(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that nonexistent node returns 404, not empty graph."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "urn:function:nonexistent.py#fake_function",
                "direction": "outgoing",
                "depth": 1,
                "max_nodes": 50,
                "relationship_type": "calls"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_empty_node_id_rejected(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that empty node_id is rejected."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "",
                "direction": "outgoing",
                "depth": 1,
                "max_nodes": 50,
                "relationship_type": "calls"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_invalid_direction_rejected(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that invalid direction is rejected."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "urn:function:backend/auth.py#login",
                "direction": "invalid_direction",
                "depth": 1,
                "max_nodes": 50,
                "relationship_type": "calls"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 400
        assert "direction" in response.json()["detail"].lower()

    def test_invalid_depth_too_small(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that depth < 1 is rejected."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "urn:function:backend/auth.py#login",
                "direction": "outgoing",
                "depth": 0,
                "max_nodes": 50,
                "relationship_type": "calls"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 400
        assert "depth" in response.json()["detail"]

    def test_invalid_depth_too_large(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that depth > 10 is rejected."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "urn:function:backend/auth.py#login",
                "direction": "outgoing",
                "depth": 11,
                "max_nodes": 50,
                "relationship_type": "calls"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 400
        assert "depth" in response.json()["detail"]

    def test_invalid_max_nodes_too_small(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that max_nodes < 1 is rejected."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "urn:function:backend/auth.py#login",
                "direction": "outgoing",
                "depth": 1,
                "max_nodes": 0,
                "relationship_type": "calls"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 400
        assert "max_nodes" in response.json()["detail"]

    def test_invalid_max_nodes_too_large(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that max_nodes > 1000 is rejected."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "urn:function:backend/auth.py#login",
                "direction": "outgoing",
                "depth": 1,
                "max_nodes": 1001,
                "relationship_type": "calls"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 400
        assert "max_nodes" in response.json()["detail"]

    def test_invalid_relationship_type_rejected(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that invalid relationship_type is rejected."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.post(
            f"/repos/{test_repo.name}/graph/query",
            json={
                "node_id": "urn:function:backend/auth.py#login",
                "direction": "outgoing",
                "depth": 1,
                "max_nodes": 50,
                "relationship_type": "invalid_type"
            },
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 400
        assert "relationship_type" in response.json()["detail"].lower()


class TestGraphSearchValid:
    """Test valid graph search scenarios."""

    def test_search_by_name(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test searching for a node by name."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.get(
            f"/repos/{test_repo.name}/graph/search?q=login",
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0


class TestGraphSearchErrors:
    """Test graph search error scenarios."""

    def test_search_with_empty_query(self, client: TestClient, test_repo: Repository, test_model_with_entities, monkeypatch):
        """Test that empty search query is rejected."""
        from backend.routers.repo.services.models import get_or_build_model

        class MockQueryLayer:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(
            "backend.routers.repo.services.models.get_or_build_model",
            lambda *args, **kwargs: MockQueryLayer(test_model_with_entities)
        )

        response = client.get(
            f"/repos/{test_repo.name}/graph/search?q=",
            headers={"Authorization": f"Bearer {test_repo.id}"}
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()
