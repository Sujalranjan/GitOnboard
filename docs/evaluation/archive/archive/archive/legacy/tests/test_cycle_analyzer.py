import pytest
from unittest.mock import Mock
from analysis.plugins.cycle_analyzer import CycleAnalyzer, TarjanSCC
from analysis.models.dependency import DependencyEdge, DependencyType
from analysis.models.severity import Severity
from analysis.models.cycle import Cycle

def test_cycle_analyzer_name():
    analyzer = CycleAnalyzer()
    assert analyzer.name == "cycle_analyzer"

def test_tarjan_scc():
    # Simple cycle A -> B -> C -> A
    graph = {
        "A": ["B"],
        "B": ["C"],
        "C": ["A", "D"],
        "D": []
    }
    tarjan = TarjanSCC(graph)
    sccs = tarjan.find_sccs()
    
    # Should find one SCC with A, B, C and one with D
    assert len(sccs) == 2
    cycles = [s for s in sccs if len(s) > 1]
    assert len(cycles) == 1
    assert set(cycles[0]) == {"A", "B", "C"}
    
def test_cycle_analyzer_with_entities():
    analyzer = CycleAnalyzer()
    
    mock_repo = Mock()
    mock_repo.analyses = Mock()
    
    mock_graph = Mock()
    mock_graph.edges = [
        DependencyEdge("mod_A", "mod_B", DependencyType.IMPORT, "", 1.0),
        DependencyEdge("mod_B", "mod_C", DependencyType.IMPORT, "", 1.0),
        DependencyEdge("mod_C", "mod_A", DependencyType.IMPORT, "", 1.0),
        # Package level edge triggers
        DependencyEdge("file1", "file2", DependencyType.IMPORT, "", 1.0),
        DependencyEdge("file2", "file3", DependencyType.IMPORT, "", 1.0),
        DependencyEdge("file3", "file1", DependencyType.IMPORT, "", 1.0),
    ]
    mock_repo.analyses.dependency_graph = mock_graph
    
    # Mock files to test package logic
    mock_entities = Mock()
    mock_f1 = Mock(path="pkgA/file1.py")
    mock_f2 = Mock(path="pkgB/file2.py")
    mock_f3 = Mock(path="pkgC/file3.py")
    # Make pkgC depend on pkgA to create a package cycle pkgA -> pkgB -> pkgC -> pkgA
    mock_entities.files = {
        "file1": mock_f1,
        "file2": mock_f2,
        "file3": mock_f3
    }
    mock_repo.entities = mock_entities
    
    result = analyzer.analyze(mock_repo)
    cycles = result.metadata["cycles"]
    
    # We should have one module cycle (mod_A, mod_B, mod_C) 
    # one module cycle (file1, file2, file3)
    # And one package cycle (pkgA, pkgB, pkgC)
    assert len(cycles) == 3
    
    assert any(c.size == 3 and "mod_A" in c.members for c in cycles)
    assert any(c.size == 3 and "pkgA" in c.members for c in cycles)
    
    # Size 3 -> ERROR severity
    assert all(c.severity == Severity.ERROR for c in cycles)
    
    # Check findings
    assert len(result.findings) == 3
    assert any("Module Cycle" in f.title for f in result.findings)
    assert any("Package Cycle" in f.title for f in result.findings)
    
    # RIM storage check
    assert mock_repo.analyses.cycles is cycles
    assert mock_repo.analysis_status.cycles is True
