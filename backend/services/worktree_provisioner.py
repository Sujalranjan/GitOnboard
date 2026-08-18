"""
WorktreeProvisioner: Provisions and populates isolated Git worktree sandboxes with real repository contents.

Ensures:
- Sandbox worktrees are populated with actual repository source files (never left as empty .git skeletons).
- Consistency between the File Explorer, Code Editor, Azure Blob Storage, and the Sandbox Terminal.
- Valid initial Git baseline commit so `git status`, `git diff`, and `git rev-parse` execute cleanly.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Set
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile
from backend.storage import get_storage

logger = logging.getLogger(__name__)

EXCLUDED_COPY_DIRS: Set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    ".next",
    "dist",
    "build",
    "data",
    ".pytest_cache",
    ".turbo",
}


class WorktreeProvisioner:
    """
    Provisions, populates, and initializes real repository files inside worktree sandboxes.
    """

    def __init__(self, base_worktree_dir: Optional[Path] = None):
        self.base_dir = (base_worktree_dir or Path(settings.worktrees_dir)).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def is_worktree_populated(self, worktree_path: Path) -> bool:
        """
        Returns True if the worktree contains actual repository files (not just empty .git or logs).
        """
        if not worktree_path.exists() or not worktree_path.is_dir():
            return False

        entries = [
            e for e in worktree_path.iterdir()
            if e.name != ".git" and not e.name.startswith("gitonboard_session_") and not e.name.startswith(".")
        ]
        return len(entries) > 0

    def _copy_directory_contents(self, source_dir: Path, target_dir: Path) -> int:
        """
        Copies non-excluded files and directories from source_dir to target_dir.
        Returns the number of files copied.
        """
        target_dir.mkdir(parents=True, exist_ok=True)
        files_copied = 0

        for root, dirs, files in os.walk(source_dir):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDED_COPY_DIRS]

            rel_root = Path(root).relative_to(source_dir)
            dest_root = target_dir / rel_root
            dest_root.mkdir(parents=True, exist_ok=True)

            for f in files:
                if f.startswith(".git") or f.endswith(".pyc") or f.endswith(".tmp"):
                    continue
                src_file = Path(root) / f
                dest_file = dest_root / f
                try:
                    shutil.copy2(src_file, dest_file)
                    files_copied += 1
                except Exception as e:
                    logger.debug(f"Error copying file {src_file}: {e}")

        return files_copied

    def _populate_from_fact_store(self, repo: Repository, target_dir: Path, db: Session) -> int:
        """
        Fetches files from Azure Blob Storage / Azurite using FactFile records.
        Returns number of files written.
        """
        latest_analysis = (
            db.query(Analysis)
            .filter(Analysis.repository_id == repo.id, Analysis.status == "Completed")
            .order_by(Analysis.created_at.desc())
            .first()
        )
        if not latest_analysis:
            return 0

        fact_files = db.query(FactFile).filter(FactFile.analysis_id == latest_analysis.id).all()
        if not fact_files:
            return 0

        storage = get_storage()
        files_written = 0

        for ff in fact_files:
            if not ff.path:
                continue
            clean_path = ff.path.replace("\\", "/").lstrip("./").lstrip("/")
            dest_file = target_dir / clean_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            # Try reading from blob
            if ff.blob_name and storage.object_exists(ff.blob_name):
                try:
                    content_bytes = storage.get_object(ff.blob_name)
                    dest_file.write_bytes(content_bytes)
                    files_written += 1
                except Exception as e:
                    logger.debug(f"Error reading blob {ff.blob_name}: {e}")

        return files_written

    def _ensure_git_baseline(self, target_dir: Path) -> None:
        """
        Ensures target_dir is a valid Git repository with an initial baseline commit.
        """
        git_dir = target_dir / ".git"
        try:
            if not git_dir.exists():
                subprocess.run(["git", "init"], cwd=target_dir, capture_output=True, check=True, timeout=10)
                subprocess.run(["git", "config", "user.name", "GitOnBoard Agent"], cwd=target_dir, capture_output=True, timeout=10)
                subprocess.run(["git", "config", "user.email", "agent@gitonboard.local"], cwd=target_dir, capture_output=True, timeout=10)

            # Check commit count
            res = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=target_dir, capture_output=True, timeout=10)
            if res.returncode != 0:
                subprocess.run(["git", "add", "."], cwd=target_dir, capture_output=True, timeout=15)
                subprocess.run(["git", "commit", "-m", "Initial repository baseline", "--allow-empty"], cwd=target_dir, capture_output=True, timeout=15)
        except Exception as err:
            logger.warning(f"Git baseline init error in {target_dir}: {err}")

    def provision(
        self,
        repo_identifier: str,
        worktree_path: Path,
        db: Optional[Session] = None,
    ) -> bool:
        """
        Main entry point: Provisions real repository contents into worktree_path.
        Returns True if the worktree was successfully populated.
        """
        worktree_path.mkdir(parents=True, exist_ok=True)

        # If already populated with files, just ensure Git baseline is present
        if self.is_worktree_populated(worktree_path):
            self._ensure_git_baseline(worktree_path)
            return True

        files_populated = 0
        should_close_db = False
        if db is None:
            try:
                db = SessionLocal()
                should_close_db = True
            except Exception:
                db = None

        try:
            # Source 1: Check if repo_identifier corresponds to a local directory in data/repos
            local_repos_root = Path(settings.storage_path) / "repos"
            for candidate in [local_repos_root / repo_identifier, local_repos_root / repo_identifier.lower()]:
                if candidate.exists() and candidate.is_dir() and candidate != worktree_path:
                    files_populated = self._copy_directory_contents(candidate, worktree_path)
                    if files_populated > 0:
                        logger.info(f"Provisioned {files_populated} files from local repo cache: {candidate}")
                        break

            # Source 2: Check active project root if repo matches current workspace (e.g. GitOnboard)
            if files_populated == 0:
                workspace_dir = Path(settings.workspace_dir).resolve()
                clean_name = repo_identifier.lower().replace("-", "").replace("_", "")
                ws_name = workspace_dir.name.lower().replace("-", "").replace("_", "")

                if clean_name in ws_name or ws_name in clean_name or repo_identifier == "default":
                    files_populated = self._copy_directory_contents(workspace_dir, worktree_path)
                    if files_populated > 0:
                        logger.info(f"Provisioned {files_populated} files from active workspace: {workspace_dir}")

            # Source 3: Fact Store / Azurite blobs in database
            if files_populated == 0 and db is not None:
                # Find matching repository
                repo = None
                if repo_identifier.isdigit():
                    repo = db.query(Repository).filter(Repository.id == int(repo_identifier)).first()
                if not repo:
                    repo = db.query(Repository).filter(Repository.url.ilike(f"%/{repo_identifier}")).first()
                if not repo:
                    repo = db.query(Repository).filter(Repository.url.ilike(f"%/{repo_identifier}.git")).first()
                if not repo:
                    # Fallback to latest created repository
                    repo = db.query(Repository).order_by(Repository.id.desc()).first()

                if repo:
                    files_populated = self._populate_from_fact_store(repo, worktree_path, db)
                    if files_populated > 0:
                        logger.info(f"Provisioned {files_populated} files from Azurite / Fact Store for repo '{repo.url}'")

        except Exception as e:
            logger.error(f"Error provisioning worktree '{worktree_path}': {e}", exc_info=True)
        finally:
            if should_close_db and db is not None:
                db.close()

        # Step 4: Ensure git baseline commit
        self._ensure_git_baseline(worktree_path)
        return self.is_worktree_populated(worktree_path)
