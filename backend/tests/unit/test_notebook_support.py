"""
Unit and integration tests for Jupyter Notebook (.ipynb) support.
Covers:
1. Jupytext in-memory conversion to py:percent with metadata_filter='-all'
2. Markdown and code cell handling
3. Notebook output isolation (preventing misleading output text from entering code)
4. Notebook magics (%pip, !ls, %%bash) conversion and AST parseability
5. Malformed/invalid notebook error handling
6. ASTParserManager parsing of .ipynb files
7. RepositoryToolLayer read_file and search_code behavior on .ipynb
8. Canonical path preservation and line coordinate consistency
"""
import json
import pytest
from pathlib import Path

from backend.intelligence.notebook import resolve_source_document, SourceDocument
from backend.intelligence.engine.scanner.detector import LanguageDetector
from backend.intelligence.engine.scanner.eligibility import FileEligibility, FileCategory
from backend.intelligence.engine.parser.manager import ASTParserManager
from backend.repository_tools.tools import RepositoryToolLayer
from backend.storage.memory import InMemoryObjectStorage
from backend.storage import set_storage
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol


SAMPLE_NOTEBOOK = {
    "cells": [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["# Legal Documents RAG Pipeline\n", "This pipeline indexes contracts.\n"]
        },
        {
            "cell_type": "code",
            "execution_count": 1,
            "metadata": {},
            "outputs": [
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": ["class FakeVectorStore:\n", "    def fake_method(): pass\n"]
                }
            ],
            "source": [
                "%pip install qdrant-client\n",
                "!ls -la\n",
                "import os\n",
                "from qdrant_client import QdrantClient\n\n",
                "class LegalVectorStore:\n",
                "    def __init__(self, host: str):\n",
                "        self.client = QdrantClient(host=host)\n\n",
                "    def search(self, query: str):\n",
                "        return self.client.search(collection_name='legal', query_vector=[0.1])\n"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": 2,
            "metadata": {},
            "outputs": [],
            "source": [
                "def initialize_pipeline():\n",
                "    return LegalVectorStore('localhost')\n"
            ]
        }
    ],
    "metadata": {
        "language_info": {"name": "python"}
    },
    "nbformat": 4,
    "nbformat_minor": 2
}


def test_resolve_source_document_non_notebook():
    doc = resolve_source_document("src/main.py", "def hello(): pass")
    assert doc.path == "src/main.py"
    assert doc.source == "def hello(): pass"
    assert doc.source_type == "source"
    assert doc.conversion_error is None


def test_resolve_source_document_valid_notebook():
    raw_json = json.dumps(SAMPLE_NOTEBOOK)
    doc = resolve_source_document("notebooks/rag.ipynb", raw_json)

    assert doc.path == "notebooks/rag.ipynb"
    assert doc.source_type == "notebook"
    assert doc.language == "Python"
    assert doc.conversion_error is None
    assert "# %% [markdown]" in doc.source
    assert "# %%" in doc.source
    assert "class LegalVectorStore:" in doc.source
    assert "def initialize_pipeline():" in doc.source

    # Verify outputs are isolated and discarded
    assert "class FakeVectorStore:" not in doc.source
    assert "def fake_method():" not in doc.source

    # Verify magics are commented out
    assert "# %pip install qdrant-client" in doc.source
    assert "# !ls -la" in doc.source


def test_resolve_source_document_malformed_notebook():
    doc = resolve_source_document("corrupt.ipynb", "{not valid json")
    assert doc.path == "corrupt.ipynb"
    assert doc.source == ""
    assert doc.conversion_error is not None
    assert doc.source_type == "notebook"


def test_scanner_and_eligibility_notebook_detection():
    lang = LanguageDetector.detect_language("notebooks/analysis.ipynb")
    assert lang == "Python"
    assert LanguageDetector.is_code_language("Python") is True

    category = FileEligibility.classify_file("notebooks/analysis.ipynb")
    assert category == FileCategory.SOURCE
    assert FileEligibility.is_analyzable_as_source("notebooks/analysis.ipynb") is True


def test_ast_parser_manager_parses_notebook(tmp_path):
    nb_path = tmp_path / "notebooks"
    nb_path.mkdir(parents=True)
    file_path = nb_path / "starter.ipynb"
    file_path.write_text(json.dumps(SAMPLE_NOTEBOOK), encoding="utf-8")

    manager = ASTParserManager(str(tmp_path))
    parsed = manager.parse_file("notebooks/starter.ipynb", "Python")

    assert parsed is not None
    assert parsed.file_path == "notebooks/starter.ipynb"
    assert parsed.language == "Python"
    # PythonProvider returns stdlib ast.Module
    import ast
    assert isinstance(parsed.ast, ast.Module)
    class_names = [n.name for n in ast.walk(parsed.ast) if isinstance(n, ast.ClassDef)]
    func_names = [n.name for n in ast.walk(parsed.ast) if isinstance(n, ast.FunctionDef)]
    assert "LegalVectorStore" in class_names
    assert "initialize_pipeline" in func_names

    # Verify SymbolAnalyzer extracts FactSymbol entities from the notebook AST
    from backend.intelligence.engine.analyzers.symbol import SymbolAnalyzer
    from backend.intelligence.rim.repository import RepositoryModel
    from backend.intelligence.rim.metadata import RepositoryMetadata

    repo_model = RepositoryModel(metadata=RepositoryMetadata(name="test", path=str(tmp_path)))
    analyzer = SymbolAnalyzer()
    analyzer.analyze(repo_model, {"notebooks/starter.ipynb": parsed})

    extracted_names = [e.name for e in repo_model.entities.values()]
    assert "LegalVectorStore" in extracted_names
    assert "initialize_pipeline" in extracted_names


def test_repository_tools_read_and_search_code_on_notebook(db):
    mock_storage = InMemoryObjectStorage()
    set_storage(mock_storage)

    blob_key = "repositories/test_hash/snapshots/snap1/notebooks/rag.ipynb"
    raw_nb = json.dumps(SAMPLE_NOTEBOOK)
    mock_storage.put_object(blob_key, raw_nb)

    user = User(id=99, github_id="gh99", username="analyst", email="analyst@example.com")
    db.add(user)
    db.flush()

    repo = Repository(id=99, url="https://github.com/org/rag-notebooks", user_id=99, repository_hash="test_hash")
    db.add(repo)
    db.flush()

    analysis = Analysis(id=99, repository_id=99, status="Completed")
    db.add(analysis)
    db.flush()

    fact_file = FactFile(
        id="99:notebooks/rag.ipynb",
        analysis_id=99,
        path="notebooks/rag.ipynb",
        language="Python",
        size=len(raw_nb),
        blob_name=blob_key,
        snapshot_id="snap1",
        is_binary=False,
    )
    db.add(fact_file)
    db.commit()

    tool_layer = RepositoryToolLayer(
        repo_name="rag-notebooks",
        analysis_id=99,
        db=db,
        repo_root=None,
    )

    # 1. read_file must return clean Python source lines, not JSON
    res = tool_layer.read_file("notebooks/rag.ipynb", start_line=1, end_line=30)
    assert res["path"] == "notebooks/rag.ipynb"
    assert "LegalVectorStore" in res["raw_text"]
    assert "{" not in res["raw_text"] or "cells" not in res["raw_text"]  # Not raw JSON
    assert "class FakeVectorStore" not in res["raw_text"]  # Discarded outputs

    # 2. search_code must match Python code and return canonical path and Python line numbers
    matches = tool_layer.search_code("LegalVectorStore")
    assert len(matches) >= 1
    assert matches[0]["file"] == "notebooks/rag.ipynb"
    assert "class LegalVectorStore" in matches[0]["snippet"]
    matched_line = matches[0]["line"]

    # Verify line coordinate consistency: reading that exact line from read_file gets the definition
    line_check = tool_layer.read_file("notebooks/rag.ipynb", start_line=matched_line, end_line=matched_line)
    assert "class LegalVectorStore" in line_check["raw_text"]

    # 3. search_code must NOT match text present only in cell outputs
    fake_matches = tool_layer.search_code("FakeVectorStore")
    assert len(fake_matches) == 0

    # 4. get_file_outline must work on canonical path
    fact_symbol = FactSymbol(
        id="99:sym_lvs",
        analysis_id=99,
        file_id="99:notebooks/rag.ipynb",
        name="LegalVectorStore",
        symbol_type="class",
        line_start=matched_line,
        line_end=matched_line + 5,
    )
    db.add(fact_symbol)
    db.commit()

    outline = tool_layer.get_file_outline("notebooks/rag.ipynb")
    assert outline["file"] == "notebooks/rag.ipynb"
    assert len(outline["symbols"]) == 1
    assert outline["symbols"][0]["name"] == "LegalVectorStore"
    assert outline["symbols"][0]["line_start"] == matched_line


def test_duplicate_symbols_across_cells(tmp_path):
    """Verify multiple definitions of the same symbol across notebook cells do not crash the analyzer."""
    notebook_with_duplicates = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["def run_query(): return 1\n"]
            },
            {
                "cell_type": "code",
                "execution_count": 2,
                "metadata": {},
                "outputs": [],
                "source": ["def run_query(): return 2\n"]
            }
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 2
    }

    nb_file = tmp_path / "dup.ipynb"
    nb_file.write_text(json.dumps(notebook_with_duplicates), encoding="utf-8")

    manager = ASTParserManager(str(tmp_path))
    parsed = manager.parse_file("dup.ipynb", "Python")

    from backend.intelligence.engine.analyzers.symbol import SymbolAnalyzer
    from backend.intelligence.rim.repository import RepositoryModel
    from backend.intelligence.rim.metadata import RepositoryMetadata

    repo_model = RepositoryModel(metadata=RepositoryMetadata(name="test_dup", path=str(tmp_path)))
    analyzer = SymbolAnalyzer()
    analyzer.analyze(repo_model, {"dup.ipynb": parsed})

    # Symbol exists and did not violate entity uniqueness
    func_entities = [e for e in repo_model.entities.values() if e.name == "run_query"]
    assert len(func_entities) == 1


def test_strip_cell_widgets_metadata():
    """Verify that colab and referenced_widgets cell metadata are stripped."""
    notebook_with_widgets = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {
                    "id": "cell_1",
                    "colab": {
                        "base_uri": "https://localhost:8080/",
                        "referenced_widgets": ["widget-uuid-1", "widget-uuid-2"] * 50
                    }
                },
                "outputs": [],
                "source": ["x = 42\n"]
            }
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 2
    }
    doc = resolve_source_document("test.ipynb", json.dumps(notebook_with_widgets))
    assert "referenced_widgets" not in doc.source
    assert "base_uri" not in doc.source
    assert "x = 42" in doc.source


def test_read_file_context_overflow_guard():
    """Verify that unbounded reads on files > 150 lines are intercepted with guidance."""
    mem_storage = InMemoryObjectStorage()
    set_storage(mem_storage)

    # 200 lines
    large_content = "\n".join([f"line_{i} = {i}" for i in range(200)])
    mem_storage.put_object("repositories/mock-hash/snapshots/snap1/big_file.py", large_content)

    class MockUser:
        id = 1

    class MockAnalysis:
        id = 1
        repository_id = 1

    class MockRepo:
        id = 1
        repository_hash = "mock-hash"

    class MockDB:
        def query(self, model):
            class MockQuery:
                def filter(self, *args):
                    return self
                def first(self):
                    if model == MockAnalysis or model.__name__ == "Analysis":
                        return MockAnalysis()
                    return MockRepo()
            return MockQuery()

    tool_layer = RepositoryToolLayer("mock-repo", analysis_id=1, db=MockDB(), user_id=1)
    
    # Unbounded read on > 150 lines file must be intercepted
    res = tool_layer.read_file("big_file.py")
    assert res.get("error") == "context_overflow_protection"
    assert "Refusing full file read" in res.get("message")
    assert res.get("total_lines") == 200

    # Bounded read within safe limits works
    bounded_res = tool_layer.read_file("big_file.py", start_line=10, end_line=30)
    assert bounded_res.get("start_line") == 10
    assert bounded_res.get("end_line") == 30
    assert "line_10 = 10" in bounded_res.get("content")


