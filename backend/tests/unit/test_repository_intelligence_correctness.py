"""
Unit and regression test suite for Repository Intelligence Correctness.
Verifies:
1. End-to-end AST parsing, symbol extraction, and relational Fact Store persistence.
2. FactSymbol.file_id foreign key mapping to FactFile.id and FactFile.symbols ORM integrity.
3. Exploration queries referencing specific files and retrieving exact function/class names.
4. Explanation context assembly enriching symbols from relevant files.
5. Strict repository isolation (A -> B -> A) with overlapping concept names.
6. Honest handling of unindexed or non-existent repositories without hallucinations.
"""
import ast
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from backend.intelligence.engine.analyzers.symbol import SymbolAnalyzer
from backend.intelligence.engine.parser.providers.base import ParsedFile
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.store.fact_store import save_rim_to_fact_store
from backend.agent.modes import execute_explore, execute_explain
from backend.agent.context.assembler import ContextAssembler, ContextAssemblyRequest


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        user = User(id=1, github_id="gh_1", username="dev1", email="dev1@test.com")
        session.add(user)
        session.commit()
        yield session
    finally:
        session.close()


def test_fact_store_symbol_file_foreign_key_linking(db_session):
    """
    Verifies that FactSymbol.file_id is correctly mapped to FactFile.id,
    and FactFile.symbols correctly returns all child symbols.
    """
    repo = Repository(id=10, url="https://github.com/org/pls-cli.git", user_id=1)
    analysis = Analysis(id=100, repository_id=10, status="Completed", engine_version="v1.0")
    db_session.add_all([repo, analysis])
    db_session.commit()

    code = """
def run_command(cmd):
    return cmd

def parse_args():
    return []

def main():
    return run_command(parse_args())
"""
    parsed = ParsedFile(
        file_path="pls_cli/please.py",
        language="Python",
        source=code,
        ast=ast.parse(code)
    )

    model = RepositoryModel(metadata=RepositoryMetadata(name="pls-cli", path="."))
    analyzer = SymbolAnalyzer()
    analyzer.analyze(model, {"pls_cli/please.py": parsed})

    save_rim_to_fact_store(db_session, analysis.id, model)
    db_session.commit()

    # Verify FactFile
    fact_file = db_session.query(FactFile).filter(
        FactFile.analysis_id == 100,
        FactFile.path == "pls_cli/please.py"
    ).first()
    assert fact_file is not None
    assert len(fact_file.symbols) == 3

    # Verify FactSymbol
    symbols = db_session.query(FactSymbol).filter(
        FactSymbol.analysis_id == 100
    ).order_by(FactSymbol.line_start).all()
    assert len(symbols) == 3

    symbol_names = [s.name for s in symbols]
    assert symbol_names == ["run_command", "parse_args", "main"]

    for s in symbols:
        assert s.file_id == fact_file.id
        assert s.file.path == "pls_cli/please.py"


def test_execute_explore_specific_file_query(db_session):
    """
    Verifies that execute_explore correctly answers queries referencing a specific file
    and returns its cataloged symbols.
    """
    repo = Repository(id=10, url="https://github.com/org/pls-cli.git", user_id=1)
    analysis = Analysis(id=100, repository_id=10, status="Completed", engine_version="v1.0")
    db_session.add_all([repo, analysis])
    db_session.commit()

    code = """
def create_quote(text, author):
    return {"text": text, "author": author}

def list_quotes():
    return []
"""
    parsed = ParsedFile(
        file_path="pls_cli/quotes.py",
        language="Python",
        source=code,
        ast=ast.parse(code)
    )

    model = RepositoryModel(metadata=RepositoryMetadata(name="pls-cli", path="."))
    analyzer = SymbolAnalyzer()
    analyzer.analyze(model, {"pls_cli/quotes.py": parsed})

    save_rim_to_fact_store(db_session, analysis.id, model)
    db_session.commit()

    res = execute_explore(
        user_requirement="What functions are defined in pls_cli/quotes.py? Give me their exact function names.",
        repository_id="pls-cli",
        user_id=1,
        db=db_session,
    )

    assert "create_quote" in res["response"]
    assert "list_quotes" in res["response"]
    assert "pls_cli/quotes.py" in res["response"]

    entity_names = [e["name"] for e in res["entities"]]
    assert "create_quote" in entity_names
    assert "list_quotes" in entity_names


def test_context_assembler_enriches_symbols_from_matched_files(db_session):
    """
    Verifies that ContextAssembler enriches relevant_symbols with symbols defined
    inside relevant files.
    """
    repo = Repository(id=10, url="https://github.com/org/quote-service.git", user_id=1)
    analysis = Analysis(id=100, repository_id=10, status="Completed", engine_version="v1.0")
    db_session.add_all([repo, analysis])
    db_session.commit()

    code = """
def fetch_quote_by_id(quote_id):
    return {"id": quote_id}
"""
    parsed = ParsedFile(
        file_path="src/quotes.py",
        language="Python",
        source=code,
        ast=ast.parse(code)
    )

    model = RepositoryModel(metadata=RepositoryMetadata(name="quote-service", path="."))
    analyzer = SymbolAnalyzer()
    analyzer.analyze(model, {"src/quotes.py": parsed})

    save_rim_to_fact_store(db_session, analysis.id, model)
    db_session.commit()

    assembler = ContextAssembler(llm_service=None)
    req = ContextAssemblyRequest(
        repository_id="quote-service",
        analysis_id=100,
        requirement="Explain the implementation in src/quotes.py",
    )
    ctx = assembler.assemble(req, db=db_session)

    assert "src/quotes.py" in ctx.relevant_files
    symbol_names = [s["name"] for s in ctx.relevant_symbols]
    assert "fetch_quote_by_id" in symbol_names


def test_adversarial_overlapping_concepts_repository_isolation(db_session):
    """
    Verifies strict A -> B -> A repository isolation with overlapping concept queries.
    """
    repo_a = Repository(id=1, url="https://github.com/org/alpha-app.git", user_id=1)
    analysis_a = Analysis(id=10, repository_id=1, status="Completed", engine_version="v1.0")

    repo_b = Repository(id=2, url="https://github.com/org/beta-app.git", user_id=1)
    analysis_b = Analysis(id=20, repository_id=2, status="Completed", engine_version="v1.0")

    db_session.add_all([repo_a, analysis_a, repo_b, analysis_b])
    db_session.commit()

    # Index Alpha Repository
    alpha_code = """
class AuthServiceA:
    def login_a(self, user):
        pass
"""
    parsed_a = ParsedFile(
        file_path="src/alpha_auth.py",
        language="Python",
        source=alpha_code,
        ast=ast.parse(alpha_code)
    )
    model_a = RepositoryModel(metadata=RepositoryMetadata(name="alpha-app", path="."))
    analyzer = SymbolAnalyzer()
    analyzer.analyze(model_a, {"src/alpha_auth.py": parsed_a})
    save_rim_to_fact_store(db_session, analysis_a.id, model_a)

    # Index Beta Repository
    beta_code = """
class AuthServiceB:
    def login_b(self, user):
        pass
"""
    parsed_b = ParsedFile(
        file_path="src/beta_auth.py",
        language="Python",
        source=beta_code,
        ast=ast.parse(beta_code)
    )
    model_b = RepositoryModel(metadata=RepositoryMetadata(name="beta-app", path="."))
    analyzer.analyze(model_b, {"src/beta_auth.py": parsed_b})
    save_rim_to_fact_store(db_session, analysis_b.id, model_b)
    db_session.commit()

    # 1. Query Repo A
    res_a1 = execute_explore(
        user_requirement="Where is authentication login implemented?",
        repository_id="alpha-app",
        user_id=1,
        db=db_session,
    )
    assert "AuthServiceA" in res_a1["response"] or "login_a" in res_a1["response"]
    assert "AuthServiceB" not in res_a1["response"]
    assert "login_b" not in res_a1["response"]

    # 2. Query Repo B
    res_b = execute_explore(
        user_requirement="Where is authentication login implemented?",
        repository_id="beta-app",
        user_id=1,
        db=db_session,
    )
    assert "AuthServiceB" in res_b["response"] or "login_b" in res_b["response"]
    assert "AuthServiceA" not in res_b["response"]
    assert "login_a" not in res_b["response"]

    # 3. Query Repo A again (A -> B -> A)
    res_a2 = execute_explore(
        user_requirement="Where is authentication login implemented?",
        repository_id="alpha-app",
        user_id=1,
        db=db_session,
    )
    assert "AuthServiceA" in res_a2["response"] or "login_a" in res_a2["response"]
    assert "AuthServiceB" not in res_a2["response"]
    assert "login_b" not in res_a2["response"]


def test_unindexed_or_nonexistent_repository_honest_response(db_session):
    """
    Verifies that querying an unanalyzed repository returns an honest notification
    without hallucinating facts or inspecting foreign state.
    """
    repo = Repository(id=5, url="https://github.com/org/empty-repo.git", user_id=1)
    db_session.add(repo)
    db_session.commit()

    res = execute_explore(
        user_requirement="What functions are in please.py?",
        repository_id="empty-repo",
        user_id=1,
        db=db_session,
    )

    assert "has not been analyzed yet or has no active index" in res["response"]
    assert res["entities"] == []
