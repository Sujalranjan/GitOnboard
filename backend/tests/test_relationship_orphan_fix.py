"""
Test: Relationship ID Resolution (Phase 2L.9 Fix Verification)

Verify that:
1. All FILE entities are saved as symbols
2. All relationships have valid source/target in symbols table
3. Zero orphaned relationships (from_symbol_id not found)
"""

import pytest
from sqlalchemy.orm import Session
from sqlalchemy import and_, select

from backend.database import SessionLocal
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from backend.models.repository import Repository, Analysis
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.identity import generate_entity_id, generate_relationship_id
from backend.intelligence.store.fact_store import save_rim_to_fact_store


@pytest.fixture
def db():
    """Create test database session"""
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def test_repo(db: Session):
    """Create test repository"""
    repo = Repository(
        url="https://github.com/test/repo",
        default_branch="main",
        user_id=1
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@pytest.fixture
def test_analysis(db: Session, test_repo):
    """Create test analysis"""
    analysis = Analysis(repository_id=test_repo.id)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def test_files_included_in_symbols(db: Session, test_analysis):
    """
    Test that FILE entities are saved as symbols.

    This verifies the fix for the orphaned relationships issue.
    Previously, FILE entities were excluded from symbols table,
    causing relationship foreign keys to fail.
    """

    # Build test RIM with files and symbols
    rim = RepositoryModel(
        name="test_repo",
        languages=["python"],
        metadata={},
    )

    # Create FILE entity
    file_id = generate_entity_id(EntityType.FILE, "main.py", "main.py")
    file_entity = Entity(
        id=file_id,
        type=EntityType.FILE,
        name="main.py",
        qualified_name="main.py",
        location=SourceLocation(repository_path="main.py", start_line=1, end_line=100),
        metadata={}
    )
    rim.entities[file_id] = file_entity

    # Create FUNCTION entity
    func_id = generate_entity_id(EntityType.FUNCTION, "main.py", "main.process")
    func_entity = Entity(
        id=func_id,
        type=EntityType.FUNCTION,
        name="process",
        qualified_name="main.process",
        location=SourceLocation(
            repository_path="main.py",
            start_line=5,
            end_line=20
        ),
        metadata={"file_id": file_id}
    )
    rim.entities[func_id] = func_entity

    # Create relationship: FILE DECLARES FUNCTION
    rel_id = generate_relationship_id(RelationshipType.DECLARES, file_id, func_id)
    rel = Relationship(
        id=rel_id,
        type=RelationshipType.DECLARES,
        source_id=file_id,    # FILE is source
        target_id=func_id,
        metadata={}
    )
    rim.relationships[rel_id] = rel

    # Save to database
    save_rim_to_fact_store(db, test_analysis.id, rim)

    # VERIFY: FILE entity saved as symbol
    file_symbol = db.query(FactSymbol).filter_by(id=f"{test_analysis.id}:{file_id}").first()
    assert file_symbol is not None, "FILE entity should be saved as symbol"
    assert file_symbol.symbol_type == "file"
    assert file_symbol.name == "main.py"

    # VERIFY: FUNCTION entity saved as symbol
    func_symbol = db.query(FactSymbol).filter_by(id=f"{test_analysis.id}:{func_id}").first()
    assert func_symbol is not None, "FUNCTION entity should be saved as symbol"
    assert func_symbol.symbol_type == "function"

    # VERIFY: Relationship saved with correct foreign keys
    rel_record = db.query(FactRelationship).filter_by(analysis_id=test_analysis.id).first()
    assert rel_record is not None, "Relationship should be saved"
    assert rel_record.from_symbol_id == f"{test_analysis.id}:{file_id}"
    assert rel_record.to_symbol_id == f"{test_analysis.id}:{func_id}"

    # VERIFY: Both foreign keys resolve to existing symbols
    from_symbol = db.query(FactSymbol).filter_by(
        id=rel_record.from_symbol_id
    ).first()
    assert from_symbol is not None, f"from_symbol_id {rel_record.from_symbol_id} should exist in symbols"

    to_symbol = db.query(FactSymbol).filter_by(
        id=rel_record.to_symbol_id
    ).first()
    assert to_symbol is not None, f"to_symbol_id {rel_record.to_symbol_id} should exist in symbols"

    print("✅ FILES properly included in symbols table")
    print("✅ Relationship foreign keys resolve correctly")


def test_no_orphaned_relationships(db: Session, test_analysis):
    """
    Test that there are zero orphaned relationships.

    Orphaned = relationship references symbol/file that doesn't exist in symbols table.
    """

    # Build test RIM with multiple entities and relationships
    rim = RepositoryModel(name="test_repo", languages=["python"], metadata={})

    # Create multiple files
    files = {}
    for i, fname in enumerate(["main.py", "utils.py", "models.py"]):
        file_id = generate_entity_id(EntityType.FILE, fname, fname)
        file_entity = Entity(
            id=file_id,
            type=EntityType.FILE,
            name=fname,
            qualified_name=fname,
            location=SourceLocation(repository_path=fname),
            metadata={}
        )
        rim.entities[file_id] = file_entity
        files[fname] = file_id

    # Create symbols in each file
    symbols = {}
    for fname, file_id in files.items():
        for j in range(3):
            sym_id = generate_entity_id(
                EntityType.FUNCTION,
                fname,
                f"{fname.replace('.py', '')}_func{j}"
            )
            sym_entity = Entity(
                id=sym_id,
                type=EntityType.FUNCTION,
                name=f"func{j}",
                qualified_name=f"{fname.replace('.py', '')}_func{j}",
                location=SourceLocation(repository_path=fname, start_line=10+j*5),
                metadata={"file_id": file_id}
            )
            rim.entities[sym_id] = sym_entity
            symbols[sym_id] = (file_id, fname)

    # Create relationships: files import each other
    sym_list = list(symbols.keys())
    for i in range(min(10, len(sym_list)-1)):
        source_id = sym_list[i]
        target_id = sym_list[i+1]

        rel_id = generate_relationship_id(RelationshipType.CALLS, source_id, target_id)
        rel = Relationship(
            id=rel_id,
            type=RelationshipType.CALLS,
            source_id=source_id,
            target_id=target_id,
            metadata={}
        )
        rim.relationships[rel_id] = rel

    # Also add file-to-file relationships
    file_ids = list(files.values())
    for i in range(len(file_ids)-1):
        rel_id = generate_relationship_id(
            RelationshipType.IMPORTS,
            file_ids[i],
            file_ids[i+1]
        )
        rel = Relationship(
            id=rel_id,
            type=RelationshipType.IMPORTS,
            source_id=file_ids[i],
            target_id=file_ids[i+1],
            metadata={}
        )
        rim.relationships[rel_id] = rel

    # Save to database
    save_rim_to_fact_store(db, test_analysis.id, rim)

    # VERIFY: Count total relationships
    total_rels = db.query(FactRelationship).filter_by(
        analysis_id=test_analysis.id
    ).count()
    print(f"Total relationships: {total_rels}")

    # VERIFY: Count orphaned relationships (from_symbol_id doesn't exist)
    orphaned_from = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == test_analysis.id,
        ~select(1).select_from(FactSymbol).where(
            FactSymbol.id == FactRelationship.from_symbol_id
        ).correlate(FactRelationship).exists()
    ).count()

    orphaned_to = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == test_analysis.id,
        ~select(1).select_from(FactSymbol).where(
            FactSymbol.id == FactRelationship.to_symbol_id
        ).correlate(FactRelationship).exists()
    ).count()

    print(f"Orphaned from_symbol_id: {orphaned_from}")
    print(f"Orphaned to_symbol_id: {orphaned_to}")

    assert orphaned_from == 0, f"Found {orphaned_from} relationships with missing from_symbol_id"
    assert orphaned_to == 0, f"Found {orphaned_to} relationships with missing to_symbol_id"

    print("✅ Zero orphaned relationships")
    print("✅ All relationship foreign keys resolve")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
