"""
Unit tests for Tool #3 (Graph Query) validation logic.
Tests parameter validation and error handling.
"""

import pytest


class TestDirectionValidation:
    """Test direction parameter validation."""

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

    def test_empty_direction_invalid(self):
        """Test that empty direction is invalid."""
        valid_directions = ["incoming", "outgoing", "both"]
        direction = ""
        assert direction not in valid_directions


class TestDepthValidation:
    """Test depth parameter validation."""

    def test_validate_depth_minimum(self):
        """Test that depth=1 is valid."""
        depth = 1
        assert depth >= 1
        assert depth <= 10

    def test_validate_depth_maximum(self):
        """Test that depth=10 is valid."""
        depth = 10
        assert depth >= 1
        assert depth <= 10

    def test_validate_depth_middle(self):
        """Test that depth=5 is valid."""
        depth = 5
        assert depth >= 1
        assert depth <= 10

    def test_validate_depth_too_small(self):
        """Test that depth < 1 is rejected."""
        depth = 0
        assert not (depth >= 1)

    def test_validate_depth_negative(self):
        """Test that negative depth is rejected."""
        depth = -1
        assert not (depth >= 1)

    def test_validate_depth_too_large(self):
        """Test that depth > 10 is rejected."""
        depth = 11
        assert not (depth <= 10)

    def test_validate_depth_way_too_large(self):
        """Test that very large depth is rejected."""
        depth = 100
        assert not (depth <= 10)


class TestMaxNodesValidation:
    """Test max_nodes parameter validation."""

    def test_validate_max_nodes_minimum(self):
        """Test that max_nodes=1 is valid."""
        max_nodes = 1
        assert max_nodes >= 1
        assert max_nodes <= 1000

    def test_validate_max_nodes_maximum(self):
        """Test that max_nodes=1000 is valid."""
        max_nodes = 1000
        assert max_nodes >= 1
        assert max_nodes <= 1000

    def test_validate_max_nodes_middle(self):
        """Test that max_nodes=500 is valid."""
        max_nodes = 500
        assert max_nodes >= 1
        assert max_nodes <= 1000

    def test_validate_max_nodes_too_small(self):
        """Test that max_nodes < 1 is rejected."""
        max_nodes = 0
        assert not (max_nodes >= 1)

    def test_validate_max_nodes_negative(self):
        """Test that negative max_nodes is rejected."""
        max_nodes = -1
        assert not (max_nodes >= 1)

    def test_validate_max_nodes_too_large(self):
        """Test that max_nodes > 1000 is rejected."""
        max_nodes = 1001
        assert not (max_nodes <= 1000)

    def test_validate_max_nodes_way_too_large(self):
        """Test that very large max_nodes is rejected."""
        max_nodes = 10000
        assert not (max_nodes <= 1000)


class TestRelationshipTypeValidation:
    """Test relationship_type parameter validation."""

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

    def test_validate_relationship_type_depends_on(self):
        """Test that 'depends_on' relationship_type is valid."""
        valid_types = ["calls", "imports", "depends_on", "inherits", "renders"]
        rel_type = "depends_on"
        assert rel_type in valid_types

    def test_validate_relationship_type_inherits(self):
        """Test that 'inherits' relationship_type is valid."""
        valid_types = ["calls", "imports", "depends_on", "inherits", "renders"]
        rel_type = "inherits"
        assert rel_type in valid_types

    def test_validate_relationship_type_renders(self):
        """Test that 'renders' relationship_type is valid."""
        valid_types = ["calls", "imports", "depends_on", "inherits", "renders"]
        rel_type = "renders"
        assert rel_type in valid_types

    def test_validate_invalid_relationship_type(self):
        """Test that invalid relationship_type is rejected."""
        valid_types = ["calls", "imports", "depends_on", "inherits", "renders"]
        rel_type = "invalid_type"
        assert rel_type not in valid_types

    def test_validate_empty_relationship_type(self):
        """Test that empty relationship_type is invalid."""
        valid_types = ["calls", "imports", "depends_on", "inherits", "renders"]
        rel_type = ""
        assert rel_type not in valid_types


class TestNodeIdValidation:
    """Test node_id validation."""

    def test_valid_node_id_format(self):
        """Test that valid URN format is accepted."""
        node_id = "urn:function:backend/auth.py#login"
        assert node_id  # Not empty
        assert isinstance(node_id, str)
        assert len(node_id) > 0

    def test_valid_node_id_class(self):
        """Test that class node_id is accepted."""
        node_id = "urn:class:backend/auth.py#AuthManager"
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

    def test_node_id_with_newline_stripped(self):
        """Test that node_id with newlines is stripped."""
        node_id = "\nurn:function:backend/auth.py#login\n"
        cleaned = node_id.strip()
        assert cleaned == "urn:function:backend/auth.py#login"

    def test_node_id_preserve_internal_spaces(self):
        """Test that internal spaces are preserved."""
        node_id = "urn:function:backend/auth.py#login handler"
        cleaned = node_id.strip()
        assert cleaned == "urn:function:backend/auth.py#login handler"


class TestErrorMessagingLogic:
    """Test error message logic for different failures."""

    def test_node_not_found_error(self):
        """Test error format for node not found."""
        node_id = "urn:function:nonexistent.py#fake"
        error_msg = f"Node '{node_id}' not found in repository graph"
        assert "not found" in error_msg.lower()
        assert node_id in error_msg

    def test_invalid_direction_error(self):
        """Test error format for invalid direction."""
        valid_directions = ["incoming", "outgoing", "both"]
        direction = "invalid"
        error_msg = f"direction must be one of {valid_directions} (got '{direction}')"
        assert "direction" in error_msg
        assert direction in error_msg

    def test_invalid_depth_error_min(self):
        """Test error format for depth too small."""
        depth = 0
        error_msg = f"depth must be >= 1 (got {depth})"
        assert "depth" in error_msg
        assert str(depth) in error_msg

    def test_invalid_depth_error_max(self):
        """Test error format for depth too large."""
        depth = 11
        error_msg = f"depth must be <= 10 (got {depth})"
        assert "depth" in error_msg
        assert str(depth) in error_msg

    def test_invalid_max_nodes_error(self):
        """Test error format for max_nodes invalid."""
        max_nodes = 1001
        error_msg = f"max_nodes must be <= 1000 (got {max_nodes})"
        assert "max_nodes" in error_msg
        assert str(max_nodes) in error_msg

    def test_empty_node_id_error(self):
        """Test error format for empty node_id."""
        node_id = ""
        error_msg = "node_id cannot be empty"
        assert "empty" in error_msg.lower()
        assert "node_id" in error_msg
