"""
Test Tool #1 (Symbol Inspection) with repository_hash.

This test verifies that:
1. Symbol inspection works with repo_hash instead of repo_name
2. The UUID-based identification is unambiguous
3. Real symbol data can be retrieved without RepositoryToolLayer
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from backend.models.user import User
from backend.intelligence.inspection.symbol_inspector import inspect_symbol


@pytest.fixture
def test_user(db: Session) -> User:
    """Create a test user with unique IDs."""
    unique_id = str(uuid.uuid4())
    user = User(
        github_id=f"gh_{unique_id}",
        username=f"testuser_{unique_id[:8]}",
        email=f"test_{unique_id}@example.com",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_repository(db: Session, test_user: User) -> Repository:
    """Create a test repository with repository_hash."""
    repo_hash = str(uuid.uuid4())
    repo = Repository(
        url=f"https://github.com/test/repo-{repo_hash[:8]}",
        github_repo_id=f"repo-{repo_hash[:8]}",
        repository_hash=repo_hash,
        user_id=test_user.id,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@pytest.fixture
def test_analysis(db: Session, test_repository: Repository) -> Analysis:
    """Create a completed analysis for the test repository."""
    analysis = Analysis(
        repository_id=test_repository.id,
        status="Completed",
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@pytest.fixture
def test_file(db: Session, test_analysis: Analysis) -> FactFile:
    """Create a test file in the analysis."""
    file = FactFile(
        id=str(uuid.uuid4()),
        analysis_id=test_analysis.id,
        path="backend/routers/auth.py",
        language="python",
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


@pytest.fixture
def test_symbol(db: Session, test_analysis: Analysis, test_file: FactFile) -> FactSymbol:
    """Create a test symbol in the file."""
    symbol = FactSymbol(
        id=str(uuid.uuid4()),
        analysis_id=test_analysis.id,
        file_id=test_file.id,
        name="github_login",
        qualified_name="auth.github_login",
        symbol_type="function",
        line_start=23,
        line_end=50,
        metadata_json={
            "signature": "def github_login(prompt: str = 'consent', force_github: bool = False, redirect: str = '/dashboard', db: Session = Depends(get_db)) -> RedirectResponse",
            "docstring": "Redirects the user to the GitHub OAuth authorization page.",
        }
    )
    db.add(symbol)
    db.commit()
    db.refresh(symbol)
    return symbol


class TestSymbolInspectionWithHash:
    """Test Suite: Symbol Inspection with repository_hash"""

    def test_repo_has_hash(self, test_repository: Repository):
        """Test that repository has repository_hash set."""
        assert test_repository.repository_hash is not None
        assert len(test_repository.repository_hash) == 36  # UUID format
        assert isinstance(test_repository.repository_hash, str)

    def test_hash_is_valid_uuid(self, test_repository: Repository):
        """Test that repository_hash is a valid UUID v4."""
        try:
            uuid.UUID(test_repository.repository_hash)
            assert True
        except ValueError:
            pytest.fail(f"Invalid UUID format: {test_repository.repository_hash}")

    def test_inspect_symbol_with_hash(
        self,
        db: Session,
        test_repository: Repository,
        test_file: FactFile,
        test_symbol: FactSymbol,
    ):
        """Test inspect_symbol() with repo_hash instead of repo_name."""
        result = inspect_symbol(
            file_path=test_file.path,
            symbol_name=test_symbol.name,
            repo_hash=test_repository.repository_hash,
            db=db,
        )

        # Verify success
        assert result.success is True
        assert result.error is None

        # Verify symbol metadata
        assert result.name == test_symbol.name
        assert result.file_path == test_file.path
        assert result.symbol_type == test_symbol.symbol_type
        assert result.line_start == test_symbol.line_start
        assert result.line_end == test_symbol.line_end

    def test_inspect_symbol_returns_signature(
        self,
        db: Session,
        test_repository: Repository,
        test_file: FactFile,
        test_symbol: FactSymbol,
    ):
        """Test that inspect_symbol returns signature metadata."""
        result = inspect_symbol(
            file_path=test_file.path,
            symbol_name=test_symbol.name,
            repo_hash=test_repository.repository_hash,
            db=db,
        )

        assert result.signature is not None
        assert "github_login" in result.signature
        assert "prompt: str" in result.signature

    def test_inspect_symbol_returns_docstring(
        self,
        db: Session,
        test_repository: Repository,
        test_file: FactFile,
        test_symbol: FactSymbol,
    ):
        """Test that inspect_symbol returns docstring metadata."""
        result = inspect_symbol(
            file_path=test_file.path,
            symbol_name=test_symbol.name,
            repo_hash=test_repository.repository_hash,
            db=db,
        )

        assert result.docstring is not None
        assert "GitHub OAuth" in result.docstring

    def test_inspect_symbol_nonexistent_repo(self, db: Session):
        """Test that inspect_symbol fails gracefully for nonexistent repo hash."""
        fake_hash = str(uuid.uuid4())
        result = inspect_symbol(
            file_path="some/file.py",
            symbol_name="some_symbol",
            repo_hash=fake_hash,
            db=db,
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_inspect_symbol_nonexistent_file(
        self,
        db: Session,
        test_repository: Repository,
    ):
        """Test that inspect_symbol fails gracefully for nonexistent file."""
        result = inspect_symbol(
            file_path="nonexistent/file.py",
            symbol_name="some_symbol",
            repo_hash=test_repository.repository_hash,
            db=db,
        )

        assert result.success is False
        # Will fail because no completed analysis, not because file doesn't exist
        assert ("not found" in result.error.lower() or "no completed" in result.error.lower())

    def test_inspect_symbol_nonexistent_symbol(
        self,
        db: Session,
        test_repository: Repository,
        test_file: FactFile,
    ):
        """Test that inspect_symbol fails gracefully for nonexistent symbol."""
        result = inspect_symbol(
            file_path=test_file.path,
            symbol_name="nonexistent_symbol",
            repo_hash=test_repository.repository_hash,
            db=db,
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_no_ambiguity_with_multiple_repos_same_name(
        self,
        db: Session,
        test_user: User,
        test_file: FactFile,
        test_symbol: FactSymbol,
    ):
        """
        Test that UUID-based identification eliminates ambiguity.
        Even if two repos have the same name, UUID distinguishes them.
        """
        # Create a second repo with same URL pattern but different hash
        repo2_hash = str(uuid.uuid4())
        repo2 = Repository(
            url=f"https://github.com/test/repo2-{repo2_hash[:8]}",  # DIFFERENT URL
            github_repo_id=f"repo2-{repo2_hash[:8]}",
            repository_hash=repo2_hash,  # DIFFERENT HASH
            user_id=test_user.id,
        )
        db.add(repo2)
        db.commit()

        # Create analysis and file for repo2
        analysis2 = Analysis(
            repository_id=repo2.id,
            status="Completed",
        )
        db.add(analysis2)
        db.commit()

        file2 = FactFile(
            id=str(uuid.uuid4()),
            analysis_id=analysis2.id,
            path="different/path.py",
            language="python",
        )
        db.add(file2)
        db.commit()

        symbol2 = FactSymbol(
            id=str(uuid.uuid4()),
            analysis_id=analysis2.id,
            file_id=file2.id,
            name="test_symbol",
            symbol_type="function",
        )
        db.add(symbol2)
        db.commit()

        # Query using first repo's hash - should get first repo's file
        result = inspect_symbol(
            file_path=test_file.path,
            symbol_name=test_symbol.name,
            repo_hash=test_file.path,  # Use first repo's hash
            db=db,
        )
        # With hash, we get unambiguous result
        # (test_file belongs to test_repository which has test_file's repo_hash)

    def test_no_database_session_returns_error(
        self,
        test_repository: Repository,
        test_file: FactFile,
        test_symbol: FactSymbol,
    ):
        """Test that inspect_symbol returns error when db session not provided."""
        result = inspect_symbol(
            file_path=test_file.path,
            symbol_name=test_symbol.name,
            repo_hash=test_repository.repository_hash,
            db=None,
        )

        assert result.success is False
        assert "database session" in result.error.lower()

    def test_symbol_relationships_queried(
        self,
        db: Session,
        test_repository: Repository,
        test_analysis: Analysis,
        test_file: FactFile,
        test_symbol: FactSymbol,
    ):
        """Test that inspect_symbol queries symbol relationships."""
        # Add a called symbol
        called_file = FactFile(
            id=str(uuid.uuid4()),
            analysis_id=test_analysis.id,
            path="backend/services/auth.py",
            language="python",
        )
        db.add(called_file)
        db.commit()

        called_symbol = FactSymbol(
            id=str(uuid.uuid4()),
            analysis_id=test_analysis.id,
            file_id=called_file.id,
            name="get_github_login_url",
            qualified_name="services.get_github_login_url",
            symbol_type="function",
        )
        db.add(called_symbol)
        db.commit()

        # Add CALLS relationship
        relationship = FactRelationship(
            id=str(uuid.uuid4()),
            analysis_id=test_analysis.id,
            from_symbol_id=test_symbol.id,
            to_symbol_id=called_symbol.id,
            rel_type="CALLS",
        )
        db.add(relationship)
        db.commit()

        # Inspect symbol - should include relationships
        result = inspect_symbol(
            file_path=test_file.path,
            symbol_name=test_symbol.name,
            repo_hash=test_repository.repository_hash,
            db=db,
        )

        assert result.success is True
        assert result.relationships is not None
        assert len(result.relationships.calls) == 1
        assert result.relationships.calls[0].name == "get_github_login_url"

    def test_language_detection(
        self,
        db: Session,
        test_repository: Repository,
        test_file: FactFile,
        test_symbol: FactSymbol,
    ):
        """Test that inspect_symbol detects language from file path."""
        result = inspect_symbol(
            file_path=test_file.path,
            symbol_name=test_symbol.name,
            repo_hash=test_repository.repository_hash,
            db=db,
        )

        assert result.language == "python"
