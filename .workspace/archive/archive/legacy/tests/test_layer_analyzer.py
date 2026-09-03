import pytest
from unittest.mock import Mock
from analysis.plugins.layer_analyzer import LayerAnalyzer, LayerHeuristics
from analysis.models.layer import ArchitecturalLayer

def test_layer_analyzer_name():
    analyzer = LayerAnalyzer()
    assert analyzer.name == "layer_analyzer"

def test_layer_heuristics():
    # Test Controller
    mod = Mock()
    mod.name = "routes"
    assert LayerHeuristics.evaluate(mod, Mock(path=""), [], 1, 0) == ArchitecturalLayer.CONTROLLER
    
    # Test Controller via import
    mod.name = "app"
    assert LayerHeuristics.evaluate(mod, Mock(path=""), ["fastapi"], 1, 0) == ArchitecturalLayer.CONTROLLER
    
    # Test Test
    mod.name = "test_app"
    assert LayerHeuristics.evaluate(mod, Mock(path="tests/app.py"), [], 0, 0) == ArchitecturalLayer.TEST
    
    # Test Model
    mod.name = "models"
    assert LayerHeuristics.evaluate(mod, Mock(path=""), [], 0, 1) == ArchitecturalLayer.MODEL
    
    # Test Repository
    mod.name = "db"
    assert LayerHeuristics.evaluate(mod, Mock(path=""), ["sqlalchemy"], 1, 1) == ArchitecturalLayer.REPOSITORY
    
    # Test Service
    mod.name = "user_service"
    assert LayerHeuristics.evaluate(mod, Mock(path=""), [], 1, 1) == ArchitecturalLayer.SERVICE
    
    # Test Unknown
    mod.name = "main"
    assert LayerHeuristics.evaluate(mod, Mock(path=""), [], 1, 1) == ArchitecturalLayer.UNKNOWN

def test_layer_analyzer_with_entities():
    analyzer = LayerAnalyzer()
    mock_repo = Mock()
    mock_repo.analyses = Mock()
    mock_repo.analysis_status = Mock()
    
    mock_entities = Mock()
    
    # Modules
    mock_m1 = Mock()
    mock_m1.name = "test_api"
    mock_m1.file_id = "f1"
    
    mock_m2 = Mock()
    mock_m2.name = "main"
    mock_m2.file_id = "f2"
    
    mock_entities.modules = {"m1": mock_m1, "m2": mock_m2}
    
    # Files
    mock_f1 = Mock()
    mock_f1.path = "tests/test_api.py"
    mock_f2 = Mock()
    mock_f2.path = "main.py"
    mock_entities.files = {"f1": mock_f1, "f2": mock_f2}
    
    mock_entities.imports = {}
    mock_entities.functions = {}
    mock_entities.classes = {}
    
    mock_repo.entities = mock_entities
    
    result = analyzer.analyze(mock_repo)
    
    layers = result.metadata["layers"]
    assert len(layers) == 2
    
    # m1 should be TEST
    l1 = next(l for l in layers if l.module_id == "m1")
    assert l1.layer == ArchitecturalLayer.TEST
    
    # m2 should be UNKNOWN and produce a finding
    l2 = next(l for l in layers if l.module_id == "m2")
    assert l2.layer == ArchitecturalLayer.UNKNOWN
    
    assert len(result.findings) == 1
    assert result.findings[0].title == "Unknown Architectural Layer for main"
    
    # Check RIM update
    assert hasattr(mock_repo.analyses, "architecture")
    assert mock_repo.analyses.architecture["m1"] == ArchitecturalLayer.TEST
    assert mock_repo.analyses.architecture["m2"] == ArchitecturalLayer.UNKNOWN
    assert mock_repo.analysis_status.architecture is True
