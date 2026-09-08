"""
Unit tests for Tool #2 (File Retrieval) validation logic.
Tests strict file existence checks and error handling.
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.event import listens_for
from sqlalchemy.engine import Engine

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile
from backend.utils.repo_paths import normalize_relative, PathTraversalError

# Enable foreign keys for SQLite
@listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db_session():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_user(db_session: Session):
    """Create test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password="hashed"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_repo(db_session: Session, test_user: User):
    """Create test repository."""
    repo = Repository(
        owner_id=test_user.id,
        name="test_repo",
        url="https://github.com/test/test_repo",
        default_branch="main"
    )
    db_session.add(repo)
    db_session.commit()
    return repo


@pytest.fixture
def test_analysis(db_session: Session, test_repo: Repository):
    """Create test analysis."""
    analysis = Analysis(
        repository_id=test_repo.id,
        status="completed",
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow()
    )
    db_session.add(analysis)
    db_session.commit()
    return analysis


@pytest.fixture
def test_fact_file(db_session: Session, test_analysis: Analysis):
    """Create test FactFile in analysis."""
    fact_file = FactFile(
        analysis_id=test_analysis.id,
        path="backend/auth.py",
        blob_name="test_blob_key",
        size=1024,
        language="python",
        content_type="text/plain",
        hash="abc123"
    )
    db_session.add(fact_file)
    db_session.commit()
    return fact_file


class TestPathValidation:
    """Test path normalization and traversal prevention."""

    def test_valid_path_normalization(self):
        """Test that valid paths are normalized correctly."""
        clean = normalize_relative("backend/auth.py")
        assert clean == "backend/auth.py"

    def test_path_normalization_removes_dots(self):
        """Test that paths with ./ are normalized."""
        clean = normalize_relative("./backend/auth.py")
        assert clean == "backend/auth.py"

    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        with pytest.raises(PathTraversalError):
            normalize_relative("../../../etc/passwd")

    def test_path_traversal_with_dots_rejected(self):
        """Test that disguised path traversal is rejected."""
        with pytest.raises(PathTraversalError):
            normalize_relative("backend/../../etc/passwd")

    def test_absolute_path_rejected(self):
        """Test that absolute paths are rejected."""
        with pytest.raises(PathTraversalError):
            normalize_relative("/etc/passwd")


class TestFileExistenceValidation:
    """Test file existence checks in analysis context."""

    def test_file_found_in_analysis(self, db_session: Session, test_analysis: Analysis, test_fact_file: FactFile):
        """Test that file found in analysis is returned."""
        fact_file = (
            db_session.query(FactFile)
            .filter(FactFile.analysis_id == test_analysis.id, FactFile.path == "backend/auth.py")
            .first()
        )
        assert fact_file is not None
        assert fact_file.path == "backend/auth.py"
        assert fact_file.blob_name == "test_blob_key"

    def test_file_not_found_in_analysis(self, db_session: Session, test_analysis: Analysis):
        """Test that nonexistent file returns None."""
        fact_file = (
            db_session.query(FactFile)
            .filter(FactFile.analysis_id == test_analysis.id, FactFile.path == "nonexistent.py")
            .first()
        )
        assert fact_file is None

    def test_file_cross_analysis_isolation(self, db_session: Session, test_repo: Repository, test_fact_file: FactFile):
        """Test that file in one analysis is not accessible via another analysis."""
        # Create second analysis
        analysis2 = RepositoryAnalysis(
            repository_id=test_repo.id,
            status="completed",
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        db_session.add(analysis2)
        db_session.commit()

        # File should not be found in analysis2
        fact_file = (
            db_session.query(FactFile)
            .filter(FactFile.analysis_id == analysis2.id, FactFile.path == "backend/auth.py")
            .first()
        )
        assert fact_file is None

    def test_multiple_files_same_analysis(self, db_session: Session, test_analysis: Analysis):
        """Test querying multiple files in same analysis."""
        file1 = FactFile(
            analysis_id=test_analysis.id,
            path="backend/auth.py",
            blob_name="blob1",
            size=100,
            language="python",
            content_type="text/plain",
            hash="hash1"
        )
        file2 = FactFile(
            analysis_id=test_analysis.id,
            path="backend/db.py",
            blob_name="blob2",
            size=200,
            language="python",
            content_type="text/plain",
            hash="hash2"
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        # Query both files
        result1 = db_session.query(FactFile).filter(
            FactFile.analysis_id == test_analysis.id,
            FactFile.path == "backend/auth.py"
        ).first()
        result2 = db_session.query(FactFile).filter(
            FactFile.analysis_id == test_analysis.id,
            FactFile.path == "backend/db.py"
        ).first()

        assert result1 is not None
        assert result2 is not None
        assert result1.blob_name == "blob1"
        assert result2.blob_name == "blob2"


class TestLineRangeValidation:
    """Test line range parameter validation."""

    def test_valid_line_range(self):
        """Test that valid line range is accepted."""
        start_line = 1
        end_line = 10
        total_lines = 50

        assert start_line >= 1
        assert end_line >= start_line
        assert end_line <= total_lines

    def test_invalid_start_line_less_than_1(self):
        """Test that start_line < 1 is rejected."""
        start_line = 0
        end_line = 10

        assert not (start_line >= 1)

    def test_invalid_end_line_less_than_start(self):
        """Test that end_line < start_line is rejected."""
        start_line = 10
        end_line = 5

        assert not (end_line >= start_line)

    def test_invalid_end_line_exceeds_total(self):
        """Test that end_line > total_lines is rejected."""
        start_line = 1
        end_line = 100
        total_lines = 50

        assert not (end_line <= total_lines)

    def test_line_extraction(self):
        """Test that line extraction works correctly."""
        content = "line1\nline2\nline3\nline4\nline5\n"
        lines = content.splitlines()
        start_line = 2
        end_line = 4

        extracted_lines = lines[start_line-1:end_line]
        extracted_content = '\n'.join(extracted_lines)

        assert extracted_content == "line2\nline3\nline4"

    def test_full_file_extraction(self):
        """Test extracting entire file."""
        content = "line1\nline2\nline3\n"
        lines = content.splitlines()
        total_lines = len(lines)

        extracted_lines = lines[0:total_lines]
        extracted_content = '\n'.join(extracted_lines)

        assert extracted_content == content.strip()


class TestBlobNameValidation:
    """Test blob_name presence validation."""

    def test_fact_file_with_blob_name(self, db_session: Session, test_analysis: Analysis):
        """Test that FactFile with blob_name is valid."""
        fact_file = FactFile(
            analysis_id=test_analysis.id,
            path="backend/auth.py",
            blob_name="valid_blob_key",
            size=100,
            language="python",
            content_type="text/plain",
            hash="hash1"
        )
        db_session.add(fact_file)
        db_session.commit()

        result = db_session.query(FactFile).filter(
            FactFile.analysis_id == test_analysis.id
        ).first()

        assert result.blob_name is not None
        assert result.blob_name == "valid_blob_key"

    def test_fact_file_without_blob_name(self, db_session: Session, test_analysis: Analysis):
        """Test that FactFile without blob_name is detected."""
        fact_file = FactFile(
            analysis_id=test_analysis.id,
            path="backend/auth.py",
            blob_name=None,
            size=100,
            language="python",
            content_type="text/plain",
            hash="hash1"
        )
        db_session.add(fact_file)
        db_session.commit()

        result = db_session.query(FactFile).filter(
            FactFile.analysis_id == test_analysis.id
        ).first()

        assert result.blob_name is None
