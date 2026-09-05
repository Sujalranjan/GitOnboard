"""
Unit tests for Stage 6: Graph Navigation

Tests bounded BFS traversal, deduplication, and entity validation.
"""
import pytest
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.enums import EntityType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigator, GraphNavigationResult
from backend.intelligence.retrieval.schema import RetrieverResult, EntityType as RetrieverEntityType


@pytest.fixture
def simple_model():
    """Create a simple test model."""
    model = RepositoryModel(metadata=RepositoryMetadata(name="test_repo", path="/tmp/test"))

    # Add entities
    func_a = Entity(
        id="func:main",
        name="main",
        type=EntityType.FUNCTION,
        location=SourceLocation(repository_path="main.py", start_line=1, end_line=10, language="python")
    )
    func_b = Entity(
        id="func:helper",
        name="helper",
        type=EntityType.FUNCTION,
        location=SourceLocation(repository_path="util.py", start_line=20, end_line=30, language="python")
    )
    func_c = Entity(
        id="func:process",
        name="process",
        type=EntityType.FUNCTION,
        location=SourceLocation(repository_path="process.py", start_line=40, end_line=50, language="python")
    )

    model.entities = {
        "func:main": func_a,
        "func:helper": func_b,
        "func:process": func_c,
    }

    # Add relationships
    rel1 = Relationship(
        id="rel:1",
        source_id="func:main",
        target_id="func:helper",
        type="CALLS"
    )
    rel2 = Relationship(
        id="rel:2",
        source_id="func:helper",
        target_id="func:process",
        type="CALLS"
    )

    model.relationships = {
        "rel:1": rel1,
        "rel:2": rel2,
    }

    return model


def test_graph_navigator_simple_traversal(simple_model):
    """Test basic BFS traversal from single anchor."""
    navigator = GraphNavigator(simple_model, max_depth=3)

    # Create seed from func_a
    seed = [
        RetrieverResult(
            id="func:main",
            entity_name="main",
            entity_type=RetrieverEntityType.SYMBOL,
            file_path="main.py",
            relevance_score=1.0
        )
    ]

    result = navigator.navigate(seed)

    assert result.entity_count > 0, "Should discover at least the seed entity"
    assert "func:main" in result.discovered_entities
    assert result.traversal_depth >= 0
    assert len(result.traversal_edges) >= 0


def test_graph_navigator_max_depth_enforcement(simple_model):
    """Test that traversal respects max_depth limit."""
    navigator = GraphNavigator(simple_model, max_depth=1)

    seed = [
        RetrieverResult(
            id="func:main",
            entity_name="main",
            entity_type=RetrieverEntityType.SYMBOL,
            file_path="main.py",
            relevance_score=1.0
        )
    ]

    result = navigator.navigate(seed)

    assert result.traversal_depth <= 1, "Should not exceed max_depth"


def test_graph_navigator_deduplication(simple_model):
    """Test that discovered entities are deduplicated."""
    navigator = GraphNavigator(simple_model, max_depth=3)

    seed = [
        RetrieverResult(
            id="func:main",
            entity_name="main",
            entity_type=RetrieverEntityType.SYMBOL,
            file_path="main.py",
            relevance_score=1.0
        )
    ]

    result = navigator.navigate(seed)

    # Check for duplicates in edges
    edge_pairs = [(e["source_id"], e["target_id"]) for e in result.traversal_edges]
    assert len(edge_pairs) == len(set(edge_pairs)), "Should not have duplicate edges"


def test_graph_navigator_entity_validation(simple_model):
    """Test that entities are validated for existence."""
    navigator = GraphNavigator(simple_model, max_depth=2)

    seed = [
        RetrieverResult(
            id="func:main",
            entity_name="main",
            entity_type=RetrieverEntityType.SYMBOL,
            file_path="main.py",
            relevance_score=1.0
        )
    ]

    result = navigator.navigate(seed)

    # All discovered entities should be in model
    for entity_id, entity in result.discovered_entities.items():
        assert entity_id in simple_model.entities, f"Entity {entity_id} should be in model"


def test_graph_navigator_empty_seed(simple_model):
    """Test handling of empty seed set."""
    navigator = GraphNavigator(simple_model, max_depth=3)

    result = navigator.navigate([])

    assert result.entity_count == 0
    assert result.edge_count == 0


def test_graph_navigator_invalid_seed(simple_model):
    """Test handling of invalid seed entities."""
    navigator = GraphNavigator(simple_model, max_depth=3)

    seed = [
        RetrieverResult(
            id="func:nonexistent",
            entity_name="nonexistent",
            entity_type=RetrieverEntityType.FUNCTION,
            file_path="nowhere.py",
            relevance_score=1.0
        )
    ]

    result = navigator.navigate(seed)

    assert result.entity_count == 0, "Should not discover anything from invalid seed"
    assert len(result.validation_errors) > 0, "Should record validation error"


def test_graph_navigator_breadth_limit(simple_model):
    """Test that per-entity edge limit is enforced."""
    navigator = GraphNavigator(simple_model, max_depth=3, max_edges_per_entity=1)

    seed = [
        RetrieverResult(
            id="func:main",
            entity_name="main",
            entity_type=RetrieverEntityType.SYMBOL,
            file_path="main.py",
            relevance_score=1.0
        )
    ]

    result = navigator.navigate(seed)

    # Each entity should have at most max_edges_per_entity outgoing edges
    edges_from_entity = {}
    for edge in result.traversal_edges:
        src = edge["source_id"]
        edges_from_entity[src] = edges_from_entity.get(src, 0) + 1

    assert all(count <= 1 for count in edges_from_entity.values()), \
        "Should not exceed max_edges_per_entity"
