import pytest
from backend.intelligence.patterns.model import PatternCategory, PatternType
from backend.intelligence.patterns.registry import PatternRegistry
from backend.intelligence.patterns.engine import PatternRecognitionEngine
from backend.intelligence.patterns.matcher import GraphMatcher
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation

@pytest.fixture
def mock_rim():
    loc = SourceLocation(repository_path="src/main.py", start_line=1, end_line=10, language="Python")
    
    ent_route = Entity(id="urn:route:1", type=EntityType.ROUTE, name="GET /users", location=loc)
    ent_ctrl = Entity(id="urn:class:2", type=EntityType.CLASS, name="UserController", location=loc)
    ent_svc = Entity(id="urn:class:3", type=EntityType.CLASS, name="UserService", location=loc)
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
        }
    )

def test_pattern_registry():
    registry = PatternRegistry()
    rules = registry.get_all_rules()
    assert len(rules) >= 3
    assert any(r["name"] == "MVC" for r in rules)

def test_graph_matcher(mock_rim):
    registry = PatternRegistry()
    rule = registry.get_rule("MVC")
    assert rule is not None
    
    matcher = GraphMatcher(mock_rim)
    patterns = matcher.match_rule(rule)
    
    assert len(patterns) == 1
    assert patterns[0].type == PatternType.MVC
    assert len(patterns[0].participants) == 4
    assert len(patterns[0].evidence) == 3

def test_pattern_engine(mock_rim):
    registry = PatternRegistry()
    engine = PatternRecognitionEngine(registry)
    
    model = engine.run(mock_rim)
    assert len(model.patterns) >= 1
    
    mvc_patterns = [p for p in model.patterns.values() if p.type == PatternType.MVC]
    assert len(mvc_patterns) == 1
