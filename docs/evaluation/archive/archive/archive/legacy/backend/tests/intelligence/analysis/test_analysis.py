import pytest
from backend.intelligence.analysis.engine.registry import AnalysisRegistry
from backend.intelligence.analysis.engine.analysis_engine import AnalysisEngine
from backend.intelligence.analysis.analyses.dependency.cycles import CircularDependencyAnalysis
from backend.intelligence.analysis.analyses.usage.dead_code import DeadCodeAnalysis
from backend.intelligence.analysis.analyses.flow.call_path import CallPathAnalysis
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.features.model import Feature, FeatureRelationship, FeatureRelationshipType
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.enums import EntityType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.relationship import Relationship, RelationshipType

@pytest.fixture
def mock_rim():
    loc = SourceLocation(repository_path="src/main.py", start_line=1, end_line=10, language="Python")
    
    # Execution View Setup (Routes -> Services -> Repositories)
    ent_route = Entity(id="urn:route:1", type=EntityType.ROUTE, name="LoginRoute", location=loc)
    ent_svc = Entity(id="urn:class:svc", type=EntityType.CLASS, name="AuthService", location=loc)
    ent_repo = Entity(id="urn:class:repo", type=EntityType.CLASS, name="UserRepository", location=loc)
    ent_dead = Entity(id="urn:class:dead", type=EntityType.CLASS, name="UnusedService", location=loc)
    
    rel1 = Relationship(id="rel1", type=RelationshipType.CALLS, source_id="urn:route:1", target_id="urn:class:svc")
    rel2 = Relationship(id="rel2", type=RelationshipType.CALLS, source_id="urn:class:svc", target_id="urn:class:repo")
    
    # Architecture View Setup (Cycles)
    feat1 = Feature(id="feat:1", name="F1", members=[], confidence=1.0, evidence=[])
    feat2 = Feature(id="feat:2", name="F2", members=[], confidence=1.0, evidence=[])
    feat3 = Feature(id="feat:3", name="F3", members=[], confidence=1.0, evidence=[])
    
    frel1 = FeatureRelationship(id="frel1", type=FeatureRelationshipType.DEPENDS_ON, source_id="feat:1", target_id="feat:2")
    frel2 = FeatureRelationship(id="frel2", type=FeatureRelationshipType.DEPENDS_ON, source_id="feat:2", target_id="feat:3")
    frel3 = FeatureRelationship(id="frel3", type=FeatureRelationshipType.DEPENDS_ON, source_id="feat:3", target_id="feat:1") # Cycle!
    
    model = RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test"),
        entities={
            "urn:route:1": ent_route,
            "urn:class:svc": ent_svc,
            "urn:class:repo": ent_repo,
            "urn:class:dead": ent_dead
        },
        relationships={
            "rel1": rel1,
            "rel2": rel2
        },
        patterns={}
    )
    model.features = {
        "feat:1": feat1,
        "feat:2": feat2,
        "feat:3": feat3
    }
    model.feature_relationships = {
        "frel1": frel1,
        "frel2": frel2,
        "frel3": frel3
    }
    return model

def test_circular_dependency(mock_rim):
    analysis = CircularDependencyAnalysis()
    res = analysis.execute(mock_rim)
    
    assert res.metrics["cycle_count"] == 1
    assert res.metrics["max_cycle_length"] == 3
    
    cycle = res.result[0]
    assert "feat:1" in cycle
    assert "feat:2" in cycle
    assert "feat:3" in cycle

def test_dead_code(mock_rim):
    analysis = DeadCodeAnalysis()
    res = analysis.execute(mock_rim)
    
    assert "urn:class:dead" in res.result
    assert "urn:route:1" not in res.result

def test_call_path(mock_rim):
    analysis = CallPathAnalysis()
    res = analysis.execute(mock_rim, options={"start_node": "urn:route:1", "end_node": "urn:class:repo"})
    
    assert len(res.result) == 3
    assert res.result[0] == "urn:route:1"
    assert res.result[1] == "urn:class:svc"
    assert res.result[2] == "urn:class:repo"

def test_engine_registry(mock_rim):
    registry = AnalysisRegistry()
    registry.register(DeadCodeAnalysis)
    
    engine = AnalysisEngine(registry)
    res = engine.execute_analysis("deadcode", mock_rim)
    
    assert res.type == "USAGE_ANALYSIS"
