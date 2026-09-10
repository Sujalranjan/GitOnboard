import pytest
from unittest.mock import Mock
from analysis.plugins.health_analyzer import HealthAnalyzer
from analysis.models.health import RepositoryHealth
from analysis.models.layer import ArchitecturalLayer
from analysis.models.severity import Severity

def test_health_analyzer_name():
    analyzer = HealthAnalyzer()
    assert analyzer.name == "health_analyzer"

def test_health_analyzer_scoring():
    analyzer = HealthAnalyzer()
    
    mock_repo = Mock()
    mock_analyses = Mock()
    
    # 1. Metrics
    mock_analyses.metrics = {
        "test_coverage_approx_percent": 80.0,
        "documentation_coverage_percent": 90.0,
        "average_functions_per_module": 15.0, # 5 over limit -> 10 penalty
        "largest_files": [{"size": 25000}] # 1 huge file -> 5 penalty
    }
    
    # 2. Architecture
    mock_analyses.architecture = {
        "m1": ArchitecturalLayer.CONTROLLER,
        "m2": ArchitecturalLayer.UNKNOWN # 1 unknown -> 2 penalty
    }
    
    # 3. Cycles
    c1 = Mock()
    c1.severity = Severity.ERROR # 1 error -> 10 penalty
    mock_analyses.cycles = [c1]
    
    # 4. Findings
    # 2 findings -> 4 penalty
    mock_analyses.findings = [Mock(), Mock()]
    
    mock_repo.analyses = mock_analyses
    
    result = analyzer.analyze(mock_repo)
    health = result.metadata["health"]
    
    # Verify scores
    c = health.categories
    assert c["Testing"].score == 80.0
    assert c["Documentation"].score == 90.0
    
    # Complexity: 100 - 10 (avg funcs) - 5 (large files) = 85.0
    assert c["Complexity"].score == 85.0
    assert "Deducted 10.0 due to high average functions" in c["Complexity"].explanation
    assert "Deducted 5 due to extremely large files" in c["Complexity"].explanation
    
    # Architecture: 100 - 10 (cycle) - 2 (unknown layer) = 88.0
    assert c["Architecture"].score == 88.0
    
    # Maintainability: 100 - (2 findings * 2) = 96.0
    assert c["Maintainability"].score == 96.0
    
    # Overall: 
    # (80 * 0.2) + (90 * 0.15) + (85 * 0.2) + (88 * 0.25) + (96 * 0.2)
    # 16 + 13.5 + 17 + 22 + 19.2 = 87.7
    assert health.health_score == 87.7
    assert health.status == "Good"
    
    assert mock_repo.analyses.health is health
