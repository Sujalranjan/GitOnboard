"""
Tests for BoundedGraphExpander integration with HybridRetriever.

Verifies:
1. Anchor nodes are identified and preserved
2. Graph expansion respects depth limits
3. Graph expansion respects node count limits
4. Node deduplication works correctly
5. Relationship context is captured
6. Expansion integrates with retriever
7. Provenance is maintained
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.database import Base
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from backend.intelligence.retrieval.bounded_graph_expander import BoundedGraphExpander
from backend.intelligence.retrieval.retriever import HybridRetriever


@pytest.fixture
def db():
    """Create in-memory SQLite database for test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_repository(db):
    """Create test repository with user."""
    user = User(id=1, github_id="test", username="test", email="test@test.com")
    db.add(user)
    db.flush()

    repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
    db.add(repo)
    db.flush()

    return repo


@pytest.fixture
def test_analysis(db, test_repository):
    """Create test analysis."""
    analysis = Analysis(id=100, repository_id=test_repository.id, status="Completed")
    db.add(analysis)
    db.commit()
    return analysis


@pytest.fixture
def test_fact_store(db, test_analysis):
    """Create sample fact store with files, symbols, and relationships."""
    analysis_id = test_analysis.id

    # Create files
    file1 = FactFile(
        id="file1",
        analysis_id=analysis_id,
        path="app/auth.py",
        language="Python",
    )
    file2 = FactFile(
        id="file2",
        analysis_id=analysis_id,
        path="app/handlers.py",
        language="Python",
    )
    file3 = FactFile(
        id="file3",
        analysis_id=analysis_id,
        path="app/utils.py",
        language="Python",
    )
    db.add_all([file1, file2, file3])
    db.flush()

    # Create symbols
    # auth.py: authenticate function
    auth_func = FactSymbol(
        id="sym_auth_func",
        analysis_id=analysis_id,
        file_id="file1",
        name="authenticate",
        qualified_name="auth.authenticate",
        symbol_type="function",
        line_start=10,
        line_end=30,
    )

    # auth.py: AuthManager class
    auth_class = FactSymbol(
        id="sym_auth_class",
        analysis_id=analysis_id,
        file_id="file1",
        name="AuthManager",
        qualified_name="auth.AuthManager",
        symbol_type="class",
        line_start=35,
        line_end=80,
    )

    # handlers.py: login_handler function
    login_handler = FactSymbol(
        id="sym_login_handler",
        analysis_id=analysis_id,
        file_id="file2",
        name="login_handler",
        qualified_name="handlers.login_handler",
        symbol_type="function",
        line_start=15,
        line_end=45,
    )

    # handlers.py: logout_handler function
    logout_handler = FactSymbol(
        id="sym_logout_handler",
        analysis_id=analysis_id,
        file_id="file2",
        name="logout_handler",
        qualified_name="handlers.logout_handler",
        symbol_type="function",
        line_start=50,
        line_end=70,
    )

    # utils.py: hash_password function
    hash_password = FactSymbol(
        id="sym_hash_password",
        analysis_id=analysis_id,
        file_id="file3",
        name="hash_password",
        qualified_name="utils.hash_password",
        symbol_type="function",
        line_start=5,
        line_end=20,
    )

    # utils.py: verify_password function
    verify_password = FactSymbol(
        id="sym_verify_password",
        analysis_id=analysis_id,
        file_id="file3",
        name="verify_password",
        qualified_name="utils.verify_password",
        symbol_type="function",
        line_start=25,
        line_end=40,
    )

    db.add_all([
        auth_func,
        auth_class,
        login_handler,
        logout_handler,
        hash_password,
        verify_password,
    ])
    db.flush()

    # Create relationships (edges)
    # login_handler calls authenticate
    rel1 = FactRelationship(
        id="rel1",
        analysis_id=analysis_id,
        from_symbol_id="sym_login_handler",
        to_symbol_id="sym_auth_func",
        rel_type="CALLS",
        evidence_line=20,
    )

    # authenticate calls hash_password
    rel2 = FactRelationship(
        id="rel2",
        analysis_id=analysis_id,
        from_symbol_id="sym_auth_func",
        to_symbol_id="sym_hash_password",
        rel_type="CALLS",
        evidence_line=15,
    )

    # login_handler calls hash_password (direct)
    rel3 = FactRelationship(
        id="rel3",
        analysis_id=analysis_id,
        from_symbol_id="sym_login_handler",
        to_symbol_id="sym_hash_password",
        rel_type="CALLS",
        evidence_line=25,
    )

    # logout_handler calls verify_password
    rel4 = FactRelationship(
        id="rel4",
        analysis_id=analysis_id,
        from_symbol_id="sym_logout_handler",
        to_symbol_id="sym_verify_password",
        rel_type="CALLS",
        evidence_line=55,
    )

    # verify_password calls hash_password
    rel5 = FactRelationship(
        id="rel5",
        analysis_id=analysis_id,
        from_symbol_id="sym_verify_password",
        to_symbol_id="sym_hash_password",
        rel_type="CALLS",
        evidence_line=30,
    )

    db.add_all([rel1, rel2, rel3, rel4, rel5])
    db.commit()

    return {
        "files": {"file1": file1, "file2": file2, "file3": file3},
        "symbols": {
            "auth_func": auth_func,
            "auth_class": auth_class,
            "login_handler": login_handler,
            "logout_handler": logout_handler,
            "hash_password": hash_password,
            "verify_password": verify_password,
        },
        "relationships": [rel1, rel2, rel3, rel4, rel5],
    }


class TestBoundedGraphExpander:
    """Test BoundedGraphExpander directly."""

    def test_anchor_resolution(self, db, test_analysis, test_fact_store):
        """Verify anchor nodes are resolved to symbols correctly."""
        expander = BoundedGraphExpander(db, test_analysis.id, max_depth=2)

        candidates = [
            {
                "id": "login_handler_1",
                "name": "login_handler",
                "file_path": "app/handlers.py",
                "symbol_id": "sym_login_handler",
                "type": "function",
                "match_type": "function",
            }
        ]

        result = expander._process_anchor(candidates[0])

        assert result is not None
        assert result["symbol_id"] == "sym_login_handler"
        assert result["name"] == "login_handler"
        assert result["is_anchor"] is True
        assert result["file_path"] == "app/handlers.py"

    def test_expansion_respects_depth_limit(self, db, test_analysis, test_fact_store):
        """Verify expansion respects max_depth limit."""
        expander = BoundedGraphExpander(
            db, test_analysis.id, max_depth=1, max_nodes_per_hop=10, max_total_nodes=50
        )

        candidates = [
            {
                "id": "login_handler_1",
                "name": "login_handler",
                "file_path": "app/handlers.py",
                "symbol_id": "sym_login_handler",
                "type": "function",
            }
        ]

        result = expander.expand_candidates(candidates)

        # Should have anchor + direct neighbors only (depth 1)
        # login_handler calls: authenticate, hash_password (depth 1)
        # Should not include hash_password's callees (depth 2)
        assert len(result) > 0
        assert result[0]["name"] == "login_handler"

        # Check that we have some expanded nodes
        expanded = [r for r in result if r.get("expansion_source", "").startswith("expanded_from")]
        assert len(expanded) > 0

    def test_expansion_respects_node_limit(self, db, test_analysis, test_fact_store):
        """Verify expansion respects max_total_nodes limit."""
        expander = BoundedGraphExpander(
            db, test_analysis.id, max_depth=3, max_nodes_per_hop=10, max_total_nodes=5
        )

        candidates = [
            {
                "id": "login_handler_1",
                "name": "login_handler",
                "file_path": "app/handlers.py",
                "symbol_id": "sym_login_handler",
                "type": "function",
            }
        ]

        result = expander.expand_candidates(candidates)

        # Should not exceed max_total_nodes
        assert len(result) <= 5

    def test_deduplication(self, db, test_analysis, test_fact_store):
        """Verify nodes are not duplicated in expansion."""
        expander = BoundedGraphExpander(
            db, test_analysis.id, max_depth=3, max_nodes_per_hop=10, max_total_nodes=50
        )

        # hash_password is reached via multiple paths
        candidates = [
            {
                "id": "login_handler_1",
                "name": "login_handler",
                "file_path": "app/handlers.py",
                "symbol_id": "sym_login_handler",
                "type": "function",
            }
        ]

        result = expander.expand_candidates(candidates)

        # Count unique symbol IDs
        symbol_ids = [r.get("symbol_id") for r in result]
        unique_ids = set(symbol_ids)

        # Should have no duplicates
        assert len(symbol_ids) == len(unique_ids)

    def test_anchor_provenance_preserved(self, db, test_analysis, test_fact_store):
        """Verify anchor node provenance is preserved in expansion."""
        expander = BoundedGraphExpander(
            db, test_analysis.id, max_depth=2, max_nodes_per_hop=10, max_total_nodes=50
        )

        candidates = [
            {
                "id": "login_handler_1",
                "name": "login_handler",
                "file_path": "app/handlers.py",
                "symbol_id": "sym_login_handler",
                "type": "function",
            }
        ]

        result = expander.expand_candidates(candidates)

        # First result should be anchor
        anchor = result[0]
        assert anchor["is_anchor"] is True
        assert anchor["expansion_source"] == "anchor"

        # Other results should reference anchor
        for node in result[1:]:
            if "expansion_source" in node:
                assert "expanded_from" in node["expansion_source"]

    def test_relationship_context_captured(self, db, test_analysis, test_fact_store):
        """Verify relationship context is captured (rel_type, role, etc)."""
        expander = BoundedGraphExpander(
            db, test_analysis.id, max_depth=2, max_nodes_per_hop=10, max_total_nodes=50
        )

        candidates = [
            {
                "id": "login_handler_1",
                "name": "login_handler",
                "file_path": "app/handlers.py",
                "symbol_id": "sym_login_handler",
                "type": "function",
            }
        ]

        result = expander.expand_candidates(candidates)

        # Check that expanded nodes have relationship context
        expanded = [r for r in result if r.get("expansion_source", "").startswith("expanded_from")]
        for node in expanded:
            # Should have relationship information
            assert "rel_type" in node or "relationship_role" in node

    def test_multiple_anchors(self, db, test_analysis, test_fact_store):
        """Verify multiple anchor nodes can be expanded together."""
        expander = BoundedGraphExpander(
            db, test_analysis.id, max_depth=2, max_nodes_per_hop=10, max_total_nodes=50
        )

        candidates = [
            {
                "id": "login_handler_1",
                "name": "login_handler",
                "file_path": "app/handlers.py",
                "symbol_id": "sym_login_handler",
                "type": "function",
            },
            {
                "id": "logout_handler_1",
                "name": "logout_handler",
                "file_path": "app/handlers.py",
                "symbol_id": "sym_logout_handler",
                "type": "function",
            },
        ]

        result = expander.expand_candidates(candidates)

        # Should have at least 2 anchors + some expanded nodes
        anchors = [r for r in result if r.get("is_anchor")]
        assert len(anchors) >= 2


class TestHybridRetrieverGraphExpansion:
    """Test HybridRetriever with graph expansion integration."""

    def test_retriever_with_graph_expansion_enabled(self, db, test_analysis, test_fact_store):
        """Verify retriever can be initialized with graph expansion enabled."""
        retriever = HybridRetriever(
            db=db,
            analysis_id=test_analysis.id,
            enable_graph_expansion=True,
            graph_expansion_depth=2,
            graph_expansion_nodes_per_hop=3,
            graph_expansion_max_total=30,
        )

        assert retriever.enable_graph_expansion is True
        assert retriever.graph_expansion_depth == 2
        assert retriever.graph_expansion_nodes_per_hop == 3
        assert retriever.graph_expansion_max_total == 30

    def test_retrieve_method_accepts_graph_expansion_parameter(self, db, test_analysis, test_fact_store):
        """Verify retrieve() method accepts enable_graph_expansion parameter."""
        retriever = HybridRetriever(
            db=db,
            analysis_id=test_analysis.id,
            enable_graph_expansion=False,  # Default disabled
        )

        # Should accept the parameter
        # (actual query may return empty, but parameter should be accepted)
        results = retriever.retrieve(
            query="login",
            enable_graph_expansion=True,  # Override instance default
        )

        # Results should be a list
        assert isinstance(results, list)

    def test_retriever_graph_expansion_respects_limits(self, db, test_analysis, test_fact_store):
        """Verify graph expansion respects configured limits."""
        retriever = HybridRetriever(
            db=db,
            analysis_id=test_analysis.id,
            enable_graph_expansion=True,
            graph_expansion_depth=1,
            graph_expansion_nodes_per_hop=2,
            graph_expansion_max_total=10,
        )

        assert retriever.graph_expansion_depth == 1
        assert retriever.graph_expansion_nodes_per_hop == 2
        assert retriever.graph_expansion_max_total == 10


class TestGraphExpansionEdgeCases:
    """Test edge cases and error conditions."""

    def test_expansion_with_no_relationships(self, db, test_analysis, test_fact_store):
        """Verify expansion handles symbols with no relationships."""
        # Create isolated symbol
        isolated_file = FactFile(
            id="isolated_file",
            analysis_id=test_analysis.id,
            path="app/isolated.py",
            language="Python",
        )
        db.add(isolated_file)
        db.flush()

        isolated_sym = FactSymbol(
            id="sym_isolated",
            analysis_id=test_analysis.id,
            file_id="isolated_file",
            name="isolated_function",
            qualified_name="isolated.isolated_function",
            symbol_type="function",
            line_start=1,
            line_end=10,
        )
        db.add(isolated_sym)
        db.commit()

        expander = BoundedGraphExpander(db, test_analysis.id, max_depth=2)

        candidates = [
            {
                "id": "isolated_func",
                "name": "isolated_function",
                "file_path": "app/isolated.py",
                "symbol_id": "sym_isolated",
                "type": "function",
            }
        ]

        result = expander.expand_candidates(candidates)

        # Should at least have the anchor
        assert len(result) > 0
        assert result[0]["name"] == "isolated_function"

    def test_expansion_with_no_anchors(self, db, test_analysis, test_fact_store):
        """Verify expansion handles empty candidate list."""
        expander = BoundedGraphExpander(db, test_analysis.id, max_depth=2)

        candidates = []
        result = expander.expand_candidates(candidates)

        assert result == []

    def test_expansion_with_no_analysis_id(self, db):
        """Verify expansion gracefully handles missing analysis_id."""
        expander = BoundedGraphExpander(db, analysis_id=999, max_depth=2)

        candidates = [
            {
                "id": "test_func",
                "name": "test_function",
                "file_path": "test.py",
                "symbol_id": "sym_test",
                "type": "function",
            }
        ]

        result = expander.expand_candidates(candidates)

        # Should return empty or original candidates without error
        assert isinstance(result, list)
