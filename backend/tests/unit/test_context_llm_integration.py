"""
Integration tests: RepositoryContext → LLM system prompt injection.

Verifies that assembled repository context is properly formatted and injected
into LLM system prompts and reaches the production LLM execution path.
"""
import tempfile
from pathlib import Path
import pytest

from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import ContextAssemblyRequest, ContextBudget
from backend.agent.context.formatter import RepositoryContextFormatter
from backend.database import Base, SessionLocal, engine
from backend.models.fact_store import FactCapability, FactFile, FactRoute, FactSymbol
from backend.models.user import User
from backend.models.repository import Analysis, Repository
from backend.services.rim_qa_protocol import QAProtocolAdapter, ToolSpec


@pytest.fixture(autouse=True)
def init_db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_context_assembly_to_formatter_end_to_end(init_db):
    """
    Test complete flow: ContextAssembler → RepositoryContext → Formatter → LLM text.
    """
    db = init_db

    # Setup: Create user, repo, analysis
    user = User(id=1, github_id="1", username="testuser", email="test@example.com")
    db.merge(user)
    db.commit()

    repo = Repository(id=1, user_id=1, url="https://github.com/test/repo")
    db.merge(repo)
    db.commit()

    analysis = Analysis(id=1, repository_id=1, status="Completed")
    db.merge(analysis)
    db.commit()

    # Seed fact store data
    ff = FactFile(
        id="test:file:auth.py",
        analysis_id=1,
        path="auth.py",
        size=500,
        is_binary=False,
    )
    ff2 = FactFile(
        id="test:file:utils.py",
        analysis_id=1,
        path="utils.py",
        size=300,
        is_binary=False,
    )

    cap = FactCapability(
        id="test:cap:auth",
        analysis_id=1,
        name="Authentication",
        capability_type="AUTH",
        status="ACTIVE",
        evidence_summary="User login and JWT validation",
    )

    sym = FactSymbol(
        id="test:sym:authenticate_user",
        analysis_id=1,
        name="authenticate_user",
        symbol_type="function",
        file_id="test:file:auth.py",
        metadata_json={"signature": "def authenticate_user(username, password)"},
    )

    sym2 = FactSymbol(
        id="test:sym:hash_password",
        analysis_id=1,
        name="hash_password",
        symbol_type="function",
        file_id="test:file:utils.py",
        metadata_json={"signature": "def hash_password(password)"},
    )

    route = FactRoute(
        id="test:route:login",
        analysis_id=1,
        method="POST",
        path="/api/auth/login",
        handler_symbol_id="test:sym:authenticate_user",
    )

    db.merge(ff)
    db.merge(ff2)
    db.merge(cap)
    db.merge(sym)
    db.merge(sym2)
    db.merge(route)
    db.commit()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create dummy repo files
        auth_file = Path(tmpdir) / "auth.py"
        auth_file.write_text(
            "def authenticate_user(username, password):\n    return True\n",
            encoding="utf-8"
        )
        utils_file = Path(tmpdir) / "utils.py"
        utils_file.write_text(
            "def hash_password(password):\n    return 'hashed'\n",
            encoding="utf-8"
        )

        # Step 1: Assemble repository context
        assembler = ContextAssembler()
        req = ContextAssemblyRequest(
            repository_id="1",
            requirement="Add password validation to authenticate_user",
            worktree_path=tmpdir,
            analysis_id=1,
        )

        context = assembler.assemble(req, db=db)

        # Verify context is complete
        assert context.repository_id == "1"
        assert len(context.evidence) > 0
        assert len(context.relevant_files) > 0
        assert len(context.relevant_symbols) > 0
        assert context.capabilities  # Should have matched Authentication capability
        assert context.contract.completeness.value in ["COMPLETE", "PARTIAL"]

        # Step 2: Format context for LLM
        formatter = RepositoryContextFormatter()
        formatted_text = formatter.format_to_system_prompt_block(context, max_chars=8000)

        # Verify formatted text contains key information
        assert "### REPOSITORY_CONTEXT" in formatted_text
        assert "authenticate_user" in formatted_text
        assert "password" in formatted_text.lower()
        assert "Completeness:" in formatted_text
        assert context.contract.completeness.value in formatted_text

        # Step 3: Verify can be injected into system prompt
        protocol = QAProtocolAdapter()
        tool_specs = [
            ToolSpec(
                name="search_repository",
                description="Search the repository",
                parameters={"type": "object", "properties": {"query": {"type": "string"}}}
            )
        ]

        system_prompt_parts = protocol.build_system_prompt(
            tool_specs=tool_specs,
            rim_metadata_block=formatted_text
        )

        # Verify formatted context reached system prompt
        assert formatted_text in system_prompt_parts.full_text
        assert "### REPOSITORY_CONTEXT" in system_prompt_parts.full_text


def test_context_formatter_preserves_metadata(init_db):
    """
    Test that formatter preserves all critical metadata without data loss.
    """
    db = init_db

    # Setup
    user = User(id=1, github_id="1", username="testuser", email="test@example.com")
    db.merge(user)
    db.commit()

    repo = Repository(id=1, user_id=1, url="https://github.com/test/repo")
    db.merge(repo)
    db.commit()

    analysis = Analysis(id=1, repository_id=1, status="Completed")
    db.merge(analysis)
    db.commit()

    # Create multiple entities
    files = []
    for i in range(5):
        ff = FactFile(
            id=f"test:file:module{i}.py",
            analysis_id=1,
            path=f"module{i}.py",
            size=100 + i * 50,
            is_binary=False,
        )
        files.append(ff)
        db.merge(ff)

    symbols = []
    for i in range(8):
        sym = FactSymbol(
            id=f"test:sym:function{i}",
            analysis_id=1,
            name=f"function{i}",
            symbol_type="function",
            file_id=f"test:file:module{i % 5}.py",
        )
        symbols.append(sym)
        db.merge(sym)

    db.commit()

    with tempfile.TemporaryDirectory() as tmpdir:
        assembler = ContextAssembler()
        req = ContextAssemblyRequest(
            repository_id="1",
            requirement="refactor function module implementation",
            worktree_path=tmpdir,
            analysis_id=1,
        )

        context = assembler.assemble(req, db=db)

        # Verify completeness - context should have evidence even if files not matched
        assert len(context.evidence) > 0
        # May or may not have files depending on keyword matching
        # But should have metadata about the repository

        # Format and verify no data loss
        formatter = RepositoryContextFormatter()
        formatted_text = formatter.format_to_system_prompt_block(context)

        # Check key info is present if items exist
        if context.relevant_files:
            for f in context.relevant_files[:3]:
                assert f in formatted_text

        if context.relevant_symbols:
            for sym in context.relevant_symbols[:3]:
                assert sym["name"] in formatted_text

        # Verify JSON summary works
        summary = formatter.format_as_json_summary(context)
        assert summary["repository_id"] == "1"
        assert summary["counts"]["files"] > 0
        assert summary["counts"]["symbols"] > 0
        assert summary["counts"]["evidence"] > 0


def test_context_in_system_prompt_not_truncated(init_db):
    """
    Test that RepositoryContext formatted for system prompt respects token budgets
    and is not excessively truncated.
    """
    db = init_db

    user = User(id=1, github_id="1", username="testuser", email="test@example.com")
    db.merge(user)
    db.commit()

    repo = Repository(id=1, user_id=1, url="https://github.com/test/repo")
    db.merge(repo)
    db.commit()

    analysis = Analysis(id=1, repository_id=1, status="Completed")
    db.merge(analysis)
    db.commit()

    # Create many entities
    for i in range(20):
        ff = FactFile(
            id=f"test:file:file{i}.py",
            analysis_id=1,
            path=f"src/file{i}.py",
            size=1000,
            is_binary=False,
        )
        db.merge(ff)

    db.commit()

    with tempfile.TemporaryDirectory() as tmpdir:
        assembler = ContextAssembler()
        req = ContextAssemblyRequest(
            repository_id="1",
            requirement="add feature x",
            worktree_path=tmpdir,
            analysis_id=1,
            context_budget=ContextBudget(
                max_files=20,
                max_symbols=30,
                max_total_evidence_size_kb=256,
            ),
        )

        context = assembler.assemble(req, db=db)

        # Format with reasonable max_chars (6000-8000 typical for system prompts)
        formatter = RepositoryContextFormatter()
        formatted_text = formatter.format_to_system_prompt_block(
            context,
            max_chars=6000,
            include_evidence_provenance=False,
        )

        # Verify formatter respects max_chars
        assert len(formatted_text) <= 6000
        assert "### REPOSITORY_CONTEXT" in formatted_text

        # Verify still contains meaningful content
        assert len(formatted_text) > 300  # At least 300 chars of content (header + metadata)


def test_extracted_evidence_for_context_window(init_db):
    """
    Test that high-priority evidence can be extracted for LLM context window.
    """
    db = init_db

    user = User(id=1, github_id="1", username="testuser", email="test@example.com")
    db.merge(user)
    db.commit()

    repo = Repository(id=1, user_id=1, url="https://github.com/test/repo")
    db.merge(repo)
    db.commit()

    analysis = Analysis(id=1, repository_id=1, status="Completed")
    db.merge(analysis)
    db.commit()

    ff = FactFile(
        id="test:file:auth.py",
        analysis_id=1,
        path="auth.py",
        size=500,
        is_binary=False,
    )
    db.merge(ff)
    db.commit()

    with tempfile.TemporaryDirectory() as tmpdir:
        auth_file = Path(tmpdir) / "auth.py"
        auth_file.write_text("def login():\n    pass\n", encoding="utf-8")

        assembler = ContextAssembler()
        req = ContextAssemblyRequest(
            repository_id="1",
            requirement="add login",
            worktree_path=tmpdir,
            analysis_id=1,
        )

        context = assembler.assemble(req, db=db)

        formatter = RepositoryContextFormatter()
        evidence = formatter.extract_evidence_for_context_window(
            context,
            focus_types=["retrieval", "source_excerpt"],
            max_items=5,
        )

        # Verify evidence extraction
        assert isinstance(evidence, list)
        assert len(evidence) <= 5
        for item in evidence:
            assert "source_type" in item
            assert "summary" in item
            assert "relevance" in item
            assert "confidence" in item


def test_repository_context_in_system_prompt_construction(init_db):
    """
    Test that RepositoryContext formatted block is properly injected into QAProtocolAdapter
    system prompt without corrupting other sections.
    """
    db = init_db

    user = User(id=1, github_id="1", username="testuser", email="test@example.com")
    db.merge(user)
    db.commit()

    repo = Repository(id=1, user_id=1, url="https://github.com/test/repo")
    db.merge(repo)
    db.commit()

    analysis = Analysis(id=1, repository_id=1, status="Completed")
    db.merge(analysis)
    db.commit()

    ff = FactFile(
        id="test:file:main.py",
        analysis_id=1,
        path="main.py",
        size=300,
        is_binary=False,
    )
    db.merge(ff)
    db.commit()

    with tempfile.TemporaryDirectory() as tmpdir:
        main_file = Path(tmpdir) / "main.py"
        main_file.write_text("def main():\n    pass\n", encoding="utf-8")

        assembler = ContextAssembler()
        req = ContextAssemblyRequest(
            repository_id="1",
            requirement="enhance main function",
            worktree_path=tmpdir,
            analysis_id=1,
        )

        context = assembler.assemble(req, db=db)
        formatter = RepositoryContextFormatter()
        context_block = formatter.format_to_system_prompt_block(context)

        # Build system prompt with RepositoryContext
        protocol = QAProtocolAdapter()
        tool_specs = [
            ToolSpec(
                name="read_file",
                description="Read file",
                parameters={"type": "object"}
            ),
            ToolSpec(
                name="search_repository",
                description="Search",
                parameters={"type": "object"}
            ),
        ]

        prompt_parts = protocol.build_system_prompt(
            tool_specs=tool_specs,
            rim_metadata_block=context_block,
        )

        # Verify all sections present and intact
        assert "CRITICAL:" in prompt_parts.grounding_and_protocol_text
        assert "RESPONSE FORMAT" in prompt_parts.grounding_and_protocol_text
        assert "### AVAILABLE TOOLS" in prompt_parts.tool_catalog_text
        assert "read_file" in prompt_parts.tool_catalog_text
        assert "search_repository" in prompt_parts.tool_catalog_text
        assert "### REPOSITORY_CONTEXT" in prompt_parts.rim_metadata_text
        assert context_block in prompt_parts.rim_metadata_text

        # Verify full_text is proper concatenation
        full = prompt_parts.full_text
        assert "CRITICAL:" in full
        assert "### AVAILABLE TOOLS" in full
        assert "### REPOSITORY_CONTEXT" in full
