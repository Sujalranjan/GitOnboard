import pytest
from backend.intelligence.query.api.base import RepositoryAPI
from backend.intelligence.query.model.query import ActionType, TargetType, ClauseType
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.features.model import Feature, FeatureMembership
from backend.intelligence.patterns.model import Pattern, PatternType
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.enums import EntityType
from backend.intelligence.rim.location import SourceLocation

@pytest.fixture
def mock_rim():
    loc = SourceLocation(repository_path="src/main.py", start_line=1, end_line=10, language="Python")
    ent = Entity(id="urn:class:1", type=EntityType.CLASS, name="AuthController", location=loc)
    
    auth_feature = Feature(
        id="feat:1",
        name="Authentication",
        description="Handles auth",
        members=[
            FeatureMembership(item_id="urn:class:1", item_type="entity", confidence=1.0)
        ],
        confidence=1.0,
        evidence=[]
    )
    
    mvc_pattern = Pattern(
        id="pat:1",
        type=PatternType.MVC,
        participants=["urn:class:1"],
        evidence=[],
        confidence=1.0
    )
    
    model = RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test"),
        entities={"urn:class:1": ent},
        relationships={},
        patterns={"pat:1": mvc_pattern}
    )
    model.features = {"feat:1": auth_feature}
    return model

def test_dsl_parser(mock_rim):
    api = RepositoryAPI(mock_rim)
    
    ast = api.engine.parser.parse("FIND FEATURE Authentication")
    assert ast.action == ActionType.FIND
    assert ast.target_type == TargetType.FEATURE
    assert ast.target_name == "Authentication"
    assert len(ast.clauses) == 0
    
    ast = api.engine.parser.parse("FROM FEATURE Authentication TRACE IMPLEMENTATION")
    assert ast.action == ActionType.FROM
    assert ast.target_type == TargetType.FEATURE
    assert ast.target_name == "Authentication"
    assert len(ast.clauses) == 1
    assert ast.clauses[0].type == ClauseType.TRACE
    assert ast.clauses[0].target == "IMPLEMENTATION"

def test_query_execution(mock_rim):
    api = RepositoryAPI(mock_rim)
    
    res = api.features.find_feature("Authentication")
    assert res.confidence == 1.0
    assert res.result.name == "Authentication"
    
    res = api.features.trace_feature("Authentication")
    assert "implementation" in res.result
    assert "urn:class:1" in res.result["implementation"]
    
    res = api.architecture.find_architecture_pattern("MVC")
    assert res.result.type == PatternType.MVC
