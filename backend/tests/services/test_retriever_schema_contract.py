"""
Tests for canonical retriever schema contract.

Verifies that:
1. Retriever results conform to RetrieverResult schema
2. RIM metadata can extract seeds from retriever results
3. Field names are consistent across all retrieval strategies
4. Conversion functions work correctly
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile
from backend.intelligence.retrieval.schema import (
    RetrieverResult,
    EntityType,
    convert_lexical_result_to_schema,
    convert_semantic_result_to_schema,
    convert_exact_result_to_schema,
)
from backend.intelligence.retrieval.lexical import BM25Index
from backend.services.rim_metadata import TargetEntityResolver


@pytest.fixture
def db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestRetrieverSchemaContract:
    """Test retriever result schema consistency."""

    def test_retriever_result_has_required_fields(self):
        """Verify RetrieverResult has all required fields."""
        result = RetrieverResult(
            id="sym_1",
            entity_name="authMiddleware",
            entity_type=EntityType.SYMBOL,
            file_path="src/middleware.js",
            line_start=10,
            line_end=25,
            qualified_name="middleware.authMiddleware",
            score_type="lexical",
            score=0.85,
        )

        assert result.id == "sym_1"
        assert result.entity_name == "authMiddleware"
        assert result.entity_type == EntityType.SYMBOL
        assert result.file_path == "src/middleware.js"
        assert result.line_start == 10
        assert result.qualified_name == "middleware.authMiddleware"

    def test_schema_serialization(self):
        """Test RetrieverResult to/from dict."""
        result = RetrieverResult(
            id="sym_1",
            entity_name="authenticate",
            entity_type=EntityType.SYMBOL,
            file_path="src/auth.py",
            qualified_name="auth.authenticate",
            score_type="semantic",
            score=0.92,
        )

        # Serialize
        data = result.to_dict()
        assert data["entity_name"] == "authenticate"
        assert data["entity_type"] == "symbol"
        assert data["score_type"] == "semantic"

        # Deserialize
        restored = RetrieverResult.from_dict(data)
        assert restored.entity_name == result.entity_name
        assert restored.entity_type == result.entity_type
        assert restored.score == result.score

    def test_convert_lexical_result_to_schema(self):
        """Test lexical result conversion."""
        lexical_doc = {
            "id": "sym_1",
            "name": "authMiddleware",
            "qualified_name": "middleware.authMiddleware",
            "type": "function",
            "file_path": "src/middleware.js",
            "line_start": 10,
            "line_end": 25,
            "bm25_score": 0.75,
        }

        result = convert_lexical_result_to_schema(lexical_doc)

        assert result.id == "sym_1"
        assert result.entity_name == "authMiddleware"
        assert result.entity_type == EntityType.SYMBOL
        assert result.file_path == "src/middleware.js"
        assert result.score_type == "lexical"
        assert result.score == 0.75

    def test_convert_semantic_result_to_schema(self):
        """Test semantic result conversion."""
        semantic_doc = {
            "id": "sym_2",
            "name": "validateToken",
            "type": "function",
            "file_path": "src/auth.py",
            "distance": 0.25,
        }

        result = convert_semantic_result_to_schema(semantic_doc)

        assert result.id == "sym_2"
        assert result.entity_name == "validateToken"
        assert result.score_type == "semantic"
        assert "distance" in result.metadata
        assert result.metadata["distance"] == 0.25

    def test_convert_exact_result_to_schema(self):
        """Test exact fact result conversion."""
        exact_doc = {
            "id": "sym_3",
            "name": "authenticate",
            "qualified_name": "auth.authenticate",
            "type": "function",
            "file_path": "src/auth.py",
            "score_type": "exact_fact",
        }

        result = convert_exact_result_to_schema(exact_doc)

        assert result.id == "sym_3"
        assert result.entity_name == "authenticate"
        assert result.entity_type == EntityType.SYMBOL
        assert result.score_type == "exact_fact"
        assert result.score == 1.0

    def test_schema_result_can_be_resolved_by_rim(self, db):
        """Test that schema results can be resolved to ORM objects."""
        # Setup: Create test user and repo
        user = User(id=1, github_id="test", username="test", email="test@test.com")
        db.add(user)
        db.flush()

        repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
        db.add(repo)
        db.flush()

        # Create analysis with symbols
        analysis = Analysis(id=100, repository_id=repo.id, status="Completed")
        db.add(analysis)
        db.flush()

        # Create test file and symbols
        test_file = FactFile(
            id=1,
            analysis_id=analysis.id,
            path="src/auth.py",
            language="Python",
        )
        db.add(test_file)
        db.flush()

        auth_symbol = FactSymbol(
            id=1,
            analysis_id=analysis.id,
            name="authenticate",
            qualified_name="auth.authenticate",
            symbol_type="function",
            file_id=test_file.id,
            line_start=10,
            line_end=30,
        )
        db.add(auth_symbol)
        db.commit()

        # Create schema result
        result = RetrieverResult(
            id="sym_1",
            entity_name="authenticate",
            entity_type=EntityType.SYMBOL,
            file_path="src/auth.py",
            line_start=10,
            qualified_name="auth.authenticate",
        )

        # Resolve using RIM's resolver
        resolver = TargetEntityResolver(db, analysis.id)
        target = resolver.resolve(result.entity_name)

        assert target is not None
        assert target.name == "authenticate"
        assert target.symbol_type == "function"

    def test_bm25_result_field_names_match_schema(self):
        """Verify BM25 indexed documents have correct field names for schema conversion."""
        docs = [
            {
                "id": 1,
                "name": "authMiddleware",
                "qualified_name": "middleware.authMiddleware",
                "type": "function",
                "file_path": "src/middleware.js",
                "search_text": "authMiddleware middleware function",
                "line_start": 10,
                "line_end": 25,
                "match_type": "function",
                "match_name": "authMiddleware",
            }
        ]

        index = BM25Index()
        index.index(docs, text_key="search_text")

        # Search should return dict with schema-compatible fields
        results = index.search("middleware", top_k=5)
        assert len(results) > 0

        doc, score = results[0]

        # Verify fields exist for schema conversion
        assert "id" in doc
        assert "name" in doc or "match_name" in doc
        assert "type" in doc or "match_type" in doc
        assert "file_path" in doc

        # Should be convertible to schema
        schema_result = convert_lexical_result_to_schema(doc)
        assert schema_result.entity_name is not None
        assert schema_result.entity_type is not None
        assert schema_result.file_path is not None

    def test_lexical_and_semantic_results_use_same_schema(self):
        """Verify lexical and semantic results can both be converted to same schema."""
        lexical_doc = {
            "id": "lex_1",
            "name": "authenticate",
            "type": "function",
            "file_path": "src/auth.py",
            "bm25_score": 0.75,
        }

        semantic_doc = {
            "id": "sem_1",
            "name": "authenticate",
            "type": "function",
            "file_path": "src/auth.py",
            "distance": 0.3,
        }

        lex_result = convert_lexical_result_to_schema(lexical_doc)
        sem_result = convert_semantic_result_to_schema(semantic_doc)

        # Both should have same entity_name, entity_type, file_path
        assert lex_result.entity_name == sem_result.entity_name
        assert lex_result.entity_type == sem_result.entity_type
        assert lex_result.file_path == sem_result.file_path

        # But different score_type
        assert lex_result.score_type != sem_result.score_type

    def test_schema_handles_missing_optional_fields(self):
        """Test RetrieverResult works with minimal required fields."""
        result = RetrieverResult(
            id="test_1",
            entity_name="test_entity",
            entity_type=EntityType.FILE,
            file_path="test.py",
        )

        assert result.id == "test_1"
        assert result.entity_name == "test_entity"
        assert result.qualified_name is None
        assert result.line_start is None
        assert result.score == 0.0

    def test_schema_entity_type_enum(self):
        """Test EntityType enum covers all retriever types."""
        assert EntityType.SYMBOL.value == "symbol"
        assert EntityType.FILE.value == "file"
        assert EntityType.ROUTE.value == "route"
        assert EntityType.DATABASE_TABLE.value == "database_table"
        assert EntityType.CAPABILITY.value == "capability"
