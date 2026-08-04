import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from fastapi.testclient import TestClient

from backend.main import app
from backend.models.repository import Analysis
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.features.model import Feature, FeatureMembership
from backend.routers.repo import intelligence as intelligence_module
from backend.dependencies.auth import get_current_user
from backend.database import get_db


def test_context_builder_endpoint_returns_feature_and_graph_context(monkeypatch):
    location = SourceLocation(repository_path="src/auth.py", start_line=1, end_line=12, language="Python")
    function = Entity(id="urn:function:login", type=EntityType.FUNCTION, name="login_user", location=location)
    klass = Entity(id="urn:class:auth", type=EntityType.CLASS, name="AuthService", location=location)
    relationship = Relationship(id="rel:1", type=RelationshipType.CALLS, source_id=function.id, target_id=klass.id)
    feature = Feature(
        id="feat:auth",
        name="Authentication",
        description="Login and session handling",
        members=[FeatureMembership(item_id=function.id, item_type="entity", confidence=0.9)],
        confidence=0.95,
        evidence=[{"source": "graph"}],
    )

    model = SimpleNamespace(
        entities={function.id: function, klass.id: klass},
        relationships={relationship.id: relationship},
        features={feature.id: feature},
        feature_relationships={},
    )
    query_layer = SimpleNamespace(model=model)

    monkeypatch.setattr(intelligence_module, "get_or_build_model", lambda repo_name, db, current_user: query_layer)

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username="alice", github_id="1", email="alice@example.com", avatar=None)
    app.dependency_overrides[get_db] = lambda: MagicMock()

    try:
        client = TestClient(app)
        response = client.get("/api/repos/repo/context?q=auth")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["context_pack"]
    assert payload["repository"]["feature_count"] == 1
    assert payload["repository"]["symbol_count"] == 2
    assert payload["features"][0]["name"] == "Authentication"
    assert any(symbol["name"] == "login_user" for symbol in payload["matched_symbols"])
    assert len(payload["graph"]["nodes"]) >= 2