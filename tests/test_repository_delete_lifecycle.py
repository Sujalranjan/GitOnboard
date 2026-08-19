"""
Regression Test Suite: Repository Deletion Lifecycle.

The bug this guards against: deleting a repository from the frontend only ever
removed the Repository database row (which cascades to Analysis/FactFile/etc. at
the DB level) but left its blob storage, worktree, and local cache state
untouched on disk. Re-importing a repository with the same name then reused that
never-cleaned worktree — including any stale/contaminated content from a
completely unrelated prior bug — because nothing ever validated it against the
newly resolved repository identity. See test_repository_fidelity.py for the
provenance-validation half of this fix; these tests cover the deletion half.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.config import settings
from backend.services.repo_cleanup import delete_repository_state


def _write_provenance(worktree_dir: Path, repository_id: int) -> None:
    marker_dir = worktree_dir / ".git"
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / "gitonboard-provenance.json").write_text(
        json.dumps({"repository_id": repository_id, "analysis_id": 1}), encoding="utf-8"
    )


def test_delete_repository_state_deletes_blob_prefix_scoped_to_repository_id():
    repo = MagicMock(id=901, url="https://github.com/org/repo-a")
    with patch("backend.storage.get_storage") as mock_storage_getter:
        mock_storage = MagicMock()
        mock_storage.delete_prefix.return_value = 3
        mock_storage_getter.return_value = mock_storage

        delete_repository_state(repo, "repo-a")

        mock_storage.delete_prefix.assert_called_once_with("repositories/901/")


def test_delete_repository_state_removes_exact_name_worktree():
    tmp_worktrees = Path(tempfile.mkdtemp(prefix="test_del_worktrees_"))
    try:
        target = tmp_worktrees / "repo-a"
        target.mkdir()
        (target / "README.md").write_text("hello", encoding="utf-8")

        repo = MagicMock(id=902, url="https://github.com/org/repo-a")
        with patch.object(settings, "worktrees_dir", str(tmp_worktrees)), \
             patch("backend.storage.get_storage") as mock_storage_getter:
            mock_storage_getter.return_value = MagicMock(delete_prefix=MagicMock(return_value=0))
            delete_repository_state(repo, "repo-a")

        assert not target.exists()
    finally:
        shutil.rmtree(tmp_worktrees, ignore_errors=True)


def test_delete_repository_state_removes_provenance_marked_worktree_by_id_not_name():
    """
    A worktree named nothing like the repo (e.g. the {repo}_{run_id} convention
    SandboxManager uses) must still be found and deleted — via its provenance
    marker's repository_id, never via fuzzy substring/name matching.
    """
    tmp_worktrees = Path(tempfile.mkdtemp(prefix="test_del_worktrees_"))
    try:
        target = tmp_worktrees / "totally-unrelated-directory-name"
        target.mkdir()
        (target / "app.py").write_text("code", encoding="utf-8")
        _write_provenance(target, repository_id=903)

        repo = MagicMock(id=903, url="https://github.com/org/repo-b")
        with patch.object(settings, "worktrees_dir", str(tmp_worktrees)), \
             patch("backend.storage.get_storage") as mock_storage_getter:
            mock_storage_getter.return_value = MagicMock(delete_prefix=MagicMock(return_value=0))
            delete_repository_state(repo, "repo-b")

        assert not target.exists()
    finally:
        shutil.rmtree(tmp_worktrees, ignore_errors=True)


def test_delete_repository_state_does_not_touch_other_repositories_worktrees():
    """Isolation: deleting repository A must never remove or modify repository B's worktree."""
    tmp_worktrees = Path(tempfile.mkdtemp(prefix="test_del_isolation_"))
    try:
        repo_a_dir = tmp_worktrees / "repo-a"
        repo_a_dir.mkdir()
        (repo_a_dir / "a.txt").write_text("a", encoding="utf-8")

        repo_b_dir = tmp_worktrees / "repo-b_run_xyz"
        repo_b_dir.mkdir()
        (repo_b_dir / "b.txt").write_text("b", encoding="utf-8")
        _write_provenance(repo_b_dir, repository_id=905)

        repo_a = MagicMock(id=904, url="https://github.com/org/repo-a")
        with patch.object(settings, "worktrees_dir", str(tmp_worktrees)), \
             patch("backend.storage.get_storage") as mock_storage_getter:
            mock_storage_getter.return_value = MagicMock(delete_prefix=MagicMock(return_value=0))
            delete_repository_state(repo_a, "repo-a")

        assert not repo_a_dir.exists()
        assert repo_b_dir.exists(), "Repository B's worktree must survive Repository A's deletion"
        assert (repo_b_dir / "b.txt").read_text(encoding="utf-8") == "b"
    finally:
        shutil.rmtree(tmp_worktrees, ignore_errors=True)


def test_delete_repository_state_removes_legacy_local_repo_cache():
    tmp_storage = Path(tempfile.mkdtemp(prefix="test_del_storage_"))
    try:
        repos_root = tmp_storage / "repos"
        repos_root.mkdir()
        cache_dir = repos_root / "repo-a"
        cache_dir.mkdir()
        (cache_dir / "file.txt").write_text("cached", encoding="utf-8")

        repo = MagicMock(id=906, url="https://github.com/org/repo-a")
        with patch.object(settings, "storage_path", str(tmp_storage)), \
             patch("backend.storage.get_storage") as mock_storage_getter:
            mock_storage_getter.return_value = MagicMock(delete_prefix=MagicMock(return_value=0))
            delete_repository_state(repo, "repo-a")

        assert not cache_dir.exists()
    finally:
        shutil.rmtree(tmp_storage, ignore_errors=True)


def test_delete_repository_state_is_best_effort_on_storage_failure():
    """A blob-storage outage must not prevent the caller (delete_repo) from
    proceeding to delete the database row — cleanup failures are logged, not raised."""
    repo = MagicMock(id=907, url="https://github.com/org/repo-a")
    with patch("backend.storage.get_storage", side_effect=RuntimeError("Azurite unreachable")):
        delete_repository_state(repo, "repo-a")  # must not raise
