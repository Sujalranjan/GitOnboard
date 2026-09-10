import pytest
from unittest.mock import Mock
from analysis.plugins.dependency_analyzer import DependencyAnalyzer
from analysis.models.dependency import DependencyType, DependencyGraph
from analysis.models.layer import ArchitecturalLayer

def test_dependency_analyzer_name():
    analyzer = DependencyAnalyzer()
    assert analyzer.name == "dependency_analyzer"

def test_dependency_analyzer_with_entities():
    analyzer = DependencyAnalyzer()
    
    mock_repo = Mock()
    mock_repo.analyses = Mock()
    mock_repo.analyses.architecture = {
        "mod_controller": ArchitecturalLayer.CONTROLLER,
        "mod_repo": ArchitecturalLayer.REPOSITORY
    }
    
    mock_repo.analysis_status = Mock()
    
    # Setup relationships
    mock_relationships = Mock()
    mock_relationships.imports = {"file_1": ["file_2"]}
    mock_relationships.calls = {"fn_1": ["fn_2"]}
    mock_relationships.depends_on = {
        "cls_1": ["cls_2"],
        "fn_3": ["fn_4"]
    }
    mock_repo.relationships = mock_relationships
    
    # Setup entities
    mock_entities = Mock()
    
    # Entity imports
    mock_imp1 = Mock(file_id="file_1", module_name="sqlalchemy")
    mock_imp2 = Mock(file_id="file_2", module_name="fastapi")
    mock_entities.imports = {"imp1": mock_imp1, "imp2": mock_imp2}
    
    # Functions
    mock_fn1 = Mock(module_id="mod_controller")
    mock_fn2 = Mock(module_id="mod_repo")
    mock_fn3 = Mock(name="my_func")
    mock_fn4 = Mock(name="my_func_decorator")
    mock_fn4.name = "login_required_decorator"
    mock_entities.functions = {
        "fn_1": mock_fn1, 
        "fn_2": mock_fn2,
        "fn_3": mock_fn3,
        "fn_4": mock_fn4
    }
    
    # Classes
    mock_cls1 = Mock(name="User")
    mock_cls2 = Mock(name="BaseModel")
    mock_cls2.name = "BaseModel"
    mock_entities.classes = {
        "cls_1": mock_cls1,
        "cls_2": mock_cls2
    }
    
    mock_repo.entities = mock_entities
    
    result = analyzer.analyze(mock_repo)
    
    graph: DependencyGraph = result.metadata["dependency_graph"]
    assert isinstance(graph, DependencyGraph)
    edges = graph.edges
    
    # 1. IMPORT (relationships.imports)
    assert any(e.source == "file_1" and e.destination == "file_2" and e.type == DependencyType.IMPORT for e in edges)
    
    # 2. IMPORT (entities.imports) -> SQLAlchemy -> DATABASE
    assert any(e.source == "file_1" and e.destination == "sqlalchemy" and e.type == DependencyType.IMPORT for e in edges)
    assert any(e.source == "file_1" and e.destination == "sqlalchemy" and e.type == DependencyType.DATABASE for e in edges)
    
    # 3. CALL
    assert any(e.source == "fn_1" and e.destination == "fn_2" and e.type == DependencyType.CALL for e in edges)
    
    # 4. CROSS-MODULE CALL -> mod_controller to mod_repo -> DATABASE
    assert any(e.source == "mod_controller" and e.destination == "mod_repo" and e.type == DependencyType.DATABASE for e in edges)
    
    # 5. API (because mod_controller is CONTROLLER)
    assert any(e.source == "mod_controller" and e.destination == "EXTERNAL_CLIENT" and e.type == DependencyType.API for e in edges)
    
    # 6. INHERITANCE (BaseModel)
    assert any(e.source == "cls_1" and e.destination == "cls_2" and e.type == DependencyType.INHERITANCE for e in edges)
    
    # 7. DECORATOR (login_required_decorator)
    assert any(e.source == "fn_3" and e.destination == "fn_4" and e.type == DependencyType.DECORATOR for e in edges)

    # Validate RIM persistence
    assert mock_repo.analyses.dependency_graph is graph
    assert mock_repo.analysis_status.dependencies is True
