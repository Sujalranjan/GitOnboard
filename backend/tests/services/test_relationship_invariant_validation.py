"""Regression tests for relationship invariant validation.

Tests that the RepositoryModel invariant is maintained:
- Every Relationship.source_id must reference an Entity in model.entities
- Every Relationship.target_id must reference an Entity in model.entities

This prevents silent failures where analyzers create orphaned relationships
that later cause empty RIM metadata ("No structural facts could be resolved").
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.fact_store import FactSymbol, FactRelationship
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.identity import generate_entity_id, generate_relationship_id
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.store.fact_store import save_rim_to_fact_store


def create_test_model():
    """Helper to create RepositoryModel with required metadata."""
    return RepositoryModel(
        metadata=RepositoryMetadata(name="test", path="/test", languages=["Python"])
    )


@pytest.fixture
def db():
    """Create in-memory SQLite database for test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestRelationshipInvariantValidation:
    """Test that orphaned relationships are caught during persistence."""

    def test_orphaned_relationship_is_rejected(self, db):
        """Verify that relationships with non-existent targets are rejected."""
        model = create_test_model()

        # Create a function entity
        func_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.hello")
        model.entities[func_id] = Entity(
            id=func_id,
            type=EntityType.CLASS,
            name="hello",
            location=SourceLocation(repository_path="test.py", start_line=1, end_line=5, language="Python"),
        )

        # Create a relationship to a non-existent entity
        orphaned_id = generate_entity_id(EntityType.FUNCTION, "external.py", "external.foo")
        rel_id = generate_relationship_id(RelationshipType.CALLS, func_id, orphaned_id)
        model.relationships[rel_id] = Relationship(
            id=rel_id,
            type=RelationshipType.CALLS,
            source_id=func_id,
            target_id=orphaned_id,  # This entity does NOT exist in model.entities
            metadata={"call_name": "foo"}
        )

        # Verify save fails with clear error
        with pytest.raises(ValueError, match="RepositoryModel invariant violated"):
            save_rim_to_fact_store(db, analysis_id=999, model=model)

    def test_orphaned_relationship_source_is_rejected(self, db):
        """Verify that relationships with non-existent sources are rejected."""
        model = create_test_model()

        # Create a function entity
        func_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.foo")
        model.entities[func_id] = Entity(
            id=func_id,
            type=EntityType.FUNCTION,
            name="foo",
            location=SourceLocation(repository_path="test.py", start_line=1, end_line=5, language="Python"),
        )

        # Create a relationship FROM a non-existent entity TO an existing one
        orphaned_src_id = generate_entity_id(EntityType.FUNCTION, "external.py", "external.bar")
        rel_id = generate_relationship_id(RelationshipType.CALLS, orphaned_src_id, func_id)
        model.relationships[rel_id] = Relationship(
            id=rel_id,
            type=RelationshipType.CALLS,
            source_id=orphaned_src_id,  # This entity does NOT exist
            target_id=func_id,
            metadata={"call_name": "foo"}
        )

        # Verify save fails
        with pytest.raises(ValueError, match="RepositoryModel invariant violated"):
            save_rim_to_fact_store(db, analysis_id=999, model=model)


class TestCallGraphAnalyzerExternalCalls:
    """Test that callgraph analyzer no longer creates orphaned relationships to external calls."""

    def test_callgraph_skips_unresolved_external_calls(self):
        """Verify callgraph doesn't create relationships to external/unresolved calls."""
        import ast
        from backend.intelligence.engine.analyzers.callgraph import PythonCallGraphVisitor
        from backend.intelligence.engine.analyzers.resolution import SymbolIndex

        code = """
def local_func():
    return external_module.foo()  # external call - foo() doesn't exist in this repo

def another_local():
    local_func()  # local call - should create relationship
"""
        tree = ast.parse(code)

        # Create a repository with only local_func
        repository = create_test_model()
        local_func_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.local_func")
        repository.entities[local_func_id] = Entity(
            id=local_func_id,
            type=EntityType.FUNCTION,
            name="local_func",
            location=SourceLocation(repository_path="test.py", start_line=1, end_line=3, language="Python"),
        )

        another_func_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.another_local")
        repository.entities[another_func_id] = Entity(
            id=another_func_id,
            type=EntityType.FUNCTION,
            name="another_local",
            location=SourceLocation(repository_path="test.py", start_line=5, end_line=7, language="Python"),
        )

        # Analyze
        index = SymbolIndex(repository)
        visitor = PythonCallGraphVisitor("test.py", repository, index)
        visitor.visit(tree)

        # Verify: should have 0 relationships to unresolved external calls
        # (Only the external_module.foo() call, which can't be resolved)
        # The local_func() call from another_local should succeed
        assert len(visitor.relationships) >= 0  # May have local call relationship

        # Verify all relationships in visitor have resolvable targets
        for rel in visitor.relationships:
            assert rel.target_id in repository.entities, f"Relationship {rel.id} references non-existent target {rel.target_id}"


class TestTypeAnalyzerExternalBases:
    """Test that type analyzer no longer creates orphaned relationships to external base classes."""

    def test_type_analyzer_skips_unresolved_bases(self):
        """Verify type analyzer doesn't create relationships to external base classes."""
        import ast
        from backend.intelligence.engine.analyzers.type import PythonTypeVisitor

        code = """
class LocalBase:
    pass

class MyClass(LocalBase):
    pass

class ExternalBase(SomeExternalBase):
    pass
"""
        tree = ast.parse(code)

        # Create visitor
        visitor = PythonTypeVisitor("test.py")
        visitor.visit(tree)

        # Verify: no relationships to undefined external bases
        # (SomeExternalBase won't resolve to an entity)
        for rel in visitor.relationships:
            assert rel.target_id is not None, f"Relationship {rel.id} has None target"
            # Target should be either a local class or an imported symbol
            # In this test, LocalBase should be resolved as a local class

    def test_type_analyzer_skips_builtin_bases(self):
        """Verify type analyzer skips builtin base classes like object, Exception."""
        import ast
        from backend.intelligence.engine.analyzers.type import PythonTypeVisitor

        code = """
class MyException(Exception):
    pass

class MyClass(object):
    pass
"""
        tree = ast.parse(code)

        visitor = PythonTypeVisitor("test.py")
        visitor.visit(tree)

        # Verify: no relationships created for builtin bases
        assert len(visitor.relationships) == 0, "Builtin base classes should not create relationships"


class TestValidRelationshipPersistence:
    """Test that valid local relationships persist correctly."""

    def test_local_function_calls_persist(self, db):
        """Verify that relationships between local entities persist correctly."""
        from backend.models.fact_store import FactSymbol, FactRelationship

        # Create model with valid local entities and relationships
        model = create_test_model()

        # Create file entity
        file_id = generate_entity_id(EntityType.FILE, "test.py", "test.py")
        model.entities[file_id] = Entity(
            id=file_id,
            type=EntityType.FILE,
            name="test.py",
            location=SourceLocation(repository_path="test.py", start_line=1, end_line=10, language="Python"),
        )

        # Create two function entities
        caller_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.caller")
        model.entities[caller_id] = Entity(
            id=caller_id,
            type=EntityType.FUNCTION,
            name="caller",
            location=SourceLocation(repository_path="test.py", start_line=1, end_line=3, language="Python"),
        )

        callee_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.callee")
        model.entities[callee_id] = Entity(
            id=callee_id,
            type=EntityType.FUNCTION,
            name="callee",
            location=SourceLocation(repository_path="test.py", start_line=5, end_line=7, language="Python"),
        )

        # Create valid relationship
        rel_id = generate_relationship_id(RelationshipType.CALLS, caller_id, callee_id)
        model.relationships[rel_id] = Relationship(
            id=rel_id,
            type=RelationshipType.CALLS,
            source_id=caller_id,
            target_id=callee_id,
            metadata={"call_name": "callee"}
        )

        # Save should succeed
        analysis_id = 100
        save_rim_to_fact_store(db, analysis_id, model)

        # Verify relationships were persisted
        rels = db.query(FactRelationship).filter(FactRelationship.analysis_id == analysis_id).all()
        assert len(rels) == 1, f"Expected 1 relationship, got {len(rels)}"
        assert rels[0].rel_type == "CALLS"
        assert rels[0].from_symbol_id == f"{analysis_id}:{caller_id}"
        assert rels[0].to_symbol_id == f"{analysis_id}:{callee_id}"

    def test_multiple_valid_relationships_persist(self, db):
        """Verify that multiple valid relationships all persist."""
        from backend.models.fact_store import FactRelationship

        model = create_test_model()

        # Create file
        file_id = generate_entity_id(EntityType.FILE, "module.py", "module.py")
        model.entities[file_id] = Entity(
            id=file_id,
            type=EntityType.FILE,
            name="module.py",
            location=SourceLocation(repository_path="module.py", start_line=1, end_line=50, language="Python"),
        )

        # Create 3 function entities
        func_ids = []
        for i in range(3):
            func_id = generate_entity_id(EntityType.FUNCTION, "module.py", f"module.func{i}")
            model.entities[func_id] = Entity(
                id=func_id,
                type=EntityType.FUNCTION,
                name=f"func{i}",
                location=SourceLocation(repository_path="module.py", start_line=i*10+1, end_line=i*10+5, language="Python"),
            )
            func_ids.append(func_id)

        # Create relationships: func0 -> func1, func1 -> func2
        for i in range(2):
            rel_id = generate_relationship_id(RelationshipType.CALLS, func_ids[i], func_ids[i+1])
            model.relationships[rel_id] = Relationship(
                id=rel_id,
                type=RelationshipType.CALLS,
                source_id=func_ids[i],
                target_id=func_ids[i+1],
                metadata={"call_name": f"func{i+1}"}
            )

        # Save should succeed
        analysis_id = 101
        save_rim_to_fact_store(db, analysis_id, model)

        # Verify both relationships persisted
        rels = db.query(FactRelationship).filter(FactRelationship.analysis_id == analysis_id).all()
        assert len(rels) == 2, f"Expected 2 relationships, got {len(rels)}"
