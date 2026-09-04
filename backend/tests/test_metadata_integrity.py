"""
Comprehensive test for symbol metadata integrity across the persistence pipeline.

Tests:
1. All symbols extracted from analyzers have file_id in metadata
2. All symbols have line_start and line_end set (for known positions)
3. FactSymbol records properly resolve file_id to FactFile.id
4. SourceReader can retrieve source code using metadata
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.engine.analyzers.symbol import SymbolAnalyzer
from backend.intelligence.engine.analyzers.route import RouteAnalyzer
from backend.intelligence.engine.analyzers.database import DatabaseAnalyzer
from backend.intelligence.engine.analyzers.test import TestAnalyzer
from backend.intelligence.engine.analyzers.config import ConfigAnalyzer
from backend.intelligence.engine.analyzers.dependency import DependencyAnalyzer
from backend.intelligence.engine.parser.providers.base import ParsedFile
from backend.intelligence.store.fact_store import save_rim_to_fact_store
from backend.intelligence.retrieval.source_reader import RepositorySourceReader

from sqlalchemy import event
from sqlalchemy.engine import Engine
import tempfile

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def temp_repo():
    """Create a temporary repository with real source files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create Python source files
        (tmpdir / "src").mkdir()
        (tmpdir / "src" / "main.py").write_text("""
class UserModel:
    \"\"\"User database model.\"\"\"
    __tablename__ = "users"
    id = 1
    name = "John"

def login_user(username: str, password: str) -> bool:
    \"\"\"Authenticate a user.\"\"\"
    return True

@app.post("/api/login")
async def handle_login_request(user: UserModel):
    \"\"\"Handle login HTTP request.\"\"\"
    return {"success": login_user("", "")}

def test_login_success():
    \"\"\"Test successful login.\"\"\"
    assert login_user("user", "pass") == True

def test_login_failure():
    \"\"\"Test failed login.\"\"\"
    assert login_user("wrong", "creds") == False
""")

        (tmpdir / "package.json").write_text("""{
  "name": "my-app",
  "version": "1.0.0",
  "dependencies": {
    "express": "^4.18.0"
  }
}""")

        yield tmpdir

def test_metadata_preservation_end_to_end(db_session, temp_repo):
    """Test that metadata is preserved through the entire pipeline."""
    # Setup database records
    user = User(id=1, github_id="gh_1", username="testuser", email="test@example.com")
    db_session.add(user)
    db_session.flush()

    repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(id=1, repository_id=repo.id, status="Analyzing")
    db_session.add(analysis)
    db_session.commit()

    # Parse repository
    python_source = (temp_repo / "src" / "main.py").read_text()
    package_json = (temp_repo / "package.json").read_text()

    parsed_python = ParsedFile(
        file_path="src/main.py",
        language="Python",
        source=python_source,
        ast=__import__('ast').parse(python_source),
    )

    parsed_json = ParsedFile(
        file_path="package.json",
        language="JSON",
        source=package_json,
        ast=None,
    )

    # Run all analyzers
    repository = RepositoryModel(
        metadata=RepositoryMetadata(name="TestRepo", path=str(temp_repo), languages=["Python", "JSON"]),
        entities={},
        relationships={},
        capabilities={},
    )

    asts = {
        "src/main.py": parsed_python,
        "package.json": parsed_json,
    }

    for analyzer in [SymbolAnalyzer(), RouteAnalyzer(), DatabaseAnalyzer(), TestAnalyzer(), ConfigAnalyzer(), DependencyAnalyzer()]:
        analyzer.analyze(repository, asts)

    # === PHASE 1: Verify RIM has complete metadata ===
    print("\n=== PHASE 1: RIM Entity Metadata ===")
    metadata_issues = []
    symbol_count = 0
    for ent_id, ent in repository.entities.items():
        # Only check code symbols, not containers (file/directory) or external references (module/dependency)
        if ent.type.value in ("file", "directory", "module", "dependency"):
            continue  # Skip non-symbol entities and external references

        symbol_count += 1
        file_id = ent.metadata.get("file_id") if ent.metadata else None
        if not file_id:
            metadata_issues.append(f"{ent.type.value}: {ent.name} - missing file_id")

        print(f"{ent.type.value:<15} | {ent.name:<25} | file_id={str(file_id):<20} | line={ent.location.start_line}-{ent.location.end_line}")

    print(f"(Total: {symbol_count} symbols checked, {len(metadata_issues)} issues)")

    if metadata_issues:
        print(f"\nMetadata issues in RIM ({len(metadata_issues)}):")
        for issue in metadata_issues:
            print(f"  - {issue}")
        # FILE and DIRECTORY entities don't need file_id, so filter them out
        code_issues = [i for i in metadata_issues if not i.startswith(("FILE:", "DIRECTORY:"))]
        if code_issues:
            print(f"\nCode symbol metadata issues ({len(code_issues)}):")
            for issue in code_issues:
                print(f"  - {issue}")
            pytest.fail("RIM has code symbols without file_id metadata")
        else:
            print("\n(Only FILE/DIRECTORY missing file_id, which is OK)")

    # === PHASE 2: Save to database and verify ===
    save_rim_to_fact_store(db_session, analysis_id=1, model=repository)

    print("\n=== PHASE 2: FactSymbol Persistence ===")
    symbols = db_session.query(FactSymbol).filter_by(analysis_id=1).all()
    files = db_session.query(FactFile).filter_by(analysis_id=1).all()

    print(f"Saved {len(symbols)} symbols and {len(files)} files")

    persistence_issues = []
    for sym in symbols:
        if sym.symbol_type in ("file", "directory"):
            continue

        if sym.file_id is None:
            persistence_issues.append(f"{sym.symbol_type}: {sym.name} - NULL file_id")

        if sym.line_start is None:
            persistence_issues.append(f"{sym.symbol_type}: {sym.name} - NULL line_start")

        if sym.line_end is None:
            persistence_issues.append(f"{sym.symbol_type}: {sym.name} - NULL line_end")

        print(f"{sym.symbol_type:<15} | {sym.name:<25} | file_id={str(sym.file_id):<40} | lines={sym.line_start}-{sym.line_end}")

    if persistence_issues:
        print(f"\nPersistence issues ({len(persistence_issues)}):")
        for issue in persistence_issues:
            print(f"  - {issue}")
        pytest.fail("Database has symbols with NULL metadata")

    # === PHASE 3: Verify source code retrieval ===
    print("\n=== PHASE 3: Source Code Retrieval ===")
    reader = RepositorySourceReader(base_path=str(temp_repo), db=db_session, analysis_id=1)

    retrieval_issues = []
    for sym in symbols:
        if sym.symbol_type in ("file", "directory", "module", "dependency", "package"):
            continue

        if sym.file_id:
            # Get file path from FactFile
            file_record = db_session.query(FactFile).filter_by(id=sym.file_id).first()
            if file_record:
                file_path = file_record.path
                if sym.line_start and sym.line_end:
                    snippet = reader.read_source_snippet(file_path, sym.line_start, sym.line_end)
                    if snippet:
                        print(f"✓ {sym.symbol_type}: {sym.name} retrieved {len(snippet)} bytes from {file_path}:{sym.line_start}")
                    else:
                        retrieval_issues.append(f"{sym.symbol_type}: {sym.name} - failed to retrieve source")
                        print(f"✗ {sym.symbol_type}: {sym.name} - failed to retrieve source")
            else:
                retrieval_issues.append(f"{sym.symbol_type}: {sym.name} - file_id references non-existent FactFile")
        else:
            retrieval_issues.append(f"{sym.symbol_type}: {sym.name} - no file_id")

    if retrieval_issues:
        print(f"\nRetrieval issues ({len(retrieval_issues)}):")
        for issue in retrieval_issues:
            print(f"  - {issue}")
        pytest.fail("Failed to retrieve source code for some symbols")

    # === Final assertions ===
    print("\n=== Final Results ===")
    print(f"✓ All {len(symbols)} symbols have complete metadata")
    print(f"✓ All symbols successfully persisted to database")
    print(f"✓ All symbols retrievable via source reader")

def test_critical_symbol_types_have_metadata(db_session):
    """Test that critical symbol types (functions, classes, methods) have file_id."""
    user = User(id=1, github_id="gh_1", username="testuser", email="test@example.com")
    db_session.add(user)
    db_session.flush()

    repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
    db_session.add(repo)
    db_session.flush()

    analysis = Analysis(id=1, repository_id=repo.id, status="Analyzing")
    db_session.add(analysis)
    db_session.commit()

    # Test source with all critical types
    python_source = """
def top_level_function():
    pass

class MyClass:
    def method(self):
        pass

    @staticmethod
    def static_method():
        pass
"""

    parsed = ParsedFile(
        file_path="test_file.py",
        language="Python",
        source=python_source,
        ast=__import__('ast').parse(python_source),
    )

    repository = RepositoryModel(
        metadata=RepositoryMetadata(name="TestRepo", path="/test", languages=["Python"]),
        entities={},
        relationships={},
        capabilities={},
    )

    SymbolAnalyzer().analyze(repository, {"test_file.py": parsed})
    save_rim_to_fact_store(db_session, analysis_id=1, model=repository)

    # Check critical types
    critical_types = ["function", "class", "method"]
    for sym_type in critical_types:
        symbols = db_session.query(FactSymbol).filter(
            FactSymbol.analysis_id == 1,
            FactSymbol.symbol_type == sym_type,
            FactSymbol.file_id == None
        ).all()

        assert len(symbols) == 0, f"Found {len(symbols)} {sym_type}(s) with NULL file_id"

    print(f"✓ All critical symbol types have file_id")

if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
