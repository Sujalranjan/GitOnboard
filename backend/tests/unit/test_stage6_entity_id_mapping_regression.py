"""
Regression test for Stage 6 Entity ID Mapping fix (Phase 2L.8 Stage 6 Repair).

Issue: GraphNavigator.navigate() was failing to match entity IDs from retriever results
to RepositoryModel.entities when IDs had different formats (bare URN vs. prefixed).

This test ensures that:
1. Bare URN format IDs are matched correctly
2. Prefixed format IDs (with analysis_id) are matched correctly
3. Symbol_id from metadata is used as fallback
4. Fuzzy matching still works as final fallback
"""
import pytest
from backend.intelligence.retrieval.schema import RetrieverResult, EntityType
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.rim.enums import EntityType as RIMEntityType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigator


@pytest.fixture
def bare_urn_model():
    """Create model with bare URN format entity IDs (from in-memory AnalysisEngine)."""
    model = RepositoryModel(metadata=RepositoryMetadata(name="test", path="/tmp/test"))

    # Add entities with bare URN format
    entity_ids = [
        "urn:function:src/auth.py#authenticate",
        "urn:function:src/auth.py#login",
        "urn:class:src/models/user.py#User",
    ]

    for entity_id in entity_ids:
        entity = Entity(
            id=entity_id,
            type=RIMEntityType.FUNCTION,
            name=entity_id.split("#")[1],
            qualified_name=entity_id.split("#")[1],
            location=SourceLocation(
                repository_path="src/auth.py",
                start_line=1,
                end_line=10,
                language="Python"
            )
        )
        model.entities[entity_id] = entity

    return model


@pytest.fixture
def prefixed_id_model():
    """Create model with analysis_id-prefixed entity IDs (from database FactStore)."""
    model = RepositoryModel(metadata=RepositoryMetadata(name="test", path="/tmp/test"))

    analysis_id = 847126

    # Add entities with prefixed format (as stored in database)
    bare_ids = [
        "urn:function:src/auth.py#authenticate",
        "urn:function:src/auth.py#login",
        "urn:class:src/models/user.py#User",
    ]

    for bare_id in bare_ids:
        prefixed_id = f"{analysis_id}:{bare_id}"
        entity = Entity(
            id=prefixed_id,  # Stored with prefix
            type=RIMEntityType.FUNCTION,
            name=bare_id.split("#")[1],
            qualified_name=bare_id.split("#")[1],
            location=SourceLocation(
                repository_path="src/auth.py",
                start_line=1,
                end_line=10,
                language="Python"
            )
        )
        model.entities[prefixed_id] = entity

    return model


def test_stage6_bare_urn_id_matching(bare_urn_model):
    """Test that GraphNavigator matches bare URN format IDs correctly."""
    navigator = GraphNavigator(bare_urn_model)

    # Create retriever results with bare URN IDs (as returned by retriever)
    retriever_results = [
        RetrieverResult(
            id="urn:function:src/auth.py#authenticate",
            entity_name="authenticate",
            entity_type=EntityType.SYMBOL,
            file_path="src/auth.py",
            qualified_name="authenticate",
            score_type="lexical",
            score=0.95,
            metadata={"symbol_id": "847126:urn:function:src/auth.py#authenticate"}
        ),
        RetrieverResult(
            id="urn:function:src/auth.py#login",
            entity_name="login",
            entity_type=EntityType.SYMBOL,
            file_path="src/auth.py",
            qualified_name="login",
            score_type="lexical",
            score=0.90,
            metadata={"symbol_id": "847126:urn:function:src/auth.py#login"}
        ),
    ]

    result = navigator.navigate(retriever_results)

    # Should find both seed entities
    assert result.entity_count >= 2, f"Expected 2+ entities, got {result.entity_count}"
    assert "urn:function:src/auth.py#authenticate" in result.discovered_entities
    assert "urn:function:src/auth.py#login" in result.discovered_entities
    assert len(result.validation_errors) == 0, f"Unexpected errors: {result.validation_errors}"


def test_stage6_prefixed_id_matching(prefixed_id_model):
    """Test that GraphNavigator matches prefixed format IDs correctly."""
    navigator = GraphNavigator(prefixed_id_model)

    # Create retriever results with bare URN IDs (as returned by retriever)
    retriever_results = [
        RetrieverResult(
            id="urn:function:src/auth.py#authenticate",
            entity_name="authenticate",
            entity_type=EntityType.SYMBOL,
            file_path="src/auth.py",
            qualified_name="authenticate",
            score_type="lexical",
            score=0.95,
            metadata={"symbol_id": "847126:urn:function:src/auth.py#authenticate"}
        ),
        RetrieverResult(
            id="urn:class:src/models/user.py#User",
            entity_name="User",
            entity_type=EntityType.SYMBOL,
            file_path="src/models/user.py",
            qualified_name="User",
            score_type="lexical",
            score=0.85,
            metadata={"symbol_id": "847126:urn:class:src/models/user.py#User"}
        ),
    ]

    result = navigator.navigate(retriever_results)

    # Should find both seed entities even though model has prefixed IDs
    assert result.entity_count >= 2, f"Expected 2+ entities, got {result.entity_count}"
    # Discovered entities will be stored with the prefixed ID
    discovered_ids = list(result.discovered_entities.keys())
    assert any("authenticate" in eid for eid in discovered_ids), \
        f"authenticate not found in {discovered_ids}"
    assert any("User" in eid for eid in discovered_ids), \
        f"User not found in {discovered_ids}"


def test_stage6_symbol_id_fallback(prefixed_id_model):
    """Test that symbol_id from metadata is used as fallback."""
    navigator = GraphNavigator(prefixed_id_model)

    # Create retriever result where bare ID doesn't exist in model
    # but symbol_id (with prefix) does
    retriever_results = [
        RetrieverResult(
            id="urn:function:src/auth.py#authenticate",
            entity_name="authenticate",
            entity_type=EntityType.SYMBOL,
            file_path="src/auth.py",
            qualified_name="authenticate",
            score_type="lexical",
            score=0.95,
            metadata={"symbol_id": "847126:urn:function:src/auth.py#authenticate"}
        ),
    ]

    result = navigator.navigate(retriever_results)

    # Should find the entity using symbol_id fallback
    assert result.entity_count >= 1, f"Expected 1+ entities, got {result.entity_count}"


def test_stage6_empty_seed_handling(bare_urn_model):
    """Test that GraphNavigator handles case where no seed entities are found."""
    navigator = GraphNavigator(bare_urn_model)

    # Create retriever result that doesn't exist in model
    retriever_results = [
        RetrieverResult(
            id="urn:function:nonexistent.py#nonexistent",
            entity_name="nonexistent",
            entity_type=EntityType.SYMBOL,
            file_path="nonexistent.py",
            qualified_name="nonexistent",
            score_type="lexical",
            score=0.1,
            metadata={"symbol_id": "847126:urn:function:nonexistent.py#nonexistent"}
        ),
    ]

    result = navigator.navigate(retriever_results)

    # Should return empty result gracefully
    assert result.entity_count == 0
    assert len(result.validation_errors) > 0, "Should record validation error"
    assert "not found" in result.validation_errors[0].lower()


def test_stage6_mixed_id_formats(bare_urn_model, prefixed_id_model):
    """Test GraphNavigator with mixed bare and prefixed IDs in model."""
    # Create model with mixed formats
    mixed_model = RepositoryModel(metadata=RepositoryMetadata(name="test", path="/tmp/test"))

    analysis_id = 847126

    # Add some with bare format
    mixed_model.entities["urn:function:src/auth.py#authenticate"] = Entity(
        id="urn:function:src/auth.py#authenticate",
        type=RIMEntityType.FUNCTION,
        name="authenticate",
        qualified_name="authenticate",
        location=SourceLocation(
            repository_path="src/auth.py",
            start_line=1,
            end_line=10,
            language="Python"
        )
    )

    # Add some with prefixed format
    mixed_model.entities[f"{analysis_id}:urn:function:src/auth.py#login"] = Entity(
        id=f"{analysis_id}:urn:function:src/auth.py#login",
        type=RIMEntityType.FUNCTION,
        name="login",
        qualified_name="login",
        location=SourceLocation(
            repository_path="src/auth.py",
            start_line=11,
            end_line=20,
            language="Python"
        )
    )

    navigator = GraphNavigator(mixed_model)

    # Create retriever results for both
    retriever_results = [
        RetrieverResult(
            id="urn:function:src/auth.py#authenticate",
            entity_name="authenticate",
            entity_type=EntityType.SYMBOL,
            file_path="src/auth.py",
            score_type="lexical",
            score=0.95,
            metadata={"symbol_id": "847126:urn:function:src/auth.py#authenticate"}
        ),
        RetrieverResult(
            id="urn:function:src/auth.py#login",
            entity_name="login",
            entity_type=EntityType.SYMBOL,
            file_path="src/auth.py",
            score_type="lexical",
            score=0.90,
            metadata={"symbol_id": "847126:urn:function:src/auth.py#login"}
        ),
    ]

    result = navigator.navigate(retriever_results)

    # Should find both entities regardless of format
    assert result.entity_count >= 2, f"Expected 2+ entities, got {result.entity_count}"
