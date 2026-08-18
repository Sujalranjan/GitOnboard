from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.main import app
from backend.models.repository import Analysis
import backend.routers.repo.intelligence as intelligence_module
from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.intelligence.features.model import Feature, FeatureMembership, FeatureRelationship, FeatureRelationshipType


def test_feature_discovery_endpoint_returns_sorted_features(monkeypatch):
    feature_a = Feature(
        id="feat:auth",
        name="Authentication",
        description="Login and session handling",
        members=[FeatureMembership(item_id="urn:route:1", item_type="route", confidence=0.92)],
        confidence=0.92,
        evidence=[{"source": "route"}],
    )
    feature_b = Feature(
        id="feat:search",
        name="Search",
        description="Repository search and indexing",
        members=[FeatureMembership(item_id="urn:route:2", item_type="route", confidence=0.81)],
        confidence=0.81,
        evidence=[{"source": "route"}],
    )
    relationship = FeatureRelationship(
        id="frel:1",
        type=FeatureRelationshipType.DEPENDS_ON,
        source_id="feat:auth",
        target_id="feat:search",
    )
    model = SimpleNamespace(features={feature_b.id: feature_b, feature_a.id: feature_a}, feature_relationships={relationship.id: relationship})
    query_layer = SimpleNamespace(model=model)

    monkeypatch.setattr(intelligence_module, "get_or_build_model", lambda repo_name, db, current_user: query_layer)

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username="alice", github_id="1", email="alice@example.com", avatar=None)
    app.dependency_overrides[get_db] = lambda: MagicMock()

    try:
        client = TestClient(app)
        response = client.get("/api/repos/repo/features")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["feature_count"] == 2
    assert payload["relationship_count"] == 1
    assert [feature["name"] for feature in payload["features"]] == ["Authentication", "Search"]
    assert payload["features"][0]["member_count"] == 1
    assert payload["features"][0]["evidence_count"] == 1