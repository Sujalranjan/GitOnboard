import pytest
import json
from unittest.mock import MagicMock
from backend.intelligence.visualization.engine.registry import PerspectiveRegistry
from backend.intelligence.visualization.engine.visualization_engine import VisualizationEngine
from backend.intelligence.visualization.perspectives.feature import FeaturePerspective
from backend.intelligence.visualization.perspectives.architecture import ArchitecturePerspective
from backend.intelligence.visualization.perspectives.execution import ExecutionPerspective
from backend.intelligence.visualization.export.json_exporter import JsonExporter
from backend.intelligence.visualization.export.mermaid_exporter import MermaidExporter
from backend.intelligence.visualization.model.visual_model import VisualGraph, VisualNode, VisualEdge
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.features.model import Feature, FeatureRelationship, FeatureRelationshipType
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.enums import EntityType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.query.api.base import RepositoryAPI
from backend.intelligence.query.model.result import QueryResult

@pytest.fixture
def mock_api():
    loc = SourceLocation(repository_path="src/main.py", start_line=1, end_line=10, language="Python")
    ent = Entity(id="urn:route:1", type=EntityType.ROUTE, name="LoginRoute", location=loc)
    feat = Feature(id="feat:1", name="Auth", members=[], confidence=1.0, evidence=[])
    
    model = RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test"),
        entities={"urn:route:1": ent},
        relationships={},
        patterns={}
    )
    model.features = {"feat:1": feat}
    model.feature_relationships = {}
    
    api = MagicMock()
    api.engine.model = model
    
    mock_result = QueryResult(type="FEATURE", result=feat, evidence=[], confidence=1.0)
    api.engine.executor.execute.return_value = mock_result
    
    # Mock analysis result
    api.engine.analysis.execute_analysis.return_value = MagicMock(result=[["feat:1"]])
    return api

def test_feature_perspective(mock_api):
    perspective = FeaturePerspective()
    graph = perspective.build(mock_api, "Auth")
    
    assert len(graph.nodes) == 1
    assert graph.nodes[0].id == "feat:1"
    assert graph.nodes[0].label == "Auth"

def test_architecture_perspective(mock_api):
    perspective = ArchitecturePerspective()
    graph = perspective.build(mock_api)
    
    assert len(graph.nodes) == 1
    assert graph.nodes[0].id == "feat:1"

def test_execution_perspective(mock_api):
    perspective = ExecutionPerspective()
    graph = perspective.build(mock_api, "urn:route:1")
    
    assert len(graph.nodes) == 1
    assert graph.nodes[0].id == "urn:route:1"

def test_exporters():
    graph = VisualGraph(
        nodes=[VisualNode(id="n1", label="Node 1", type="feature")],
        edges=[VisualEdge(source="n1", target="n1", label="self", style="solid")]
    )
    
    json_out = JsonExporter().export(graph)
    data = json.loads(json_out)
    assert len(data["nodes"]) == 1
    
    mermaid_out = MermaidExporter().export(graph)
    assert "graph TD" in mermaid_out
    assert 'n1["Node 1"]' in mermaid_out
