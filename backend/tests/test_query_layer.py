"""
Comprehensive tests for bidirectional QueryLayer navigation.

Tests cover:
- Forward query methods (get_calls, get_imports, etc.)
- Reverse query methods (get_called_by, get_imported_by, etc.)
- Relationship metadata preservation
- Empty/NULL results
- All relationship types
"""

import pytest
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.query_layer import QueryLayer


def build_test_repository():
    """Build a test repository with various relationships."""

    # Create entities
    file_main = Entity(
        id="file_main_py",
        type=EntityType.FILE,
        name="main.py",
        location=SourceLocation(
            repository_path="src/main.py",
            start_line=1,
            end_line=100,
            language="Python",
        ),
        metadata={"language": "Python"},
    )

    file_utils = Entity(
        id="file_utils_py",
        type=EntityType.FILE,
        name="utils.py",
        location=SourceLocation(
            repository_path="src/utils.py",
            start_line=1,
            end_line=50,
            language="Python",
        ),
        metadata={"language": "Python"},
    )

    file_models = Entity(
        id="file_models_py",
        type=EntityType.FILE,
        name="models.py",
        location=SourceLocation(
            repository_path="src/models.py",
            start_line=1,
            end_line=150,
            language="Python",
        ),
        metadata={"language": "Python"},
    )

    # Functions
    func_main = Entity(
        id="func_main",
        type=EntityType.FUNCTION,
        name="main",
        qualified_name="src.main.main",
        location=SourceLocation(
            repository_path="src/main.py",
            start_line=10,
            end_line=30,
            language="Python",
        ),
        metadata={"file_id": "file_main_py"},
    )

    func_helper = Entity(
        id="func_helper",
        type=EntityType.FUNCTION,
        name="helper",
        qualified_name="src.utils.helper",
        location=SourceLocation(
            repository_path="src/utils.py",
            start_line=10,
            end_line=20,
            language="Python",
        ),
        metadata={"file_id": "file_utils_py"},
    )

    func_util_func = Entity(
        id="func_util",
        type=EntityType.FUNCTION,
        name="utility_function",
        qualified_name="src.utils.utility_function",
        location=SourceLocation(
            repository_path="src/utils.py",
            start_line=25,
            end_line=40,
            language="Python",
        ),
        metadata={"file_id": "file_utils_py"},
    )

    # Classes
    class_base = Entity(
        id="class_base",
        type=EntityType.CLASS,
        name="BaseClass",
        qualified_name="src.models.BaseClass",
        location=SourceLocation(
            repository_path="src/models.py",
            start_line=50,
            end_line=80,
            language="Python",
        ),
        metadata={"file_id": "file_models_py"},
    )

    class_derived = Entity(
        id="class_derived",
        type=EntityType.CLASS,
        name="DerivedClass",
        qualified_name="src.models.DerivedClass",
        location=SourceLocation(
            repository_path="src/main.py",
            start_line=35,
            end_line=60,
            language="Python",
        ),
        metadata={"file_id": "file_main_py"},
    )

    class_another = Entity(
        id="class_another",
        type=EntityType.CLASS,
        name="AnotherClass",
        qualified_name="src.models.AnotherClass",
        location=SourceLocation(
            repository_path="src/models.py",
            start_line=85,
            end_line=120,
            language="Python",
        ),
        metadata={"file_id": "file_models_py"},
    )

    # Create relationships
    relationships = {}

    # CALLS relationships
    # main() calls helper()
    relationships["rel_main_calls_helper"] = Relationship(
        id="rel_main_calls_helper",
        type=RelationshipType.CALLS,
        source_id="func_main",
        target_id="func_helper",
        metadata={"line": 15, "snippet": "helper()"},
    )

    # main() calls utility_function()
    relationships["rel_main_calls_util"] = Relationship(
        id="rel_main_calls_util",
        type=RelationshipType.CALLS,
        source_id="func_main",
        target_id="func_util",
        metadata={"line": 20, "snippet": "utility_function()"},
    )

    # helper() calls utility_function()
    relationships["rel_helper_calls_util"] = Relationship(
        id="rel_helper_calls_util",
        type=RelationshipType.CALLS,
        source_id="func_helper",
        target_id="func_util",
        metadata={"line": 12, "snippet": "utility_function()"},
    )

    # IMPORTS relationships
    # main imports utils
    relationships["rel_main_imports_utils"] = Relationship(
        id="rel_main_imports_utils",
        type=RelationshipType.IMPORTS,
        source_id="file_main_py",
        target_id="file_utils_py",
        metadata={"line": 1, "snippet": "import utils"},
    )

    # main imports models
    relationships["rel_main_imports_models"] = Relationship(
        id="rel_main_imports_models",
        type=RelationshipType.IMPORTS,
        source_id="file_main_py",
        target_id="file_models_py",
        metadata={"line": 2, "snippet": "from models import *"},
    )

    # utils imports models
    relationships["rel_utils_imports_models"] = Relationship(
        id="rel_utils_imports_models",
        type=RelationshipType.IMPORTS,
        source_id="file_utils_py",
        target_id="file_models_py",
        metadata={"line": 1, "snippet": "import models"},
    )

    # DEPENDS_ON relationships
    # main depends on utils
    relationships["rel_main_depends_utils"] = Relationship(
        id="rel_main_depends_utils",
        type=RelationshipType.DEPENDS_ON,
        source_id="file_main_py",
        target_id="file_utils_py",
        metadata={"reason": "uses utility functions"},
    )

    # main depends on models
    relationships["rel_main_depends_models"] = Relationship(
        id="rel_main_depends_models",
        type=RelationshipType.DEPENDS_ON,
        source_id="file_main_py",
        target_id="file_models_py",
        metadata={"reason": "uses model classes"},
    )

    # INHERITS relationships
    # DerivedClass inherits from BaseClass
    relationships["rel_derived_inherits_base"] = Relationship(
        id="rel_derived_inherits_base",
        type=RelationshipType.INHERITS,
        source_id="class_derived",
        target_id="class_base",
        metadata={"line": 35, "snippet": "class DerivedClass(BaseClass):"},
    )

    # AnotherClass inherits from BaseClass
    relationships["rel_another_inherits_base"] = Relationship(
        id="rel_another_inherits_base",
        type=RelationshipType.INHERITS,
        source_id="class_another",
        target_id="class_base",
        metadata={"line": 85, "snippet": "class AnotherClass(BaseClass):"},
    )

    # USES relationships
    # main uses DerivedClass
    relationships["rel_main_uses_derived"] = Relationship(
        id="rel_main_uses_derived",
        type=RelationshipType.USES,
        source_id="func_main",
        target_id="class_derived",
        metadata={"line": 25, "snippet": "obj = DerivedClass()"},
    )

    # helper uses AnotherClass
    relationships["rel_helper_uses_another"] = Relationship(
        id="rel_helper_uses_another",
        type=RelationshipType.USES,
        source_id="func_helper",
        target_id="class_another",
        metadata={"line": 15, "snippet": "return AnotherClass()"},
    )

    # IMPLEMENTS relationships (simulating interface implementation)
    interface_entity = Entity(
        id="interface_serializable",
        type=EntityType.INTERFACE,
        name="Serializable",
        qualified_name="src.models.Serializable",
        location=SourceLocation(
            repository_path="src/models.py",
            start_line=1,
            end_line=10,
            language="Python",
        ),
        metadata={"file_id": "file_models_py"},
    )

    # DerivedClass implements Serializable
    relationships["rel_derived_implements_serial"] = Relationship(
        id="rel_derived_implements_serial",
        type=RelationshipType.IMPLEMENTS,
        source_id="class_derived",
        target_id="interface_serializable",
        metadata={"line": 35, "snippet": "class DerivedClass(Serializable):"},
    )

    # AnotherClass implements Serializable
    relationships["rel_another_implements_serial"] = Relationship(
        id="rel_another_implements_serial",
        type=RelationshipType.IMPLEMENTS,
        source_id="class_another",
        target_id="interface_serializable",
        metadata={"line": 85, "snippet": "class AnotherClass(Serializable):"},
    )

    entities = {
        file_main.id: file_main,
        file_utils.id: file_utils,
        file_models.id: file_models,
        func_main.id: func_main,
        func_helper.id: func_helper,
        func_util_func.id: func_util_func,
        class_base.id: class_base,
        class_derived.id: class_derived,
        class_another.id: class_another,
        interface_entity.id: interface_entity,
    }

    return RepositoryModel(
        metadata=RepositoryMetadata(name="TestRepo", path="/test", languages=["Python"]),
        entities=entities,
        relationships=relationships,
    )


class TestQueryLayerForwardQueries:
    """Tests for forward relationship queries."""

    @pytest.fixture
    def query_layer(self):
        model = build_test_repository()
        return QueryLayer(model)

    def test_get_calls_forward(self, query_layer):
        """Test get_calls - what does main() call?"""
        calls = query_layer.get_calls("func_main")
        assert len(calls) == 2
        assert "func_helper" in calls
        assert "func_util" in calls

    def test_get_calls_no_calls(self, query_layer):
        """Test get_calls when function makes no calls."""
        calls = query_layer.get_calls("func_nonexistent")
        assert calls == []

    def test_get_imports_forward(self, query_layer):
        """Test get_imports - what does main.py import?"""
        imports = query_layer.get_imports("file_main_py")
        assert len(imports) == 2
        assert "file_utils_py" in imports
        assert "file_models_py" in imports

    def test_get_dependencies_forward(self, query_layer):
        """Test get_dependencies - what does main.py depend on?"""
        deps = query_layer.get_dependencies("file_main_py")
        assert len(deps) == 2
        assert "file_utils_py" in deps
        assert "file_models_py" in deps

    def test_get_uses_forward(self, query_layer):
        """Test get_uses - what does main() use?"""
        uses = query_layer.get_uses("func_main")
        assert len(uses) == 1
        assert "class_derived" in uses

    def test_get_inherits_forward(self, query_layer):
        """Test get_inherits - what does DerivedClass inherit from?"""
        inherits = query_layer.get_inherits("class_derived")
        assert len(inherits) == 1
        assert "class_base" in inherits

    def test_get_implements_forward(self, query_layer):
        """Test get_implements - what does DerivedClass implement?"""
        implements = query_layer.get_implements("class_derived")
        assert len(implements) == 1
        assert "interface_serializable" in implements


class TestQueryLayerReverseQueries:
    """Tests for reverse (bidirectional) relationship queries."""

    @pytest.fixture
    def query_layer(self):
        model = build_test_repository()
        return QueryLayer(model)

    def test_get_called_by_reverse(self, query_layer):
        """Test get_called_by - what calls helper()?"""
        callers = query_layer.get_called_by("func_helper")
        assert len(callers) == 1
        assert "func_main" in callers

    def test_get_callers_alias(self, query_layer):
        """Test get_callers alias for get_called_by."""
        callers1 = query_layer.get_called_by("func_util")
        callers2 = query_layer.get_callers("func_util")
        assert callers1 == callers2

    def test_get_imported_by_reverse(self, query_layer):
        """Test get_imported_by - what imports utils.py?"""
        importers = query_layer.get_imported_by("file_utils_py")
        assert len(importers) == 1
        assert "file_main_py" in importers

    def test_get_importers_alias(self, query_layer):
        """Test get_importers alias for get_imported_by."""
        importers1 = query_layer.get_imported_by("file_models_py")
        importers2 = query_layer.get_importers("file_models_py")
        assert importers1 == importers2

    def test_get_depended_by_reverse(self, query_layer):
        """Test get_depended_by - what depends on models.py?"""
        depended = query_layer.get_depended_by("file_models_py")
        assert len(depended) == 1
        assert "file_main_py" in depended

    def test_get_dependent_files_alias(self, query_layer):
        """Test get_dependent_files alias for get_depended_by."""
        deps1 = query_layer.get_depended_by("file_utils_py")
        deps2 = query_layer.get_dependent_files("file_utils_py")
        assert deps1 == deps2

    def test_get_used_by_reverse(self, query_layer):
        """Test get_used_by - what uses DerivedClass?"""
        users = query_layer.get_used_by("class_derived")
        assert len(users) == 1
        assert "func_main" in users

    def test_get_users_alias(self, query_layer):
        """Test get_users alias for get_used_by."""
        users1 = query_layer.get_used_by("class_another")
        users2 = query_layer.get_users("class_another")
        assert users1 == users2

    def test_get_extended_by_reverse(self, query_layer):
        """Test get_extended_by - what extends BaseClass?"""
        subclasses = query_layer.get_extended_by("class_base")
        assert len(subclasses) == 2
        assert "class_derived" in subclasses
        assert "class_another" in subclasses

    def test_get_subclasses_alias(self, query_layer):
        """Test get_subclasses alias for get_extended_by."""
        subs1 = query_layer.get_extended_by("class_base")
        subs2 = query_layer.get_subclasses("class_base")
        assert subs1 == subs2

    def test_get_implementers_reverse(self, query_layer):
        """Test get_implementers - what implements Serializable?"""
        implementers = query_layer.get_implementers("interface_serializable")
        assert len(implementers) == 2
        assert "class_derived" in implementers
        assert "class_another" in implementers

    def test_get_implementations_alias(self, query_layer):
        """Test get_implementations alias for get_implementers."""
        impl1 = query_layer.get_implementers("interface_serializable")
        impl2 = query_layer.get_implementations("interface_serializable")
        assert impl1 == impl2


class TestQueryLayerRelationshipMetadata:
    """Tests for relationship queries with metadata."""

    @pytest.fixture
    def query_layer(self):
        model = build_test_repository()
        return QueryLayer(model)

    def test_get_forward_relationships_no_filter(self, query_layer):
        """Test get_forward_relationships - all outgoing relationships."""
        rels = query_layer.get_forward_relationships("func_main")
        assert len(rels) == 3  # 2 CALLS + 1 USES
        rel_types = {r["type"] for r in rels}
        assert "CALLS" in rel_types
        assert "USES" in rel_types

    def test_get_forward_relationships_with_filter(self, query_layer):
        """Test get_forward_relationships with type filter."""
        rels = query_layer.get_forward_relationships("func_main", rel_type="CALLS")
        assert len(rels) == 2
        for rel in rels:
            assert rel["type"] == "CALLS"

    def test_get_reverse_relationships_no_filter(self, query_layer):
        """Test get_reverse_relationships - all incoming relationships."""
        rels = query_layer.get_reverse_relationships("func_util")
        assert len(rels) == 2  # called by main and helper
        for rel in rels:
            assert rel["type"] == "CALLS"
            assert rel["source_id"] in ["func_main", "func_helper"]

    def test_get_reverse_relationships_with_filter(self, query_layer):
        """Test get_reverse_relationships with type filter."""
        rels = query_layer.get_reverse_relationships("file_models_py", rel_type="IMPORTS")
        assert len(rels) == 2
        for rel in rels:
            assert rel["type"] == "IMPORTS"

    def test_relationship_metadata_preserved(self, query_layer):
        """Test that metadata is preserved in relationship queries."""
        rels = query_layer.get_forward_relationships("func_main", rel_type="CALLS")
        for rel in rels:
            assert "metadata" in rel
            assert isinstance(rel["metadata"], dict)
            assert "line" in rel["metadata"] or "reason" in rel["metadata"]


class TestQueryLayerEmptyResults:
    """Tests for empty and NULL result handling."""

    @pytest.fixture
    def query_layer(self):
        model = build_test_repository()
        return QueryLayer(model)

    def test_nonexistent_entity(self, query_layer):
        """Test queries on nonexistent entities return empty lists."""
        assert query_layer.get_calls("nonexistent") == []
        assert query_layer.get_called_by("nonexistent") == []
        assert query_layer.get_imports("nonexistent") == []
        assert query_layer.get_imported_by("nonexistent") == []

    def test_entity_with_no_incoming_relationships(self, query_layer):
        """Test entity with no incoming relationships."""
        # func_main is the top-level function, nothing calls it
        callers = query_layer.get_called_by("func_main")
        assert callers == []

    def test_entity_with_no_outgoing_relationships(self, query_layer):
        """Test entity with no outgoing relationships."""
        # interface_serializable has no outgoing relationships
        uses = query_layer.get_uses("interface_serializable")
        assert uses == []

    def test_empty_forward_relationships(self, query_layer):
        """Test get_forward_relationships with no matches."""
        rels = query_layer.get_forward_relationships("interface_serializable")
        assert rels == []

    def test_empty_reverse_relationships(self, query_layer):
        """Test get_reverse_relationships with no matches."""
        rels = query_layer.get_reverse_relationships("func_main", rel_type="IMPLEMENTS")
        assert rels == []


class TestQueryLayerBackwardsCompatibility:
    """Tests to ensure backward compatibility with existing QueryLayer methods."""

    @pytest.fixture
    def query_layer(self):
        model = build_test_repository()
        return QueryLayer(model)

    def test_find_function_still_works(self, query_layer):
        """Test that find_function still works as before."""
        functions = query_layer.find_function("main")
        assert len(functions) == 1
        assert functions[0].id == "func_main"

    def test_get_class_still_works(self, query_layer):
        """Test that get_class still works as before."""
        classes = query_layer.get_class("BaseClass")
        assert len(classes) == 1
        assert classes[0].id == "class_base"

    def test_get_file_still_works(self, query_layer):
        """Test that get_file still works as before."""
        file = query_layer.get_file("file_main_py")
        assert file is not None
        assert file.name == "main.py"

    def test_get_classes_in_file_still_works(self, query_layer):
        """Test that get_classes_in_file still works as before."""
        classes = query_layer.get_classes_in_file("file_models_py")
        assert len(classes) == 2
        class_names = {c.name for c in classes}
        assert "BaseClass" in class_names
        assert "AnotherClass" in class_names

    def test_get_files_still_works(self, query_layer):
        """Test that get_files still works as before."""
        files = query_layer.get_files()
        assert len(files) == 3
        file_names = {f.name for f in files}
        assert "main.py" in file_names
        assert "utils.py" in file_names
        assert "models.py" in file_names

    def test_search_entities_still_works(self, query_layer):
        """Test that search_entities still works as before."""
        results = query_layer.search_entities("Base")
        assert len(results) > 0
        result_names = [r["name"] for r in results]
        assert "BaseClass" in result_names


class TestQueryLayerBidirectionalConsistency:
    """Tests to verify consistency of forward and reverse queries."""

    @pytest.fixture
    def query_layer(self):
        model = build_test_repository()
        return QueryLayer(model)

    def test_calls_bidirectional_consistency(self, query_layer):
        """Verify that A->B in forward CALLS means B's get_called_by includes A."""
        main_calls = query_layer.get_calls("func_main")
        for target in main_calls:
            callers = query_layer.get_called_by(target)
            assert "func_main" in callers

    def test_imports_bidirectional_consistency(self, query_layer):
        """Verify that A->B in forward IMPORTS means B's get_imported_by includes A."""
        main_imports = query_layer.get_imports("file_main_py")
        for target in main_imports:
            importers = query_layer.get_imported_by(target)
            assert "file_main_py" in importers

    def test_inherits_bidirectional_consistency(self, query_layer):
        """Verify that A->B in forward INHERITS means B's get_extended_by includes A."""
        derived_inherits = query_layer.get_inherits("class_derived")
        for target in derived_inherits:
            subclasses = query_layer.get_extended_by(target)
            assert "class_derived" in subclasses

    def test_implements_bidirectional_consistency(self, query_layer):
        """Verify that A->B in forward IMPLEMENTS means B's get_implementers includes A."""
        derived_implements = query_layer.get_implements("class_derived")
        for target in derived_implements:
            implementers = query_layer.get_implementers(target)
            assert "class_derived" in implementers


class TestQueryLayerComplexScenarios:
    """Tests for complex query scenarios."""

    @pytest.fixture
    def query_layer(self):
        model = build_test_repository()
        return QueryLayer(model)

    def test_transitive_call_chain(self, query_layer):
        """Test tracing a call chain: main -> helper -> utility_function."""
        # main calls helper
        main_calls = query_layer.get_calls("func_main")
        assert "func_helper" in main_calls

        # helper calls utility_function
        helper_calls = query_layer.get_calls("func_helper")
        assert "func_util" in helper_calls

        # utility_function has no calls
        util_calls = query_layer.get_calls("func_util")
        assert util_calls == []

    def test_multiple_inheritance_hierarchy(self, query_layer):
        """Test multiple classes inheriting from same base."""
        base_extensions = query_layer.get_extended_by("class_base")
        assert len(base_extensions) == 2
        assert "class_derived" in base_extensions
        assert "class_another" in base_extensions

    def test_multiple_implementations(self, query_layer):
        """Test multiple classes implementing same interface."""
        interface_implementations = query_layer.get_implementers("interface_serializable")
        assert len(interface_implementations) == 2
        assert "class_derived" in interface_implementations
        assert "class_another" in interface_implementations

    def test_mixed_relationship_types(self, query_layer):
        """Test entity with multiple different relationship types."""
        # main.py has IMPORTS, DEPENDS_ON relationships
        forward_rels = query_layer.get_forward_relationships("file_main_py")
        rel_types = {r["type"] for r in forward_rels}
        assert "IMPORTS" in rel_types
        assert "DEPENDS_ON" in rel_types
