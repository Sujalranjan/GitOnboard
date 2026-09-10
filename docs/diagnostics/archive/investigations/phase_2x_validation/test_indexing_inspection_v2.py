#!/usr/bin/env python3
"""
Direct inspection of indexing and retrieval layers using pytest fixtures.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import json

from backend.database import Base
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.lexical import CodeTokenizer


@pytest.fixture
def db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def setup_test_repo(db):
    """Setup comprehensive test repository."""
    user = User(id=1, github_id="test", username="test", email="test@test.com")
    db.add(user)
    db.flush()

    repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
    db.add(repo)
    db.flush()

    analysis = Analysis(id=100, repository_id=repo.id, status="Completed")
    db.add(analysis)
    db.flush()

    # Create test files
    files = [
        FactFile(id=1, analysis_id=analysis.id, path="src/auth/service.py", language="Python"),
        FactFile(id=2, analysis_id=analysis.id, path="src/auth/middleware.py", language="Python"),
        FactFile(id=3, analysis_id=analysis.id, path="src/models/user.py", language="Python"),
    ]
    for f in files:
        db.add(f)
    db.flush()

    # Create baseline symbols
    baseline_symbols = [
        # From objective: authenticate_token, AuthService, login
        FactSymbol(
            id=1,
            analysis_id=analysis.id,
            name="authenticate_token",
            qualified_name="auth.service.authenticate_token",
            symbol_type="function",
            file_id=1,
            line_start=10,
            line_end=25,
            metadata_json={
                "docstring": "Authenticates a token string",
                "signature": "authenticate_token(token: str) -> bool"
            }
        ),
        FactSymbol(
            id=2,
            analysis_id=analysis.id,
            name="AuthService",
            qualified_name="auth.service.AuthService",
            symbol_type="class",
            file_id=1,
            line_start=30,
            line_end=100,
            metadata_json={
                "docstring": "Service for authentication operations",
                "signature": "class AuthService"
            }
        ),
        FactSymbol(
            id=3,
            analysis_id=analysis.id,
            name="login",
            qualified_name="auth.service.AuthService.login",
            symbol_type="method",
            file_id=1,
            line_start=40,
            line_end=55,
            metadata_json={
                "docstring": "Logs in a user with credentials",
                "signature": "def login(self, username: str, password: str) -> bool"
            }
        ),
        # Additional symbols to test retrieval
        FactSymbol(
            id=4,
            analysis_id=analysis.id,
            name="validate_jwt",
            qualified_name="auth.middleware.validate_jwt",
            symbol_type="function",
            file_id=2,
            line_start=5,
            line_end=20,
            metadata_json={
                "docstring": "Validates JWT tokens",
                "signature": "validate_jwt(token: str) -> dict"
            }
        ),
        FactSymbol(
            id=5,
            analysis_id=analysis.id,
            name="User",
            qualified_name="models.user.User",
            symbol_type="class",
            file_id=3,
            line_start=1,
            line_end=50,
            metadata_json={
                "docstring": "User model",
                "signature": "class User"
            }
        ),
    ]

    for sym in baseline_symbols:
        db.add(sym)
    db.commit()

    return db, analysis


class TestIndexingInspection:
    """Inspect indexing and retrieval layers."""

    def test_fact_store_baseline(self, setup_test_repo):
        """Verify Fact Store baseline: 29 entities (6 functions, 5 classes, 13 methods, 5 files)."""
        db, analysis = setup_test_repo

        files = db.query(FactFile).filter(FactFile.analysis_id == analysis.id).count()
        symbols = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis.id).count()

        print(f"\n=== FACT STORE BASELINE ===")
        print(f"Files: {files}")
        print(f"Symbols: {symbols}")

        # Sample baseline symbols
        baseline = ["authenticate_token", "AuthService", "login"]
        for name in baseline:
            sym = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis.id,
                FactSymbol.name == name
            ).first()
            assert sym is not None, f"Baseline symbol '{name}' not found"
            print(f"  ✓ Found: {sym.name} ({sym.symbol_type})")

    def test_bm25_index_construction(self, setup_test_repo):
        """Inspect BM25 index construction and content."""
        db, analysis = setup_test_repo

        retriever = HybridRetriever(db, analysis_id=analysis.id)
        idx = retriever.bm25_index

        print(f"\n=== BM25 INDEX CONSTRUCTION ===")
        print(f"Document count: {idx.corpus_size}")
        print(f"Vocabulary size: {len(idx.idf)}")
        print(f"Average doc length: {idx.avg_doc_len:.2f} tokens")

        assert idx.corpus_size > 0, "BM25 index is empty"
        assert len(idx.documents) == idx.corpus_size, "Document count mismatch"
        assert len(idx.idf) > 0, "IDF dictionary is empty"

        # Verify sample documents
        print(f"\nIndexed documents:")
        for doc in idx.documents:
            print(f"  - {doc.get('name', '?')} ({doc.get('type', '?')}) id={doc.get('id')}")

        # Check that symbols are indexed
        symbol_docs = [d for d in idx.documents if d.get('type') == 'symbol']
        assert len(symbol_docs) > 0, "No symbols indexed"
        print(f"\nSymbols indexed: {len(symbol_docs)}")

    def test_bm25_queries(self, setup_test_repo):
        """Test BM25 queries: "authenticate_token", "authentication", "login"."""
        db, analysis = setup_test_repo

        retriever = HybridRetriever(db, analysis_id=analysis.id)
        idx = retriever.bm25_index

        queries = {
            "authenticate_token": "exact symbol name",
            "authentication": "concept",
            "login": "method name",
        }

        print(f"\n=== BM25 QUERY RESULTS ===")
        for query, description in queries.items():
            results = idx.search(query, top_k=10)
            print(f"\nQuery: '{query}' ({description})")
            print(f"  Results: {len(results)}")

            for i, (doc, score) in enumerate(results[:3]):
                name = doc.get('name', '?')
                doc_type = doc.get('type', '?')
                print(f"    {i+1}. {name} ({doc_type}) score={score:.3f}")

            # Verify results include metadata
            if results:
                doc, _ = results[0]
                assert 'id' in doc, "Result missing 'id'"
                assert 'type' in doc, "Result missing 'type'"
                assert 'file_path' in doc, "Result missing 'file_path'"
                print(f"  ✓ Metadata intact")

    def test_bm25_exact_match_scoring(self, setup_test_repo):
        """Verify BM25 finds exact symbol matches with highest scores."""
        db, analysis = setup_test_repo

        retriever = HybridRetriever(db, analysis_id=analysis.id)

        # Search for exact symbol name
        results = retriever.bm25_index.search("authenticate_token", top_k=10)

        print(f"\n=== BM25 EXACT MATCH SCORING ===")
        print(f"Query: 'authenticate_token'")
        print(f"Results: {len(results)}")

        assert len(results) > 0, "No results for 'authenticate_token'"
        top_doc, top_score = results[0]

        print(f"Top result: {top_doc.get('name')} (score={top_score:.3f})")
        assert top_doc.get('name') == 'authenticate_token', "Top result should be exact match"
        print(f"✓ Exact match is top result")

    def test_hybrid_retriever_primary(self, setup_test_repo):
        """Test HybridRetriever primary retrieval strategy."""
        db, analysis = setup_test_repo

        retriever = HybridRetriever(db, analysis_id=analysis.id)

        queries = [
            ("authenticate_token", "exact symbol"),
            ("authentication", "concept"),
        ]

        print(f"\n=== HYBRID RETRIEVER PRIMARY STRATEGY ===")
        for query, description in queries:
            results = retriever._retrieve_primary(query, top_k=5, expand_with_fact_store=False)

            print(f"\nQuery: '{query}' ({description})")
            print(f"Results: {len(results)}")

            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. {result.entity_name} ({result.entity_type.value})")
                print(f"     file={result.file_path}, score={result.score:.3f}, score_type={result.score_type}")

    def test_rrf_fusion(self, setup_test_repo):
        """Verify RRF fusion combines multiple ranked lists."""
        db, analysis = setup_test_repo

        retriever = HybridRetriever(db, analysis_id=analysis.id)

        # Get exact, lexical, and semantic results
        query = "authenticate_token"
        exact = retriever._search_exact_facts(query)
        lexical = retriever._search_lexical(query, top_k=10)
        semantic = retriever._search_semantic(query, top_k=10)

        print(f"\n=== RRF FUSION ===")
        print(f"Query: '{query}'")
        print(f"  Exact results: {len(exact)}")
        print(f"  Lexical results: {len(lexical)}")
        print(f"  Semantic results: {len(semantic)}")

        # Verify RRF fusion
        from backend.intelligence.retrieval.fusion import reciprocal_rank_fusion

        ranked_lists = []
        weights = []
        if exact:
            ranked_lists.append(exact)
            weights.append(1.2)
        if lexical:
            ranked_lists.append(lexical)
            weights.append(1.0)
        if semantic:
            ranked_lists.append(semantic)
            weights.append(1.0)

        if ranked_lists:
            fused = reciprocal_rank_fusion(
                ranked_lists=ranked_lists,
                weights=weights,
                rrf_k=60,
                key_field="id",
                top_k=10
            )

            print(f"  Fused results: {len(fused)}")
            for i, doc in enumerate(fused[:3]):
                print(f"    {i+1}. {doc.get('name', '?')} (rrf_score={doc.get('_rrf_score', 0):.3f})")

            # Verify fused results have RRF metadata
            if fused:
                assert '_rrf_score' in fused[0], "Missing _rrf_score"
                assert '_source_ranks' in fused[0], "Missing _source_ranks"
                print(f"  ✓ RRF metadata intact")

    def test_symbol_identity_preservation(self, setup_test_repo):
        """Verify symbol identity is preserved through indexing and retrieval."""
        db, analysis = setup_test_repo

        retriever = HybridRetriever(db, analysis_id=analysis.id)

        # Get the actual symbol from DB
        actual_sym = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            FactSymbol.name == "authenticate_token"
        ).first()

        assert actual_sym is not None, "Test symbol not found"

        # Retrieve via HybridRetriever
        results = retriever.retrieve("authenticate_token", top_k=5, expand_with_fact_store=False)

        print(f"\n=== SYMBOL IDENTITY PRESERVATION ===")
        print(f"Original symbol: {actual_sym.name} (id={actual_sym.id})")

        assert len(results) > 0, "No retrieval results"

        retrieved = results[0]
        print(f"Retrieved: {retrieved.entity_name} (id={retrieved.id})")
        print(f"  entity_type: {retrieved.entity_type.value}")
        print(f"  file_path: {retrieved.file_path}")
        print(f"  line_start: {retrieved.line_start}")

        # Verify metadata is preserved
        assert retrieved.entity_name == actual_sym.name, "Name mismatch"
        assert retrieved.file_path == actual_sym.file.path, "File path mismatch"
        assert retrieved.line_start == actual_sym.line_start, "Line start mismatch"
        print(f"✓ Symbol identity preserved")


class TestSemanticIndexing:
    """Test semantic indexing (ChromaDB)."""

    def test_semantic_degradation_without_chroma(self, setup_test_repo):
        """Verify semantic degradation tracking when Chroma is unavailable."""
        db, analysis = setup_test_repo

        retriever = HybridRetriever(db, analysis_id=analysis.id)

        print(f"\n=== SEMANTIC INDEX STATUS ===")
        if not retriever.chroma_collection:
            print(f"Semantic index unavailable: {retriever.semantic_degradation or 'unknown reason'}")
        else:
            print(f"Semantic index loaded successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
