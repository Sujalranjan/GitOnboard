import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from backend.routers.repo.graph import get_knowledge_graph, get_knowledge_graph_node
from backend.models.fact_store import (
    FactFile,
    FactSymbol,
    FactRelationship,
    FactRoute,
    FactDatabaseObject,
    FactCapability,
    FactCapabilityMember,
)
from backend.models.repository import Repository, Analysis
from backend.models.user import User


class TestKnowledgeGraphEndpoints:
    """Unit tests for the Layer 4 Fact Store Knowledge Graph API."""

    @pytest.fixture
    def mock_db_and_context(self):
        db = MagicMock()
        user = User(id=1, email="test@example.com")
        repo = Repository(id=10, user_id=1, url="https://github.com/org/test-repo", repository_hash="test-uuid")
        repo.name = "test-repo"
        analysis = Analysis(id=99, repository_id=10, status="Completed")

        # Mock Fact Store models
        file1 = FactFile(id="f1", analysis_id=99, path="src/auth.py", language="python", size=1200)
        file2 = FactFile(id="f2", analysis_id=99, path="src/utils.py", language="python", size=800)

        sym1 = FactSymbol(
            id="s1",
            analysis_id=99,
            file_id="f1",
            name="login",
            qualified_name="src.auth.login",
            symbol_type="function",
            line_start=10,
            line_end=25,
        )
        sym1.file = file1

        sym2 = FactSymbol(
            id="s2",
            analysis_id=99,
            file_id="f2",
            name="hash_password",
            qualified_name="src.utils.hash_password",
            symbol_type="function",
            line_start=5,
            line_end=15,
        )
        sym2.file = file2

        rel1 = FactRelationship(
            id="r1",
            analysis_id=99,
            from_symbol_id="s1",
            to_symbol_id="s2",
            rel_type="CALLS",
            evidence_line=18,
            status="CONFIRMED",
        )
        rel2 = FactRelationship(
            id="r2",
            analysis_id=99,
            from_symbol_id="f1",
            to_symbol_id="f2",
            rel_type="IMPORTS",
            evidence_line=1,
            status="CONFIRMED",
        )
        rel3 = FactRelationship(
            id="r3",
            analysis_id=99,
            from_symbol_id="f1",
            to_symbol_id="s1",
            rel_type="DECLARES",
            evidence_line=10,
            status="CONFIRMED",
        )

        route1 = FactRoute(
            id="rt1",
            analysis_id=99,
            method="POST",
            path="/api/login",
            handler_symbol_id="s1",
        )

        cap1 = FactCapability(
            id="cap1",
            analysis_id=99,
            name="Authentication",
            capability_type="AUTH",
            status="CONFIRMED",
            evidence_summary="Session & password verification",
        )

        member1 = FactCapabilityMember(
            id="m1",
            capability_id="cap1",
            symbol_id="s1",
            role="entry_point",
        )

        # Configure mock queries
        def mock_query(model):
            q = MagicMock()
            if model == FactFile:
                q.filter.return_value.all.return_value = [file1, file2]
                q.filter.return_value.first.return_value = file1
            elif model == FactSymbol:
                q.filter.return_value.all.return_value = [sym1, sym2]
                q.filter.return_value.first.return_value = sym1
            elif model == FactRelationship:
                q.filter.return_value.all.return_value = [rel1, rel2, rel3]
            elif model == FactRoute:
                q.filter.return_value.all.return_value = [route1]
                q.filter.return_value.first.return_value = route1
            elif model == FactDatabaseObject:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.first.return_value = None
            elif model == FactCapability:
                q.filter.return_value.all.return_value = [cap1]
                q.filter.return_value.first.return_value = cap1
                q.join.return_value.filter.return_value.all.return_value = [cap1]
            elif model == FactCapabilityMember:
                q.filter.return_value.all.return_value = [member1]
            else:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = mock_query
        return db, user, repo, analysis

    def test_get_knowledge_graph_success(self, monkeypatch, mock_db_and_context):
        db, user, repo, analysis = mock_db_and_context

        # Mock get_latest_analysis
        monkeypatch.setattr(
            "backend.routers.repo.graph.get_latest_analysis",
            lambda repo_name, db_session, current_user: (repo, analysis),
        )

        result = get_knowledge_graph(
            repo_name="test-repo",
            view="all",
            db=db,
            current_user=user,
        )

        assert result["repo_name"] == "test-repo"
        assert result["analysis_id"] == 99
        assert "nodes" in result
        assert "edges" in result
        assert "stats" in result

        # Verify stats
        stats = result["stats"]
        assert stats["raw_total_files"] == 2
        assert stats["raw_total_symbols"] == 2
        assert stats["raw_total_relationships"] == 3
        assert stats["raw_total_routes"] == 1
        assert stats["raw_total_capabilities"] == 1

        # Check node types present
        node_names = {n["name"] for n in result["nodes"]}
        assert "login" in node_names
        assert "hash_password" in node_names

    def test_get_knowledge_graph_view_filter_calls(self, monkeypatch, mock_db_and_context):
        db, user, repo, analysis = mock_db_and_context

        monkeypatch.setattr(
            "backend.routers.repo.graph.get_latest_analysis",
            lambda repo_name, db_session, current_user: (repo, analysis),
        )

        result = get_knowledge_graph(
            repo_name="test-repo",
            view="calls",
            db=db,
            current_user=user,
        )

        edge_types = {e["type"] for e in result["edges"]}
        assert edge_types == {"CALLS"}

    def test_get_knowledge_graph_node_details(self, monkeypatch, mock_db_and_context):
        db, user, repo, analysis = mock_db_and_context

        monkeypatch.setattr(
            "backend.routers.repo.graph.get_latest_analysis",
            lambda repo_name, db_session, current_user: (repo, analysis),
        )

        result = get_knowledge_graph_node(
            repo_name="test-repo",
            node_id="s1",
            db=db,
            current_user=user,
        )

        assert "node" in result
        assert result["node"]["name"] == "login"
        assert result["node"]["type"] == "FUNCTION"
        assert "incoming" in result
        assert "outgoing" in result
        assert "capabilities" in result

    def test_get_knowledge_graph_repo_not_found(self, monkeypatch, mock_db_and_context):
        db, user, _, _ = mock_db_and_context

        def raise_404(*args, **kwargs):
            raise HTTPException(status_code=404, detail="Repository not found")

        monkeypatch.setattr(
            "backend.routers.repo.graph.get_latest_analysis",
            raise_404,
        )

        with pytest.raises(HTTPException) as exc_info:
            get_knowledge_graph(
                repo_name="nonexistent-repo",
                db=db,
                current_user=user,
            )
        assert exc_info.value.status_code == 404
