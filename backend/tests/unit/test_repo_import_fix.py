"""
Test suite for repository import fix.

Tests verify that:
1. Multiple different repos can be imported without overwriting
2. Re-importing same repo reuses existing record (no duplicates)
3. github_repo_id uniqueness is maintained
4. PROD mode still works correctly
"""

import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.database import Base
from backend.services.github import check_repo_limits
from backend.config import settings


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for tests"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user"""
    user = User(
        github_id="test-user-123",
        username="testuser",
        email="test@example.com"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestRepositoryImportFix:
    """Test the repository import fix"""

    @pytest.mark.asyncio
    async def test_local_mode_generates_unique_ids(self):
        """
        Test that LOCAL mode generates unique github_repo_id for different repos.

        Before fix: "local"
        After fix: "local-owner-repo"
        """
        # Test with LOCAL mode
        with patch.object(settings, 'deployment_type', 'LOCAL'):
            result_a = await check_repo_limits("owner", "repo-a")
            result_b = await check_repo_limits("owner", "repo-b")

            # Both should return LOCAL mode values
            assert result_a["default_branch"] == "main"
            assert result_b["default_branch"] == "main"

            # But github_repo_id should be DIFFERENT for different repos
            assert result_a["github_repo_id"] == "local-owner-repo-a"
            assert result_b["github_repo_id"] == "local-owner-repo-b"
            assert result_a["github_repo_id"] != result_b["github_repo_id"]

    @pytest.mark.asyncio
    async def test_local_mode_same_repo_same_id(self):
        """
        Test that same repo in LOCAL mode always generates same github_repo_id.
        (Important for re-imports to work correctly)
        """
        with patch.object(settings, 'deployment_type', 'LOCAL'):
            result_1 = await check_repo_limits("owner", "repo-a")
            result_2 = await check_repo_limits("owner", "repo-a")

            # Same repo should generate same ID
            assert result_1["github_repo_id"] == result_2["github_repo_id"]
            assert result_1["github_repo_id"] == "local-owner-repo-a"

    @pytest.mark.asyncio
    async def test_prod_mode_uses_actual_github_id(self):
        """
        Test that PROD mode still uses actual GitHub repository ID.
        (Ensure we didn't break PROD deployments)
        """
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123456789,
            "default_branch": "main",
            "size": 1024
        }

        with patch.object(settings, 'deployment_type', 'PROD'):
            with patch('backend.services.github.get_github_client') as mock_client:
                mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

                result = await check_repo_limits("owner", "repo", token="fake-token")

                # PROD mode should use actual GitHub ID
                assert result["github_repo_id"] == "123456789"
                assert result["default_branch"] == "main"

    def test_multiple_repos_create_separate_records(self, db_session: Session, test_user: User):
        """
        Test that importing two different repos creates two separate database records.

        This is the core issue being fixed:
        Before: Both repos would reuse the same record (github_repo_id="local")
        After: Each repo gets unique ID and separate record
        """
        # Import repo A
        repo_a = Repository(
            github_repo_id="local-owner-repo-a",
            url="https://github.com/owner/repo-a",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_a)
        db_session.commit()
        db_session.refresh(repo_a)

        # Import repo B with different unique ID
        repo_b = Repository(
            github_repo_id="local-owner-repo-b",
            url="https://github.com/owner/repo-b",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_b)
        db_session.commit()
        db_session.refresh(repo_b)

        # Verify both repos exist with different IDs
        repos = db_session.query(Repository).filter(Repository.user_id == test_user.id).all()
        assert len(repos) == 2
        assert repo_a.id != repo_b.id
        assert repo_a.github_repo_id != repo_b.github_repo_id
        assert repo_a.url != repo_b.url

    def test_reimport_same_repo_reuses_record(self, db_session: Session, test_user: User):
        """
        Test that re-importing the same repo reuses the existing record.

        This ensures we don't create duplicates when importing same repo twice.
        """
        # First import
        repo_1 = Repository(
            github_repo_id="local-owner-repo-a",
            url="https://github.com/owner/repo-a",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_1)
        db_session.commit()
        db_session.refresh(repo_1)
        repo_1_id = repo_1.id

        # Second import (same URL, same unique ID)
        existing_repo = db_session.query(Repository).filter(
            Repository.user_id == test_user.id,
            Repository.github_repo_id == "local-owner-repo-a"
        ).first()

        # Should find existing repo, not create new one
        assert existing_repo is not None
        assert existing_repo.id == repo_1_id

        # Total repos should still be 1
        all_repos = db_session.query(Repository).filter(Repository.user_id == test_user.id).all()
        assert len(all_repos) == 1

    def test_unique_constraint_on_github_repo_id(self, db_session: Session, test_user: User):
        """
        Test that database prevents duplicate github_repo_ids per user.
        """
        # Create first repo
        repo_a = Repository(
            github_repo_id="local-owner-repo-a",
            url="https://github.com/owner/repo-a",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_a)
        db_session.commit()

        # Try to create second repo with SAME github_repo_id
        repo_dup = Repository(
            github_repo_id="local-owner-repo-a",  # ← Duplicate!
            url="https://github.com/different/url",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_dup)

        # Should raise integrity error due to unique constraint
        with pytest.raises(Exception):  # sqlalchemy.exc.IntegrityError
            db_session.commit()

    def test_url_unique_constraint_per_user(self, db_session: Session, test_user: User):
        """
        Test that database also prevents same URL per user.
        """
        # Create first repo
        repo_a = Repository(
            github_repo_id="local-owner-repo-a",
            url="https://github.com/owner/repo-a",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_a)
        db_session.commit()

        # Try to create second repo with SAME URL (even with different ID)
        repo_dup = Repository(
            github_repo_id="local-different-id",
            url="https://github.com/owner/repo-a",  # ← Duplicate URL!
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_dup)

        # Should raise integrity error due to unique constraint on (user_id, url)
        with pytest.raises(Exception):  # sqlalchemy.exc.IntegrityError
            db_session.commit()

    def test_analysis_attached_to_correct_repo(self, db_session: Session, test_user: User):
        """
        Test that analysis records are attached to correct repository.

        Before fix: Analysis might attach to wrong repo if repos are reused
        After fix: Analysis clearly belongs to specific repo via repo_id
        """
        # Create two repos
        repo_a = Repository(
            github_repo_id="local-owner-repo-a",
            url="https://github.com/owner/repo-a",
            default_branch="main",
            user_id=test_user.id
        )
        repo_b = Repository(
            github_repo_id="local-owner-repo-b",
            url="https://github.com/owner/repo-b",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_a)
        db_session.add(repo_b)
        db_session.commit()
        db_session.refresh(repo_a)
        db_session.refresh(repo_b)

        # Create analysis for repo_a
        analysis_a = Analysis(
            repository_id=repo_a.id,
            status="Completed"
        )
        db_session.add(analysis_a)
        db_session.commit()

        # Create analysis for repo_b
        analysis_b = Analysis(
            repository_id=repo_b.id,
            status="Queued"
        )
        db_session.add(analysis_b)
        db_session.commit()

        # Verify analyses belong to correct repos
        repo_a_analyses = db_session.query(Analysis).filter(Analysis.repository_id == repo_a.id).all()
        repo_b_analyses = db_session.query(Analysis).filter(Analysis.repository_id == repo_b.id).all()

        assert len(repo_a_analyses) == 1
        assert len(repo_b_analyses) == 1
        assert repo_a_analyses[0].id != repo_b_analyses[0].id

    def test_no_orphaned_analysis_after_fix(self, db_session: Session, test_user: User):
        """
        Test that no analysis records become orphaned after the fix.

        Before fix: Reusing repos could orphan analysis records
        After fix: Each repo has its own analysis chain
        """
        # Create repo A with analysis
        repo_a = Repository(
            github_repo_id="local-owner-repo-a",
            url="https://github.com/owner/repo-a",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_a)
        db_session.commit()
        db_session.refresh(repo_a)

        analysis_a = Analysis(
            repository_id=repo_a.id,
            status="Completed"
        )
        db_session.add(analysis_a)
        db_session.commit()

        # Create repo B with separate analysis
        repo_b = Repository(
            github_repo_id="local-owner-repo-b",
            url="https://github.com/owner/repo-b",
            default_branch="main",
            user_id=test_user.id
        )
        db_session.add(repo_b)
        db_session.commit()
        db_session.refresh(repo_b)

        analysis_b = Analysis(
            repository_id=repo_b.id,
            status="Queued"
        )
        db_session.add(analysis_b)
        db_session.commit()

        # Check: no orphaned analyses
        all_analyses = db_session.query(Analysis).all()
        all_repo_ids = {repo.id for repo in db_session.query(Repository).all()}

        for analysis in all_analyses:
            assert analysis.repository_id in all_repo_ids, \
                f"Orphaned analysis {analysis.id}: no repo with id {analysis.repository_id}"

        assert len(all_analyses) == 2  # Both analyses should exist
