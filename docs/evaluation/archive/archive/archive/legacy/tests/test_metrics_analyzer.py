import pytest
from unittest.mock import Mock
from analysis.plugins.metrics_analyzer import MetricsAnalyzer
from analysis.models.metrics import RepositoryMetrics

def test_metrics_analyzer_name():
    analyzer = MetricsAnalyzer()
    assert analyzer.name == "metrics_analyzer"

def test_metrics_analyzer_empty_repository():
    analyzer = MetricsAnalyzer()
    mock_repo = Mock()
    mock_repo.entities = None
    
    result = analyzer.analyze(mock_repo)
    assert len(result.findings) == 1
    assert result.findings[0].title == "Missing Entities"

def test_metrics_analyzer_with_entities():
    analyzer = MetricsAnalyzer()
    mock_repo = Mock()
    mock_repo.analyses = None
    
    # Mock entities
    mock_entities = Mock()
    
    # Files
    mock_f1 = Mock(path="test_1.py", size=150, is_python=True)
    mock_f1.name = "test_1.py"
    mock_f2 = Mock(path="main.py", size=450, is_python=True)
    mock_f2.name = "main.py"
    mock_entities.files = {"f1": mock_f1, "f2": mock_f2}
    
    # Modules
    mock_m1 = Mock()
    mock_m1.name = "m1"
    mock_m2 = Mock()
    mock_m2.name = "m2"
    mock_entities.modules = {"m1": mock_m1, "m2": mock_m2}
    
    # Directories, Classes, Methods, Imports
    mock_entities.directories = {"d1": Mock()}
    mock_entities.classes = {"c1": Mock(module_id="m1", docstring="Class doc")}
    mock_entities.methods = {"mth1": Mock(module_id="m1", docstring="")}
    mock_entities.imports = {"i1": Mock()}
    
    # Functions
    mock_fn1 = Mock(name="route_func", module_id="m2", docstring="Func doc")
    mock_fn1.name = "get_route"
    mock_fn2 = Mock(name="helper_func", module_id="m2", docstring="")
    mock_fn2.name = "helper"
    mock_entities.functions = {"fn1": mock_fn1, "fn2": mock_fn2}
    
    mock_repo.entities = mock_entities
    
    result = analyzer.analyze(mock_repo)
    
    metrics = result.metrics
    assert isinstance(metrics, RepositoryMetrics)
    assert metrics.total_files == 2
    assert metrics.total_lines == (150 + 450) // 30  # fallback calculation
    
    c = metrics.custom_metrics
    assert c["total_directories"] == 1
    assert c["total_modules"] == 2
    assert c["total_classes"] == 1
    assert c["total_functions"] == 2
    assert c["total_methods"] == 1
    assert c["total_imports"] == 1
    assert c["total_api_routes"] == 1  # get_route
    
    # Doc coverage: 4 capable (1 class, 2 funcs, 1 method). 2 have docstrings.
    assert c["documentation_coverage_percent"] == 50.0
    
    # Avg functions per module: 2 funcs / 2 modules
    assert c["average_functions_per_module"] == 1.0
    
    # Test coverage: 2 python files, 1 is test
    assert c["test_coverage_approx_percent"] == 50.0
