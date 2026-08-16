"""
Unit tests for RepositoryToolLayer: security boundaries, hybrid search, file slice reading, and graph queries.
"""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from backend.repository_tools import (
    RepositoryToolLayer,
    RepositorySecurityError,
    validate_repo_path,
)
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship


@pytest.fixture
def temp_repo(tmp_path):
    """Creates a temporary repository directory tree for testing."""
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()

    # Source files
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text(
        "import os\n\ndef entrypoint():\n    print('Hello World')\n\nclass AppService:\n    def run(self):\n        pass\n",
        encoding="utf-8"
    )
    (src_dir / "auth.py").write_text(
        "def authenticate_user(token: str):\n    return token == 'secret'\n",
        encoding="utf-8"
    )

    # Documentation files
    (repo_dir / "README.md").write_text("# Sample Project\n\nThis is a sample project.\n", encoding="utf-8")
    (repo_dir / "ARCHITECTURE.md").write_text("# Architecture\n\nLayered architecture.\n", encoding="utf-8")
    (repo_dir / "AGENTS.md").write_text("# Agent Instructions\n\nAlways run pytest before committing.\n", encoding="utf-8")
    (repo_dir / "CLAUDE.md").write_text("# Claude Guidance\n\nUse Python 3.12.\n", encoding="utf-8")

    # Binary file
    (repo_dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    # Deep nested file
    docs_dir = repo_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "api.md").write_text("# API Reference\n\nEndpoint list.\n", encoding="utf-8")

    return repo_dir


def test_read_file_success(temp_repo):
    tools = RepositoryToolLayer(repo_name="sample_repo", repo_root=temp_repo)
    result = tools.read_file("src/main.py", start_line=1, end_line=4)

    assert result["path"] == "src/main.py"
    assert result["start_line"] == 1
    assert result["end_line"] == 4
    assert "1 | import os" in result["content"]
    assert "def entrypoint():" in result["content"]


def test_read_file_security_path_traversal(temp_repo):
    tools = RepositoryToolLayer(repo_name="sample_repo", repo_root=temp_repo)

    with pytest.raises(RepositorySecurityError, match="Path traversal detected|Path escapes repository root"):
        tools.read_file("../../etc/passwd")

    with pytest.raises(RepositorySecurityError, match="Path traversal detected|Path escapes repository root"):
        tools.read_file("src/../../outside.txt")


def test_read_file_security_binary_rejection(temp_repo):
    tools = RepositoryToolLayer(repo_name="sample_repo", repo_root=temp_repo)

    with pytest.raises(RepositorySecurityError, match="Binary files cannot be read as text"):
        tools.read_file("image.png")


def test_read_file_security_clamping(temp_repo):
    tools = RepositoryToolLayer(repo_name="sample_repo", repo_root=temp_repo)
    result = tools.read_file("src/main.py", start_line=1, end_line=9999)

    # File only has 8 lines, clamped to 8
    assert result["end_line"] == 8
    assert result["total_lines"] == 8


def test_find_files(temp_repo):
    tools = RepositoryToolLayer(repo_name="sample_repo", repo_root=temp_repo)
    matches = tools.find_files("*.md")
    paths = [m["path"] for m in matches]

    assert "README.md" in paths
    assert "ARCHITECTURE.md" in paths
    assert "AGENTS.md" in paths
    assert "CLAUDE.md" in paths
    assert "docs/api.md" in paths


def test_search_code_lexical(temp_repo):
    tools = RepositoryToolLayer(repo_name="sample_repo", repo_root=temp_repo)
    matches = tools.search_code("authenticate_user")

    assert len(matches) >= 1
    assert matches[0]["file"] == "src/auth.py"
    assert "authenticate_user" in matches[0]["snippet"]


def test_hybrid_search_repository(temp_repo):
    tools = RepositoryToolLayer(repo_name="sample_repo", repo_root=temp_repo)
    results = tools.search_repository("auth")

    # Should find file and lexical matches
    assert any("auth" in r.get("file", "").lower() for r in results)


def test_db_backed_symbols_and_relationships(temp_repo):
    mock_db = MagicMock()
    
    # Mock symbols
    mock_sym = MagicMock()
    mock_sym.id = "sym_1"
    mock_sym.name = "authenticate_user"
    mock_sym.qualified_name = "src.auth.authenticate_user"
    mock_sym.symbol_type = "function"
    mock_sym.line_start = 1
    mock_sym.line_end = 2
    
    # Mock query
    mock_query = MagicMock()
    mock_db.query.return_value = mock_query
    mock_query.join.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.all.return_value = [(mock_sym, "src/auth.py")]
    
    tools = RepositoryToolLayer(repo_name="sample_repo", analysis_id=1, db=mock_db, repo_root=temp_repo)
    
    symbols = tools.get_symbol("authenticate")
    assert len(symbols) == 1
    assert symbols[0]["name"] == "authenticate_user"
    assert symbols[0]["file"] == "src/auth.py"
