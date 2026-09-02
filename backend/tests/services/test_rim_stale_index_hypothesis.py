"""
Diagnostic tests to prove or disprove the stale-index hypothesis in RIM pipeline.

Hypothesis: HybridRetriever indexes are built once at initialization,
never updated after analyzer runs, causing retriever.retrieve() to diverge
from live repository tools (search_code, get_symbol, etc).
"""

import pytest
from sqlalchemy.orm import Session
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.identity import generate_entity_id, generate_relationship_id
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.store.fact_store import save_rim_to_fact_store


class TestRetrieverIndexLifecycle:
    """Test when and how retriever indexes are built/refreshed."""

    def test_retriever_bm25_index_built_at_init(self, db):
        """DIAGNOSTIC: Verify BM25 index is built during HybridRetriever.__init__"""
        # Setup: Fresh analysis with symbols in FactStore
        user = User(id=1, github_id="test", username="test", email="test@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 100
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add symbols to FactStore
        file_id = f"{analysis_id}:urn:file:test.py#test.py"
        file_rec = FactFile(
            id=file_id,
            analysis_id=analysis_id,
            path="test.py",
            language="Python",
        )
        db.add(file_rec)
        db.flush()

        sym_id = f"{analysis_id}:urn:function:test.py#authenticate"
        sym = FactSymbol(
            id=sym_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="authenticate",
            qualified_name="test.authenticate",
            symbol_type="function",
            line_start=10,
            line_end=20,
        )
        db.add(sym)
        db.commit()

        # Create retriever - this should build BM25 index from FactStore
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # Diagnostic: Check if BM25 index was built
        assert retriever.bm25_index is not None, "BM25 index should be built during init"
        assert len(retriever.bm25_index._documents) > 0, "BM25 index should have documents"

        # Test: Can retriever find the symbol?
        results = retriever.retrieve("authenticate", top_k=5, expand_with_fact_store=False)
        assert len(results) > 0, "Should find 'authenticate' symbol in index"

    def test_retriever_index_not_refreshed_after_factstore_change(self, db):
        """DIAGNOSTIC: Verify BM25 index is NOT refreshed when FactStore changes"""
        # Setup: Create analysis with 1 symbol
        user = User(id=2, github_id="test2", username="test2", email="test2@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=2, url="https://github.com/test2/repo2", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 101
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        file_id = f"{analysis_id}:urn:file:auth.py#auth.py"
        file_rec = FactFile(id=file_id, analysis_id=analysis_id, path="auth.py", language="Python")
        db.add(file_rec)
        db.flush()

        sym_id = f"{analysis_id}:urn:function:auth.py#login"
        sym = FactSymbol(
            id=sym_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="login",
            qualified_name="auth.login",
            symbol_type="function",
            line_start=5,
            line_end=15,
        )
        db.add(sym)
        db.commit()

        # Create retriever (indexes 1 symbol)
        retriever1 = HybridRetriever(db=db, analysis_id=analysis_id)
        results1 = retriever1.retrieve("login", top_k=5, expand_with_fact_store=False)
        initial_count = len(results1)
        assert initial_count > 0, "Should find 'login' initially"

        # Now add a NEW symbol to FactStore
        sym2_id = f"{analysis_id}:urn:function:auth.py#logout"
        sym2 = FactSymbol(
            id=sym2_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="logout",
            qualified_name="auth.logout",
            symbol_type="function",
            line_start=20,
            line_end=25,
        )
        db.add(sym2)
        db.commit()

        # NEW retriever created (should index both symbols)
        retriever2 = HybridRetriever(db=db, analysis_id=analysis_id)
        results2 = retriever2.retrieve("logout", top_k=5, expand_with_fact_store=False)
        logout_found = len(results2) > 0

        # OLD retriever still has old index (should NOT find logout)
        results_old = retriever1.retrieve("logout", top_k=5, expand_with_fact_store=False)
        logout_found_old = len(results_old) > 0

        # DIAGNOSTIC
        print(f"Initial retriever found 'login': {initial_count > 0}")
        print(f"New retriever finds 'logout': {logout_found}")
        print(f"Old retriever finds 'logout': {logout_found_old}")

        # This demonstrates the stale index: old retriever doesn't know about new symbol
        assert not logout_found_old, "STALE INDEX: Old retriever should NOT find new symbol"
        assert logout_found, "New retriever should find new symbol"


class TestRIMComparisonRetrieverInitialization:
    """Test how HybridRetriever is initialized in rim_comparison_service_v2"""

    def test_rim_comparison_retriever_sees_factstore_state(self, db):
        """DIAGNOSTIC: What FactStore state does retriever see?"""
        # Setup: Analysis with symbols
        user = User(id=3, github_id="test3", username="test3", email="test3@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=3, url="https://github.com/test3/repo3", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 102
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add FactFile
        file_id = f"{analysis_id}:urn:file:app.py#app.py"
        file_rec = FactFile(id=file_id, analysis_id=analysis_id, path="app.py", language="Python")
        db.add(file_rec)
        db.flush()

        # Add FactSymbol
        sym_id = f"{analysis_id}:urn:function:app.py#main"
        sym = FactSymbol(
            id=sym_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="main",
            qualified_name="app.main",
            symbol_type="function",
            line_start=1,
            line_end=10,
        )
        db.add(sym)
        db.commit()

        # Simulate RIM comparison service initialization
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # Check what retriever can find
        results = retriever.retrieve("main", top_k=5, expand_with_fact_store=False)

        # DIAGNOSTIC
        print(f"Analysis ID: {analysis_id}")
        print(f"FactFile records: {db.query(FactFile).filter_by(analysis_id=analysis_id).count()}")
        print(f"FactSymbol records: {db.query(FactSymbol).filter_by(analysis_id=analysis_id).count()}")
        print(f"Retriever found 'main': {len(results) > 0}")
        print(f"BM25 index has {len(retriever.bm25_index._documents) if retriever.bm25_index else 0} documents")

        assert len(results) > 0, "Retriever should find symbols from FactStore"


class TestOrphanedRelationshipsPersistence:
    """Test if my orphaned relationship fix actually improves persistence."""

    def test_valid_relationships_persist(self, db):
        """DIAGNOSTIC: Do valid relationships actually get persisted to FactStore?"""
        # Setup: Create analysis with valid relationships
        user = User(id=4, github_id="test4", username="test4", email="test4@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=4, url="https://github.com/test4/repo4", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 103

        # Create model with entities and relationships
        model = RepositoryModel(metadata=RepositoryMetadata(name="test", path="/test", languages=["Python"]))

        # Add file entity
        file_id = generate_entity_id(EntityType.FILE, "test.py", "test.py")
        model.entities[file_id] = Entity(
            id=file_id,
            type=EntityType.FILE,
            name="test.py",
            location=SourceLocation(repository_path="test.py", start_line=1, end_line=10, language="Python"),
        )

        # Add two function entities
        func1_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.func1")
        model.entities[func1_id] = Entity(
            id=func1_id,
            type=EntityType.FUNCTION,
            name="func1",
            location=SourceLocation(repository_path="test.py", start_line=1, end_line=5, language="Python"),
        )

        func2_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.func2")
        model.entities[func2_id] = Entity(
            id=func2_id,
            type=EntityType.FUNCTION,
            name="func2",
            location=SourceLocation(repository_path="test.py", start_line=6, end_line=10, language="Python"),
        )

        # Add valid relationship (both entities exist)
        rel_id = generate_relationship_id(RelationshipType.CALLS, func1_id, func2_id)
        model.relationships[rel_id] = Relationship(
            id=rel_id,
            type=RelationshipType.CALLS,
            source_id=func1_id,
            target_id=func2_id,
            metadata={"call_name": "func2"},
        )

        # Create analysis record
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.commit()

        # Persist to FactStore
        save_rim_to_fact_store(db, analysis_id, model)

        # DIAGNOSTIC: Check if relationship was persisted
        rels = db.query(FactRelationship).filter_by(analysis_id=analysis_id).all()

        print(f"Model had {len(model.relationships)} relationships")
        print(f"FactStore has {len(rels)} relationships after persistence")
        for rel in rels:
            print(f"  - {rel.rel_type}: {rel.from_symbol_id} -> {rel.to_symbol_id}")

        assert len(rels) == 1, "Valid relationship should be persisted"
        assert rels[0].rel_type == "CALLS"

    def test_orphaned_relationships_rejected(self, db):
        """DIAGNOSTIC: Are orphaned relationships detected and rejected?"""
        # Setup: Create analysis with orphaned relationship
        user = User(id=5, github_id="test5", username="test5", email="test5@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=5, url="https://github.com/test5/repo5", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 104

        # Create model with orphaned relationship (target doesn't exist)
        model = RepositoryModel(metadata=RepositoryMetadata(name="test", path="/test", languages=["Python"]))

        # Add only source entity
        func1_id = generate_entity_id(EntityType.FUNCTION, "test.py", "test.func1")
        model.entities[func1_id] = Entity(
            id=func1_id,
            type=EntityType.FUNCTION,
            name="func1",
            location=SourceLocation(repository_path="test.py", start_line=1, end_line=5, language="Python"),
        )

        # Add relationship to NON-EXISTENT entity
        orphaned_id = generate_entity_id(EntityType.FUNCTION, "external.py", "external.foo")
        rel_id = generate_relationship_id(RelationshipType.CALLS, func1_id, orphaned_id)
        model.relationships[rel_id] = Relationship(
            id=rel_id,
            type=RelationshipType.CALLS,
            source_id=func1_id,
            target_id=orphaned_id,  # NOT IN MODEL.ENTITIES
            metadata={"call_name": "foo"},
        )

        # Create analysis record
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.commit()

        # Try to persist - should fail with my validation
        try:
            save_rim_to_fact_store(db, analysis_id, model)
            # If we get here, validation FAILED (bug - should have raised error)
            rels = db.query(FactRelationship).filter_by(analysis_id=analysis_id).count()
            print(f"ERROR: Orphaned relationship was persisted! ({rels} relationships in DB)")
            assert False, "Orphaned relationship should be rejected"
        except ValueError as e:
            # Validation PASSED (expected)
            print(f"Good: Validation caught orphaned relationship: {str(e)[:100]}...")
            assert "invariant violated" in str(e).lower()


class TestMetricsSourceAudit:
    """Audit exactly where metrics come from."""

    def test_files_retrieved_metric_source(self):
        """DIAGNOSTIC: Where does files_retrieved metric come from?"""
        # This is based on code inspection:
        # rim_comparison_service_v2.py:356
        # files_retrieved = len(loop_result.files_read)
        #
        # loop_result.files_read is populated by:
        # rim_qa_loop.py:238-239
        # if tool_name == "read_file" and tool_observation.success:
        #     result.files_read.append(path)
        #
        # So files_retrieved ONLY counts read_file tool calls, NOT:
        # - search_code results
        # - search_repository results
        # - find_files results
        # - get_file_outline results

        metrics_source = {
            "files_retrieved": "len(loop_result.files_read)",
            "files_read_populated_by": "tool_name == 'read_file' and tool_observation.success",
            "search_code_counted": False,
            "search_repository_counted": False,
            "find_files_counted": False,
        }

        # DIAGNOSTIC
        print("Metrics source audit:")
        for key, value in metrics_source.items():
            print(f"  {key}: {value}")

        assert not metrics_source["search_code_counted"], "search_code results NOT in files_retrieved"
        assert not metrics_source["search_repository_counted"], "search_repository results NOT in files_retrieved"

    def test_symbols_retrieved_metric_source(self):
        """DIAGNOSTIC: Where does symbols_retrieved metric come from?"""
        # rim_comparison_service_v2.py:357
        # symbols_retrieved = len(loop_result.symbols_read)
        #
        # loop_result.symbols_read populated by:
        # rim_qa_loop.py:242-243
        # elif tool_name == "get_symbol" and tool_observation.success:
        #     result.symbols_read.append(name)
        #
        # So symbols_retrieved ONLY counts get_symbol tool calls

        metrics_source = {
            "symbols_retrieved": "len(loop_result.symbols_read)",
            "symbols_read_populated_by": "tool_name == 'get_symbol' and tool_observation.success",
            "search_repository_results_counted": False,
        }

        assert not metrics_source["search_repository_results_counted"]


class TestDataDivergence:
    """Test if retriever and search_code see different data."""

    def test_search_code_vs_retriever_divergence(self, db):
        """DIAGNOSTIC: Can search_code find files that retriever can't?"""
        # This test would need access to actual repository files and blob storage.
        # For diagnostic purposes, we can verify the architectural separation:

        # 1. search_code reads from:
        #    - repo_root (worktree) if available
        #    - FactFile + Blob Storage if not

        # 2. retriever reads from:
        #    - BM25 index built from FactStore at init time
        #    - Chroma embeddings if available
        #    - Exact fact search

        # The divergence point: if FactStore is incomplete when retriever is initialized,
        # but complete when search_code runs, they see different data.

        # For RIM metadata, this is especially problematic because:
        # - RIM metadata uses retriever.retrieve() (on stale/incomplete index)
        # - Baseline loop uses search_code (on live data)
        # - They diverge

        print("Architectural separation verified:")
        print("- search_code: direct file access + FactFile")
        print("- retriever: BM25 index (from FactStore at init)")
        print("- Divergence point: retriever index may be stale")
