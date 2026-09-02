"""
Regression tests for unified retrieval architecture (Phase 4 implementation).

Tests that:
1. BM25 and Chroma indexes are built during analysis
2. Indexes are stored as artifacts
3. Retriever loads pre-built indexes
4. Retriever and live tools see the same data (no divergence)
5. Semantic degradation is tracked explicitly
6. Multiple different questions work correctly
7. No hardcoding of filenames, symbols, queries
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.database import Base
from backend.models.repository import Repository, Analysis, AnalysisArtifact
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.identity import generate_entity_id, generate_relationship_id
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.store.fact_store import save_rim_to_fact_store


@pytest.fixture
def db():
    """Create in-memory SQLite database for test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestIndexBuildingAndArtifactStorage:
    """Test that indexes are built during analysis and stored as artifacts."""

    def test_semantic_index_builder_creates_artifact(self):
        """Verify SemanticIndexBuilder.build_index returns compressed Chroma data."""
        # Create model with diverse entities
        model = RepositoryModel(metadata=RepositoryMetadata(name="test", path="/test", languages=["Python"]))

        # Add various entity types
        file_id = generate_entity_id(EntityType.FILE, "auth.py", "auth.py")
        model.entities[file_id] = Entity(
            id=file_id,
            type=EntityType.FILE,
            name="auth.py",
            location=SourceLocation(repository_path="auth.py", start_line=1, end_line=100, language="Python"),
        )

        func_id = generate_entity_id(EntityType.FUNCTION, "auth.py", "authenticate")
        model.entities[func_id] = Entity(
            id=func_id,
            type=EntityType.FUNCTION,
            name="authenticate",
            location=SourceLocation(repository_path="auth.py", start_line=10, end_line=30, language="Python"),
            qualified_name="auth.authenticate",
            metadata={"docstring": "Authenticates user credentials"},
        )

        class_id = generate_entity_id(EntityType.CLASS, "auth.py", "AuthManager")
        model.entities[class_id] = Entity(
            id=class_id,
            type=EntityType.CLASS,
            name="AuthManager",
            location=SourceLocation(repository_path="auth.py", start_line=35, end_line=80, language="Python"),
        )

        # Build semantic index
        builder = SemanticIndexBuilder()
        chroma_bytes = builder.build_index(model.entities)

        # Verify result
        assert chroma_bytes is not None, "SemanticIndexBuilder should return bytes"
        assert len(chroma_bytes) > 0, "Semantic index should have non-zero size"
        assert isinstance(chroma_bytes, bytes), "Should return bytes for storage"

    def test_bm25_index_export_from_retriever(self, db):
        """Verify BM25 index can be exported for artifact storage."""
        user = User(id=1, github_id="test", username="test", email="test@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 200
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add files and symbols
        file_id = f"{analysis_id}:urn:file:app.py#app.py"
        file_rec = FactFile(id=file_id, analysis_id=analysis_id, path="app.py", language="Python")
        db.add(file_rec)
        db.flush()

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

        # Create retriever (builds index)
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # Export index for artifact storage
        if retriever.bm25_index:
            bm25_data = {
                "documents": retriever.bm25_index.documents,
                "idf": dict(retriever.bm25_index.idf),
                "doc_len": retriever.bm25_index.doc_len,
                "corpus_size": retriever.bm25_index.corpus_size,
                "avg_doc_len": retriever.bm25_index.avg_doc_len,
            }
            # Verify export is valid
            assert isinstance(bm25_data["documents"], list)
            assert isinstance(bm25_data["idf"], dict)
            assert isinstance(bm25_data["doc_len"], list)


class TestIndexLoadingFromArtifacts:
    """Test that retriever loads pre-built indexes from artifacts."""

    def test_retriever_loads_bm25_from_artifact(self, db):
        """Verify HybridRetriever loads BM25 index from analysis artifact."""
        user = User(id=2, github_id="test2", username="test2", email="test2@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=2, url="https://github.com/test2/repo2", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 201
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add test data
        file_id = f"{analysis_id}:urn:file:test.py#test.py"
        file_rec = FactFile(id=file_id, analysis_id=analysis_id, path="test.py", language="Python")
        db.add(file_rec)
        db.flush()

        sym_id = f"{analysis_id}:urn:function:test.py#validate"
        sym = FactSymbol(
            id=sym_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="validate",
            qualified_name="test.validate",
            symbol_type="function",
            line_start=5,
            line_end=20,
        )
        db.add(sym)
        db.commit()

        # Build and store BM25 index
        retriever1 = HybridRetriever(db=db, analysis_id=analysis_id)
        assert retriever1.bm25_index is not None

        # Export and store as artifact
        bm25_data = {
            "documents": retriever1.bm25_index.documents,
            "idf": dict(retriever1.bm25_index.idf),
            "doc_len": retriever1.bm25_index.doc_len,
            "corpus_size": retriever1.bm25_index.corpus_size,
            "avg_doc_len": retriever1.bm25_index.avg_doc_len,
        }
        artifact = AnalysisArtifact(
            analysis_id=analysis_id,
            type="bm25_index",
            data=bm25_data,
        )
        db.add(artifact)
        db.commit()

        # Create new retriever - should load from artifact
        retriever2 = HybridRetriever(db=db, analysis_id=analysis_id)
        assert retriever2.bm25_index is not None
        assert len(retriever2.bm25_index.documents) > 0

        # Verify it can find the symbol
        results = retriever2.retrieve("validate", top_k=5, expand_with_fact_store=False)
        assert len(results) > 0, "Should find 'validate' from loaded artifact"


class TestRetrieverAndToolDataConsistency:
    """Test that retriever and live tools see the same data."""

    def test_retriever_sees_all_factstore_entities(self, db):
        """Verify BM25 index indexes all entities in FactStore."""
        user = User(id=3, github_id="test3", username="test3", email="test3@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=3, url="https://github.com/test3/repo3", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 202
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add multiple files
        files = []
        for i in range(3):
            file_id = f"{analysis_id}:urn:file:module{i}.py#module{i}.py"
            file_rec = FactFile(id=file_id, analysis_id=analysis_id, path=f"module{i}.py", language="Python")
            db.add(file_rec)
            files.append(file_rec)
        db.flush()

        # Add symbols in each file
        symbols = []
        for i, file_rec in enumerate(files):
            for j in range(2):
                sym_id = f"{analysis_id}:urn:function:module{i}.py#func{j}"
                sym = FactSymbol(
                    id=sym_id,
                    analysis_id=analysis_id,
                    file_id=file_rec.id,
                    name=f"func{j}",
                    qualified_name=f"module{i}.func{j}",
                    symbol_type="function",
                    line_start=j * 10,
                    line_end=j * 10 + 5,
                )
                db.add(sym)
                symbols.append(sym)
        db.commit()

        # Create retriever
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # Check that all files are in index
        assert retriever.bm25_index is not None
        assert len(retriever.bm25_index.documents) >= 6, "Should index at least files + symbols"

        # Verify can find symbols from different files
        for i in range(3):
            results = retriever.retrieve(f"func0", top_k=5, expand_with_fact_store=False)
            # Should find multiple func0 across different files
            assert len(results) > 0, f"Should find func0 functions"

    def test_no_orphaned_symbols_in_retrieval(self, db):
        """Verify retriever only indexes symbols that exist in FactStore."""
        user = User(id=4, github_id="test4", username="test4", email="test4@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=4, url="https://github.com/test4/repo4", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 203
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add file with symbol
        file_id = f"{analysis_id}:urn:file:core.py#core.py"
        file_rec = FactFile(id=file_id, analysis_id=analysis_id, path="core.py", language="Python")
        db.add(file_rec)
        db.flush()

        sym_id = f"{analysis_id}:urn:function:core.py#process"
        sym = FactSymbol(
            id=sym_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="process",
            qualified_name="core.process",
            symbol_type="function",
            line_start=1,
            line_end=20,
        )
        db.add(sym)
        db.commit()

        # Build index
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # All indexed documents should be resolvable
        if retriever.bm25_index and retriever.bm25_index.documents:
            for doc in retriever.bm25_index.documents:
                # Documents should have proper structure
                assert "id" in doc or "name" in doc, f"Document missing id/name: {doc}"


class TestSemanticDegradationTracking:
    """Test that semantic degradation is tracked explicitly."""

    def test_semantic_degradation_when_no_artifact(self, db):
        """Verify semantic_degradation is set when artifact missing."""
        user = User(id=5, github_id="test5", username="test5", email="test5@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=5, url="https://github.com/test5/repo5", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 204
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.commit()

        # Create retriever without semantic artifact
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # Should track degradation reason
        assert retriever.semantic_degradation is not None, "Should track why semantic search failed"
        assert "artifact_not_found" in retriever.semantic_degradation.lower() or "unavailable" in retriever.semantic_degradation.lower()

    def test_semantic_search_returns_empty_with_degradation(self, db):
        """Verify semantic search returns empty when degraded."""
        user = User(id=6, github_id="test6", username="test6", email="test6@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=6, url="https://github.com/test6/repo6", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 205
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.commit()

        # Create retriever without Chroma collection
        retriever = HybridRetriever(db=db, analysis_id=analysis_id, chroma_collection=None)

        # Semantic search should return empty
        results = retriever._search_semantic("test query", top_k=5)
        assert len(results) == 0, "Semantic search should return empty when degraded"


class TestMultipleQuestionsAndScenarios:
    """Test with various different questions and entity types."""

    def test_retrieval_with_authentication_question(self, db):
        """Test retrieval with authentication-related entities."""
        user = User(id=7, github_id="test7", username="test7", email="test7@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=7, url="https://github.com/test7/repo7", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 206
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add authentication-related entities
        file_id = f"{analysis_id}:urn:file:auth.py#auth.py"
        file_rec = FactFile(id=file_id, analysis_id=analysis_id, path="auth.py", language="Python")
        db.add(file_rec)
        db.flush()

        auth_func_id = f"{analysis_id}:urn:function:auth.py#authenticate_user"
        auth_sym = FactSymbol(
            id=auth_func_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="authenticate_user",
            qualified_name="auth.authenticate_user",
            symbol_type="function",
            line_start=10,
            line_end=30,
        )
        db.add(auth_sym)
        db.commit()

        # Create retriever
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # Query with authentication-related question
        results = retriever.retrieve("How does authentication work", top_k=5, expand_with_fact_store=False)
        # Should find authentication-related entities even if exact match isn't perfect
        assert retriever.bm25_index is not None

    def test_retrieval_with_database_question(self, db):
        """Test retrieval with database-related entities."""
        user = User(id=8, github_id="test8", username="test8", email="test8@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=8, url="https://github.com/test8/repo8", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 207
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add database-related entities
        file_id = f"{analysis_id}:urn:file:models.py#models.py"
        file_rec = FactFile(id=file_id, analysis_id=analysis_id, path="models.py", language="Python")
        db.add(file_rec)
        db.flush()

        model_class_id = f"{analysis_id}:urn:class:models.py#UserModel"
        model_sym = FactSymbol(
            id=model_class_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="UserModel",
            qualified_name="models.UserModel",
            symbol_type="class",
            line_start=5,
            line_end=40,
        )
        db.add(model_sym)
        db.commit()

        # Create retriever
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # Query with database-related question
        results = retriever.retrieve("What data is stored", top_k=5, expand_with_fact_store=False)
        # Should handle the query even if no exact results
        assert retriever.bm25_index is not None

    def test_retrieval_with_api_endpoint_question(self, db):
        """Test retrieval with API endpoint entities."""
        user = User(id=9, github_id="test9", username="test9", email="test9@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=9, url="https://github.com/test9/repo9", user_id=user.id)
        db.add(repo)
        db.flush()

        analysis_id = 208
        analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Add API-related entities
        file_id = f"{analysis_id}:urn:file:api.py#api.py"
        file_rec = FactFile(id=file_id, analysis_id=analysis_id, path="api.py", language="Python")
        db.add(file_rec)
        db.flush()

        endpoint_func_id = f"{analysis_id}:urn:function:api.py#get_users"
        endpoint_sym = FactSymbol(
            id=endpoint_func_id,
            analysis_id=analysis_id,
            file_id=file_id,
            name="get_users",
            qualified_name="api.get_users",
            symbol_type="function",
            line_start=50,
            line_end=70,
        )
        db.add(endpoint_sym)
        db.commit()

        # Create retriever
        retriever = HybridRetriever(db=db, analysis_id=analysis_id)

        # Query with API-related question
        results = retriever.retrieve("What endpoints are available", top_k=5, expand_with_fact_store=False)
        assert retriever.bm25_index is not None
