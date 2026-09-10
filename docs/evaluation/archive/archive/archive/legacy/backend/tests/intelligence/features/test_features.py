import pytest
from backend.intelligence.features.model import FeatureRelationshipType
from backend.intelligence.features.engine import FeatureReconstructionEngine
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.capabilities.model import Capability, CapabilityCategory, CapabilityRelationship, CapabilityRelationshipType

@pytest.fixture
def mock_rim():
    cap_auth = Capability(
        id="cap:auth1",
        purpose="Authenticate User",
        category=CapabilityCategory.AUTHENTICATION,
        responsibilities=[],
        keywords=["login", "jwt"],
        representative_sources=["urn:route:login", "urn:class:AuthController"],
        confidence=0.9,
        evidence=[]
    )
    
    cap_sess = Capability(
        id="cap:auth2",
        purpose="Manage Session",
        category=CapabilityCategory.AUTHENTICATION,
        responsibilities=[],
        keywords=["session", "jwt"],
        representative_sources=["urn:class:SessionManager"],
        confidence=0.8,
        evidence=[]
    )
    
    cap_db = Capability(
        id="cap:db1",
        purpose="Manage Persistence",
        category=CapabilityCategory.PERSISTENCE,
        responsibilities=[],
        keywords=["database", "repository"],
        representative_sources=["urn:class:UserRepository"],
        confidence=0.9,
        evidence=[]
    )
    
    rel_auth_sess = CapabilityRelationship(
        id="crel:1",
        type=CapabilityRelationshipType.DEPENDS_ON,
        source_id="cap:auth1",
        target_id="cap:auth2"
    )
    
    rel_sess_db = CapabilityRelationship(
        id="crel:2",
        type=CapabilityRelationshipType.PERSISTS,
        source_id="cap:auth2",
        target_id="cap:db1"
    )
    
    model = RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test"),
        entities={},
        relationships={},
        patterns={}
    )
    model.capabilities = {
        "cap:auth1": cap_auth,
        "cap:auth2": cap_sess,
        "cap:db1": cap_db
    }
    model.capability_relationships = {
        "crel:1": rel_auth_sess,
        "crel:2": rel_sess_db
    }
    
    return model

def test_feature_engine(mock_rim):
    engine = FeatureReconstructionEngine()
    
    model = engine.run(mock_rim)
    
    assert len(model.features) > 0
    
    # Check if Authentication clustered together
    auth_features = [f for f in model.features.values() if "Authentication" in f.name]
    assert len(auth_features) >= 1
    
    auth_feat = auth_features[0]
    
    # Should contain cap:auth1 and cap:auth2
    cap_ids = [m.item_id for m in auth_feat.members if m.item_type == "capability"]
    assert "cap:auth1" in cap_ids
    assert "cap:auth2" in cap_ids
    assert "cap:db1" not in cap_ids
    
    # Check relationships
    rels = list(model.feature_relationships.values())
    assert len(rels) > 0
    
    # Should project the PERSISTS relationship into a USES relationship
    feat_rel = [r for r in rels if r.source_id == auth_feat.id][0]
    assert feat_rel.type == FeatureRelationshipType.USES
