"""
Repository-scoped filesystem and object-storage cleanup for repository deletion.

Deleting a Repository row cascades to its Analysis/AnalysisArtifact/AnalysisJob/FactFile
rows at the database level (see backend/models/repository.py and
backend/models/fact_store.py — cascade="all, delete-orphan" plus ON DELETE CASCADE), but
the database has never been the only place repository state lives:

- Azure Blob Storage / Azurite holds the actual file contents, keyed by
  `repositories/{repository_id}/...` (backend/storage/naming.py).
- data/worktrees/ holds sandbox worktrees populated from that Fact Store snapshot.
- data/repos/ is a legacy/vestigial local-cache location (no longer written by the
  ingestion pipeline — see backend/services/worker.py — but cleaned up here for hygiene
  in case it exists from an older build).

None of these are deleted by `db.delete(repo)` alone. Left behind, they cause exactly the
bug this module fixes: re-importing a repository with the same name reuses a stale worktree
that was never wiped, so "delete then reload" does not produce a clean snapshot.

Cleanup here is scoped strictly to the repository being deleted:
- Blob storage is scoped by `repository_id`, which is a real, unique, database-assigned
  identity — no other repository's blobs share that prefix.
- Worktree directories are identified either by an exact name match (the same repo_name
  string every other part of this codebase already uses as the run_id/worktree key), or by
  their WorktreeProvisioner provenance marker recording this exact `repository_id` — never
  by fuzzy substring/prefix matching against other repositories' names.

All steps are best-effort and independently logged: a filesystem or storage error here must
never block the database deletion the user actually asked for, but must also never be
reported as silent success — failures are logged at warning/error level for operators.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from backend.config import settings
from backend.models.repository import Repository

logger = logging.getLogger(__name__)


def _delete_blob_storage(repository_id: int) -> None:
    try:
        from backend.storage import get_storage
        storage = get_storage()
        deleted = storage.delete_prefix(f"repositories/{repository_id}/")
        logger.info(f"Deleted {deleted} blob(s) under repositories/{repository_id}/")
    except Exception as e:
        logger.warning(f"Blob storage cleanup failed for repository {repository_id}: {e}")


def _worktree_belongs_to_repo(worktree_dir: Path, repository_id: int) -> bool:
    marker = worktree_dir / ".git" / "gitonboard-provenance.json"
    try:
        if marker.exists():
            data = json.loads(marker.read_text(encoding="utf-8"))
            return data.get("repository_id") == repository_id
    except Exception as e:
        logger.debug(f"Could not read provenance marker at {marker}: {e}")
    return False


def _delete_worktrees(repository_id: int, repo_name: str) -> None:
    base_dir = Path(settings.worktrees_dir)
    if not base_dir.exists():
        return

    targets = set()

    # Exact-name worktree: the canonical directory /scan, the Terminal, and the file
    # editor all resolve to for this repo_name (see structure.py, sandbox_manager.py).
    for candidate_name in (repo_name, repo_name.lower()):
        candidate = base_dir / candidate_name
        if candidate.exists() and candidate.is_dir():
            targets.add(candidate.resolve())

    # Any other worktree directory whose provenance marker proves it was provisioned
    # for this exact repository_id (covers {repo}_{run_id}-style directories created
    # by SandboxManager without resorting to fuzzy name matching).
    try:
        for item in base_dir.iterdir():
            if item.is_dir() and _worktree_belongs_to_repo(item, repository_id):
                targets.add(item.resolve())
    except Exception as e:
        logger.warning(f"Could not scan {base_dir} for repository {repository_id} worktrees: {e}")

    for target in targets:
        try:
            shutil.rmtree(target, ignore_errors=False)
            logger.info(f"Deleted worktree {target} for repository {repository_id} ({repo_name})")
        except Exception as e:
            logger.warning(f"Failed to delete worktree {target} for repository {repository_id}: {e}")


def _delete_local_repo_cache(repo_name: str) -> None:
    """Best-effort cleanup of the legacy data/repos/{name} cache location, if present."""
    repos_root = Path(settings.storage_path) / "repos"
    if not repos_root.exists():
        return
    for candidate_name in (repo_name, repo_name.lower()):
        candidate = repos_root / candidate_name
        if candidate.exists() and candidate.is_dir():
            try:
                shutil.rmtree(candidate, ignore_errors=False)
                logger.info(f"Deleted local repo cache {candidate}")
            except Exception as e:
                logger.warning(f"Failed to delete local repo cache {candidate}: {e}")


def delete_repository_state(repo: Repository, repo_name: str) -> None:
    """
    Best-effort deletion of all filesystem and object-storage state scoped to `repo`,
    ahead of the caller deleting the Repository row itself (which cascades the
    database-side Analysis/FactFile/etc. rows). Never raises — a cleanup failure here
    must not prevent the user's delete request from completing, but is always logged.
    """
    _delete_blob_storage(repo.id)
    _delete_worktrees(repo.id, repo_name)
    _delete_local_repo_cache(repo_name)
