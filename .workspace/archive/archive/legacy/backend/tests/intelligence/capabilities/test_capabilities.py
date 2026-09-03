import pytest
from backend.intelligence.capabilities.model import CapabilityCategory, CapabilityRelationshipType
from backend.intelligence.capabilities.taxonomy import infer_category_and_purpose_from_keywords
from backend.intelligence.capabilities.engine import CapabilityBuilderEngine
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation

def test_taxonomy_inference():
    cat, purp = infer_category_and_purpose_from_keywords(["login", "jwt", "user"])
    assert cat == CapabilityCategory.AUTHENTICATION
    assert purp == "Authenticate User"
    
    cat, purp = infer_category_and_purpose_from_keywords(["save", "repository"])
    assert cat == CapabilityCategory.PERSISTENCE
    assert purp == "Manage Persistence"

@pytest.fixture
def mock_rim():
    loc = SourceLocation(repository_path="src/main.py", start_line=1, end_line=10, language="Python")
    
    ent_route = Entity(id="urn:route:1", type=EntityType.ROUTE, name="POST /login", location=loc)
    ent_ctrl = Entity(id="urn:class:2", type=EntityType.CLASS, name="AuthController", location=loc)
    ent_svc = Entity(id="urn:class:3", type=EntityType.CLASS, name="JwtService", location=loc)
    ent_repo = Entity(id="urn:class:4", type=EntityType.CLASS, name="UserRepository", location=loc)
    
    rel1 = Relationship(id="rel:1", type=RelationshipType.EXPOSES, source_id="urn:route:1", target_id="urn:class:2")
    rel2 = Relationship(id="rel:2", type=RelationshipType.CALLS, source_id="urn:class:2", target_id="urn:class:3")
    rel3 = Relationship(id="rel:3", type=RelationshipType.USES, source_id="urn:class:3", target_id="urn:class:4")
    
    return RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test"),
        entities={
            "urn:route:1": ent_route,
            "urn:class:2": ent_ctrl,
            "urn:class:3": ent_svc,
            "urn:class:4": ent_repo
        },
        relationships={
            "rel:1": rel1,
            "rel:2": rel2,
            "rel:3": rel3
        },
        patterns={}
    )

def test_capability_engine(mock_rim):
    engine = CapabilityBuilderEngine()
    
    model = engine.run(mock_rim)
    assert len(model.capabilities) > 0
    
    # We expect AuthController and JwtService and /login to merge into Authentication
    auth_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.AUTHENTICATION]
    assert len(auth_caps) == 1
    
    auth_cap = auth_caps[0]
    assert "login" in auth_cap.keywords or "jwt" in auth_cap.keywords or "auth" in auth_cap.keywords
    assert len(auth_cap.representative_sources) >= 2 # Should have combined some
    
    # We expect UserRepository to become Persistence
    pers_caps = [c for c in model.capabilities.values() if c.category == CapabilityCategory.PERSISTENCE]
    assert len(pers_caps) == 1
    pers_cap = pers_caps[0]
    
    # Verify semantic relationships
    rels = list(model.capability_relationships.values())
    assert len(rels) >= 1
    
    # Ensure Auth depends on/persists Persistence
    auth_to_pers = [r for r in rels if r.source_id == auth_cap.id and r.target_id == pers_cap.id]
    assert len(auth_to_pers) == 1
    assert auth_to_pers[0].type == CapabilityRelationshipType.PERSISTS
