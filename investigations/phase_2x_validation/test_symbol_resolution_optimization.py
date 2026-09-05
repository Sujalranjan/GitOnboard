#!/usr/bin/env python3
"""
Simple inline test to verify symbol resolution optimization.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.intelligence.engine.analyzers.resolution import SymbolIndex, resolve_reference
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.metadata import RepositoryMetadata

def test_imports_by_file_index():
    """Verify imports_by_file index is built correctly."""
    repo = RepositoryModel(
        metadata=RepositoryMetadata(name="test_repo", path="/tmp/test", languages=["Python"])
    )

    # Create test entities
    file_a = Entity(
        id="file_a",
        type=EntityType.FILE,
        name="a.py",
        qualified_name="a.py",
        location={"file": "a.py", "line": 1},
        metadata={}
    )
    file_b = Entity(
        id="file_b",
        type=EntityType.FILE,
        name="b.py",
        qualified_name="b.py",
        location={"file": "b.py", "line": 1},
        metadata={}
    )
    repo.entities["file_a"] = file_a
    repo.entities["file_b"] = file_b

    # Add import relationship: file_a imports file_b
    import_rel = Relationship(
        id="import_1",
        type=RelationshipType.IMPORTS,
        source_id="file_a",
        target_id="file_b"
    )
    repo.relationships["import_1"] = import_rel

    # Build index
    index = SymbolIndex(repo)

    # Verify imports_by_file is populated
    assert "file_a" in index.imports_by_file, "file_a not in imports_by_file"
    assert "file_b" in index.imports_by_file["file_a"], "file_b not in imports for file_a"
    print("✓ Test passed: imports_by_file index built correctly")

def test_symbols_by_module_index():
    """Verify symbols_by_module index is built correctly."""
    repo = RepositoryModel(
        metadata=RepositoryMetadata(name="test_repo", path="/tmp/test", languages=["Python"])
    )

    # Create entities
    file_a = Entity(
        id="file_a",
        type=EntityType.FILE,
        name="a.py",
        qualified_name="a.py",
        metadata={}
    )
    func_a = Entity(
        id="func_a",
        type=EntityType.FUNCTION,
        name="foo",
        qualified_name="a.foo",
        location={"file": "a.py", "line": 5},
        metadata={"file_id": "a.py"}
    )
    repo.entities["file_a"] = file_a
    repo.entities["func_a"] = func_a

    index = SymbolIndex(repo)

    # Verify symbols_by_module is populated
    assert "a.py" in index.symbols_by_module, "a.py not in symbols_by_module"
    assert "foo" in index.symbols_by_module["a.py"], "foo not in symbols for a.py"
    assert "func_a" in index.symbols_by_module["a.py"]["foo"], "func_a not in foo candidates"
    print("✓ Test passed: symbols_by_module index built correctly")

def test_resolve_reference_with_optimization():
    """Verify resolve_reference still works with optimized Strategy 3."""
    repo = RepositoryModel(
        metadata=RepositoryMetadata(name="test_repo", path="/tmp/test", languages=["Python"])
    )

    # Create entities
    file_a = Entity(
        id="file_a",
        type=EntityType.FILE,
        name="a.py",
        qualified_name="a.py",
        metadata={}
    )
    file_b = Entity(
        id="file_b",
        type=EntityType.FILE,
        name="b.py",
        qualified_name="b.py",
        metadata={}
    )
    func_b = Entity(
        id="func_b",
        type=EntityType.FUNCTION,
        name="foo",
        qualified_name="b.foo",
        metadata={"file_id": "b.py"}
    )
    repo.entities["file_a"] = file_a
    repo.entities["file_b"] = file_b
    repo.entities["func_b"] = func_b

    # Add import: file_a imports file_b
    import_rel = Relationship(
        id="import_1",
        type=RelationshipType.IMPORTS,
        source_id="file_a",
        target_id="file_b"
    )
    repo.relationships["import_1"] = import_rel

    # Resolve reference: "foo" in context of file_a
    index = SymbolIndex(repo)
    result = resolve_reference(repo, "a.py", "foo", None, index)

    # Should find func_b via import resolution (Strategy 3)
    assert result == "func_b", f"Expected func_b, got {result}"
    print("✓ Test passed: resolve_reference with optimized Strategy 3 works correctly")

def test_file_scope_resolution_unchanged():
    """Verify file-scope resolution (Strategy 2) still works."""
    repo = RepositoryModel(
        metadata=RepositoryMetadata(name="test_repo", path="/tmp/test", languages=["Python"])
    )

    # Create entities
    file_a = Entity(
        id="file_a",
        type=EntityType.FILE,
        name="a.py",
        qualified_name="a.py",
        metadata={}
    )
    func_a = Entity(
        id="func_a",
        type=EntityType.FUNCTION,
        name="bar",
        qualified_name="a.bar",
        metadata={"file_id": "a.py"}
    )
    repo.entities["file_a"] = file_a
    repo.entities["func_a"] = func_a

    # Initialize symbols_by_file manually (would normally be done in build())
    index = SymbolIndex(repo)

    # Resolve "bar" in context of a.py (should find func_a in file scope)
    result = resolve_reference(repo, "a.py", "bar", None, index)

    assert result == "func_a", f"Expected func_a, got {result}"
    print("✓ Test passed: file-scope resolution (Strategy 2) unchanged")

if __name__ == "__main__":
    try:
        test_imports_by_file_index()
        test_symbols_by_module_index()
        test_resolve_reference_with_optimization()
        test_file_scope_resolution_unchanged()
        print("\n" + "="*60)
        print("✓✓✓ ALL TESTS PASSED ✓✓✓")
        print("="*60)
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
