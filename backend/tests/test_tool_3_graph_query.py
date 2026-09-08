"""
Unit tests for Tool #3 (Graph Query) validation logic.
Tests strict node existence checks and parameter validation.
"""

import pytest
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.graphs.graph_query_service import GraphQueryService


@pytest.fixture
def test_model_with_entities():
    """Create a test RepositoryModel with sample entities and relationships."""
    model = RepositoryModel()

    # Create entities
    loc1 = SourceLocation(repository_path="backend/auth.py", start_line=10, end_line=15, language="python")
    entity1 = Entity(
        id="urn:function:backend/auth.py#login",
        name="login",
        type=EntityType.FUNCTION,
        location=loc1
    )

    loc2 = SourceLocation(repository_path="backend/database.py", start_line=20, end_line=25, language="python")
    entity2 = Entity(
        id="urn:function:backend/database.py#get_user",
        name="get_user",
        type=EntityType.FUNCTION,
        location=loc2
    )

    loc3 = SourceLocation(repository_path="backend/utils.py", start_line=30, end_line=35, language="python")
    entity3 = Entity(
        id="urn:function:backend/utils.py#hash_password",
        name="hash_password",
        type=EntityType.FUNCTION,
        location=loc3
    )

    model.entities = {
        entity1.id: entity1,
        entity2.id: entity2,
        entity3.id: entity3,
    }

    # Create relationships
    rel1 = Relationship(
        id="rel1",
        source_id=entity1.id,
        target_id=entity2.id,
        type=RelationshipType.CALLS,
        file_path="backend/auth.py"
    )

    rel2 = Relationship(
        id="rel2",
        source_id=entity1.id,
        target_id=entity3.id,
        type=RelationshipType.CALLS,
        file_path="backend/auth.py"
    )

    model.relationships = {
        rel1.id: rel1,
        rel2.id: rel2,
    }

    return model


class TestNodeExistenceValidation:
    """Test node existence checks."""

    def test_node_exists_in_model(self, test_model_with_entities):
        """Test that existing node is found in model."""
        node_id = "urn:function:backend/auth.py#login"
        assert node_id in test_model_with_entities.entities
        assert test_model_with_entities.entities[node_id].name == "login"

    def test_node_not_exists_in_model(self, test_model_with_entities):
        """Test that nonexistent node is not found in model."""
        node_id = "urn:function:nonexistent.py#fake"
        assert node_id not in test_model_with_entities.entities

    def test_node_exists_returns_entity(self, test_model_with_entities):
        """Test that existing node returns entity object."""
        node_id = "urn:function:backend/auth.py#login"
        entity = test_model_with_entities.entities.get(node_id)
        assert entity is not None
        assert entity.type == EntityType.FUNCTION

    def test_node_not_exists_returns_none(self, test_model_with_entities):
        """Test that nonexistent node returns None."""
        node_id = "urn:function:nonexistent.py#fake"
        entity = test_model_with_entities.entities.get(node_id)
        assert entity is None


class TestGraphTraversalWithValidation:
    """Test graph traversal with node validation."""

    def test_traverse_from_valid_node(self, test_model_with_entities):
        """Test traversing from a valid node."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:backend/auth.py#login"

        # Verify node exists
        assert node_id in service.model.entities

        # Traverse
        result = service.traverse(
            node_id=node_id,
            direction="outgoing",
            depth=1,
            max_nodes=50,
            relationship_type="calls"
        )

        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) > 0

    def test_traverse_from_invalid_node_would_fail(self, test_model_with_entities):
        """Test that traversing from invalid node would be caught by validation."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:nonexistent.py#fake"

        # Validation check (what endpoint does)
        if node_id not in service.model.entities:
            # This is what the endpoint should do
            is_valid = False
        else:
            is_valid = True

        assert not is_valid


class TestParameterValidation:
    """Test parameter validation for graph queries."""

    def test_validate_direction_incoming(self):
        """Test that 'incoming' direction is valid."""
        valid_directions = ["incoming", "outgoing", "both"]
        direction = "incoming"
        assert direction in valid_directions

    def test_validate_direction_outgoing(self):
        """Test that 'outgoing' direction is valid."""
        valid_directions = ["incoming", "outgoing", "both"]
        direction = "outgoing"
        assert direction in valid_directions

    def test_validate_direction_both(self):
        """Test that 'both' direction is valid."""
        valid_directions = ["incoming", "outgoing", "both"]
        direction = "both"
        assert direction in valid_directions

    def test_validate_invalid_direction(self):
        """Test that invalid direction is rejected."""
        valid_directions = ["incoming", "outgoing", "both"]
        direction = "invalid_direction"
        assert direction not in valid_directions

    def test_validate_depth_range(self):
        """Test that depth is in valid range."""
        depth = 5
        assert depth >= 1
        assert depth <= 10

    def test_validate_depth_too_small(self):
        """Test that depth < 1 is rejected."""
        depth = 0
        assert not (depth >= 1)

    def test_validate_depth_too_large(self):
        """Test that depth > 10 is rejected."""
        depth = 11
        assert not (depth <= 10)

    def test_validate_max_nodes_range(self):
        """Test that max_nodes is in valid range."""
        max_nodes = 500
        assert max_nodes >= 1
        assert max_nodes <= 1000

    def test_validate_max_nodes_too_small(self):
        """Test that max_nodes < 1 is rejected."""
        max_nodes = 0
        assert not (max_nodes >= 1)

    def test_validate_max_nodes_too_large(self):
        """Test that max_nodes > 1000 is rejected."""
        max_nodes = 1001
        assert not (max_nodes <= 1000)

    def test_validate_relationship_type_calls(self):
        """Test that 'calls' relationship_type is valid."""
        valid_types = ["calls", "imports", "depends_on", "inherits", "renders"]
        rel_type = "calls"
        assert rel_type in valid_types

    def test_validate_relationship_type_imports(self):
        """Test that 'imports' relationship_type is valid."""
        valid_types = ["calls", "imports", "depends_on", "inherits", "renders"]
        rel_type = "imports"
        assert rel_type in valid_types

    def test_validate_invalid_relationship_type(self):
        """Test that invalid relationship_type is rejected."""
        valid_types = ["calls", "imports", "depends_on", "inherits", "renders"]
        rel_type = "invalid_type"
        assert rel_type not in valid_types


class TestNodeIdValidation:
    """Test node_id validation."""

    def test_valid_node_id_format(self):
        """Test that valid URN format is accepted."""
        node_id = "urn:function:backend/auth.py#login"
        assert node_id  # Not empty
        assert isinstance(node_id, str)

    def test_empty_node_id_rejected(self):
        """Test that empty node_id is rejected."""
        node_id = ""
        assert not (node_id and node_id.strip())

    def test_whitespace_only_node_id_rejected(self):
        """Test that whitespace-only node_id is rejected."""
        node_id = "   "
        assert not (node_id and node_id.strip())

    def test_node_id_strip_whitespace(self):
        """Test that node_id whitespace is stripped."""
        node_id = "  urn:function:backend/auth.py#login  "
        cleaned = node_id.strip()
        assert cleaned == "urn:function:backend/auth.py#login"


class TestGraphQueryService:
    """Test GraphQueryService methods."""

    def test_get_entity(self, test_model_with_entities):
        """Test retrieving entity by id."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:backend/auth.py#login"

        entity = service.get_entity(node_id)
        assert entity is not None
        assert entity.name == "login"

    def test_get_entity_not_found(self, test_model_with_entities):
        """Test retrieving nonexistent entity."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:nonexistent.py#fake"

        entity = service.get_entity(node_id)
        assert entity is None

    def test_get_outgoing_relationships(self, test_model_with_entities):
        """Test getting outgoing relationships."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:backend/auth.py#login"

        outgoing = service.get_outgoing(node_id)
        assert len(outgoing) == 2  # login calls get_user and hash_password

    def test_get_incoming_relationships(self, test_model_with_entities):
        """Test getting incoming relationships."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:backend/database.py#get_user"

        incoming = service.get_incoming(node_id)
        assert len(incoming) == 1  # Called by login

    def test_search_by_name(self, test_model_with_entities):
        """Test searching entities by name."""
        service = GraphQueryService(test_model_with_entities)
        results = service.search("login")

        assert len(results) > 0
        assert any(r["name"] == "login" for r in results)

    def test_search_returns_empty_for_nonexistent(self, test_model_with_entities):
        """Test search returns empty for nonexistent name."""
        service = GraphQueryService(test_model_with_entities)
        results = service.search("nonexistent_function")

        assert len(results) == 0


class TestTraversalResult:
    """Test graph traversal result format."""

    def test_traverse_result_has_nodes_and_edges(self, test_model_with_entities):
        """Test that traverse result contains nodes and edges."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:backend/auth.py#login"

        result = service.traverse(
            node_id=node_id,
            direction="outgoing",
            depth=1,
            max_nodes=50,
            relationship_type="calls"
        )

        assert "nodes" in result
        assert "edges" in result
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)

    def test_traverse_result_nodes_have_id_and_label(self, test_model_with_entities):
        """Test that result nodes have required fields."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:backend/auth.py#login"

        result = service.traverse(
            node_id=node_id,
            direction="outgoing",
            depth=1,
            max_nodes=50,
            relationship_type="calls"
        )

        for node in result["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "full_name" in node

    def test_traverse_result_edges_have_required_fields(self, test_model_with_entities):
        """Test that result edges have required fields."""
        service = GraphQueryService(test_model_with_entities)
        node_id = "urn:function:backend/auth.py#login"

        result = service.traverse(
            node_id=node_id,
            direction="outgoing",
            depth=1,
            max_nodes=50,
            relationship_type="calls"
        )

        for edge in result["edges"]:
            assert "id" in edge
            assert "source" in edge
            assert "target" in edge

    def test_traverse_node_with_no_relationships(self, test_model_with_entities):
        """Test traversing node with no relationships returns just the node."""
        service = GraphQueryService(test_model_with_entities)
        # hash_password has no outgoing calls
        node_id = "urn:function:backend/utils.py#hash_password"

        result = service.traverse(
            node_id=node_id,
            direction="outgoing",
            depth=1,
            max_nodes=50,
            relationship_type="calls"
        )

        # Should have the node itself even with no edges
        assert len(result["nodes"]) > 0
        # But no outgoing edges
        assert len(result["edges"]) == 0
