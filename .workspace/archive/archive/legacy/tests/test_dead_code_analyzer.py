import pytest
from unittest.mock import Mock
from analysis.plugins.dead_code_analyzer import DeadCodeAnalyzer
from analysis.models.severity import Severity
from analysis.models.layer import ArchitecturalLayer

def test_dead_code_analyzer_name():
    analyzer = DeadCodeAnalyzer()
    assert analyzer.name == "dead_code_analyzer"

def test_dead_code_detection():
    analyzer = DeadCodeAnalyzer()
    
    mock_repo = Mock()
    mock_entities = Mock()
    mock_relationships = Mock()
    mock_analyses = Mock()
    
    # Files
    mock_f1 = Mock(path="main.py")
    mock_f2 = Mock(path="utils.py")
    mock_f3 = Mock(path="api/routes.py")
    mock_entities.files = {"f1": mock_f1, "f2": mock_f2, "f3": mock_f3}
    
    # Modules
    mock_m1 = Mock(name="main_mod", file_id="f1")
    mock_m1.name = "main"
    mock_m2 = Mock(name="utils_mod", file_id="f2")
    mock_m2.name = "utils"
    mock_m3 = Mock(name="routes_mod", file_id="f3")
    mock_m3.name = "routes"
    mock_entities.modules = {"m1": mock_m1, "m2": mock_m2, "m3": mock_m3}
    
    # Functions
    mock_fn1 = Mock(name="main_func", file_id="f1", module_id="m1")
    mock_fn1.name = "main"
    mock_fn2 = Mock(name="helper", file_id="f2", module_id="m2")
    mock_fn2.name = "helper"
    mock_fn3 = Mock(name="unused_func", file_id="f2", module_id="m2")
    mock_fn3.name = "unused_func"
    mock_fn4 = Mock(name="api_route", file_id="f3", module_id="m3")
    mock_fn4.name = "get_user"
    mock_fn5 = Mock(name="init", file_id="f2", module_id="m2")
    mock_fn5.name = "__init__"
    mock_entities.functions = {
        "fn1": mock_fn1, "fn2": mock_fn2, "fn3": mock_fn3, "fn4": mock_fn4, "fn5": mock_fn5
    }
    
    # Classes
    mock_cls1 = Mock(name="UsedClass", file_id="f2", module_id="m2")
    mock_cls1.name = "UsedClass"
    mock_cls2 = Mock(name="DeadClass", file_id="f2", module_id="m2")
    mock_cls2.name = "DeadClass"
    mock_cls3 = Mock(name="ModelClass", file_id="f3", module_id="m3")
    mock_cls3.name = "ModelClass"
    mock_entities.classes = {
        "cls1": mock_cls1, "cls2": mock_cls2, "cls3": mock_cls3
    }
    
    # Relationships
    mock_relationships.calls = {"fn1": ["fn2"]} # fn1 calls fn2. fn3 is dead.
    mock_relationships.depends_on = {"cls_user": ["cls1"]} # cls1 is used. cls2 is dead.
    # m1 imports m3. m2 is never imported.
    mock_relationships.imports = {"m1": ["m3"]}
    
    # Architecture
    mock_analyses.architecture = {
        "m3": ArchitecturalLayer.CONTROLLER,
        "m1": ArchitecturalLayer.UNKNOWN,
        "m2": ArchitecturalLayer.UTILITY
    }
    
    mock_repo.entities = mock_entities
    mock_repo.relationships = mock_relationships
    mock_repo.analyses = mock_analyses
    
    result = analyzer.analyze(mock_repo)
    
    # We expect:
    # 1. Unused Function: unused_func (fn3)
    # 2. Unused Class: DeadClass (cls2)
    # 3. Unreachable Module: utils_mod (m2)
    
    findings = result.findings
    assert len(findings) == 3
    
    assert any(f.title == "Unused Function: unused_func" for f in findings)
    assert any(f.title == "Unused Class: DeadClass" for f in findings)
    assert any(f.title == "Unreachable Module: utils" for f in findings)
    
    for f in findings:
        assert f.severity == Severity.WARNING
