"""
GitManager: Isolated Git Sandbox Manager using Python subprocess.

Manages bare/local repositories and ephemeral Git worktrees under:
  STORAGE_PATH/worktrees/<repo_id>_<run_id>
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Union

from backend.config import settings
from backend.services.worktree_provisioner import WorktreeProvisioner

logger = logging.getLogger(__name__)


class GitManagerError(Exception):
    """Base exception for Git sandbox manager operations."""
    pass


class GitManager:
    """
    Manages isolated Git worktrees and repository sandboxes.
    """

    def __init__(self, base_worktree_dir: Optional[Union[str, Path]] = None):
        self.base_dir = Path(base_worktree_dir or settings.worktrees_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.provisioner = WorktreeProvisioner(self.base_dir)

    def _run_cmd(
        self,
        cmd: List[str],
        cwd: Optional[Union[str, Path]] = None,
        timeout_sec: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a git command via subprocess with timeout and error handling."""
        cwd_path = Path(cwd).resolve() if cwd else None
        try:
            logger.debug(f"GitManager running command: {' '.join(cmd)} in cwd={cwd_path}")
            result = subprocess.run(
                cmd,
                cwd=cwd_path,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=True,
            )
            return result
        except subprocess.TimeoutExpired as err:
            msg = f"Git command timed out after {timeout_sec}s: {' '.join(cmd)}"
            logger.error(msg)
            raise GitManagerError(msg) from err
        except subprocess.CalledProcessError as err:
            stderr = err.stderr.strip() if err.stderr else str(err)
            msg = f"Git command failed (exit {err.returncode}): {' '.join(cmd)}\nError: {stderr}"
            logger.error(msg)
            raise GitManagerError(msg) from err
        except Exception as err:
            msg = f"Unexpected error executing git command {' '.join(cmd)}: {err}"
            logger.error(msg)
            raise GitManagerError(msg) from err

    def _ensure_git_repo(self, repo_path: Path) -> None:
        """Verify or initialize target path as a valid Git repository."""
        git_dir = repo_path / ".git"
        if not git_dir.exists() and not (repo_path / "HEAD").exists():
            logger.info(f"Initializing Git repository at {repo_path}")
            self._run_cmd(["git", "init"], cwd=repo_path)
            self._run_cmd(["git", "config", "user.name", "GitOnBoard Agent"], cwd=repo_path)
            self._run_cmd(["git", "config", "user.email", "agent@gitonboard.local"], cwd=repo_path)
            try:
                self._run_cmd(["git", "add", "."], cwd=repo_path)
                self._run_cmd(["git", "commit", "-m", "Initial baseline commit", "--allow-empty"], cwd=repo_path)
            except Exception as err:
                logger.warning(f"Could not create initial commit: {err}")

    def create_worktree(
        self,
        repo_id: Union[str, int],
        run_id: str,
        source_repo_path: Optional[Union[str, Path]] = None,
        base_branch: str = "main",
        new_branch: Optional[str] = None,
    ) -> Path:
        """
        Creates an isolated Git worktree sandbox under STORAGE_PATH/worktrees/<repo_id>_<run_id>.
        Guarantees source repository and target worktree are populated with real repository files.
        """
        repo_id_str = str(repo_id)
        worktree_name = f"{repo_id_str}_{run_id}"
        worktree_path = (self.base_dir / worktree_name).resolve()

        # Resolve source repository directory
        if source_repo_path:
            source_path = Path(source_repo_path).resolve()
        else:
            source_path = (Path(settings.storage_path) / "repos" / repo_id_str).resolve()

        # Provision repository contents into source_path if not populated
        if not self.provisioner.is_worktree_populated(source_path):
            self.provisioner.provision(repo_identifier=repo_id_str, worktree_path=source_path)

        self._ensure_git_repo(source_path)

        # Cleanup target worktree path if it already exists
        if worktree_path.exists():
            self.remove_worktree(worktree_path, source_repo_path=source_path)

        branch = new_branch or f"sandbox/{run_id}"

        # Try creating worktree from base_branch, or create new branch from HEAD
        try:
            self._run_cmd(
                ["git", "worktree", "add", "-b", branch, str(worktree_path)],
                cwd=source_path,
            )
        except GitManagerError:
            try:
                self._run_cmd(
                    ["git", "worktree", "add", str(worktree_path), branch],
                    cwd=source_path,
                )
            except GitManagerError:
                try:
                    self._run_cmd(
                        ["git", "worktree", "add", "-B", branch, str(worktree_path), "HEAD"],
                        cwd=source_path,
                    )
                except GitManagerError:
                    # Direct copy fallback if git worktree add fails
                    self.provisioner.provision(repo_identifier=repo_id_str, worktree_path=worktree_path)

        # Ensure worktree is populated with repository files
        if not self.provisioner.is_worktree_populated(worktree_path):
            self.provisioner.provision(repo_identifier=repo_id_str, worktree_path=worktree_path)

        logger.info(f"Created isolated Git worktree sandbox: {worktree_path} on branch {branch}")
        return worktree_path


    def get_diff(
        self,
        worktree_path: Union[str, Path],
        base_branch: str = "main",
    ) -> str:
        """
        Returns unified diff string of modifications inside the worktree against base_branch or HEAD.
        Includes untracked newly added files.
        """
        wt_path = Path(worktree_path).resolve()
        if not wt_path.exists():
            raise GitManagerError(f"Worktree directory does not exist: {wt_path}")

        diff_output = ""
        # 1. Staged and unstaged tracked changes
        try:
            res = self._run_cmd(["git", "diff", "HEAD"], cwd=wt_path)
            diff_output = res.stdout
        except GitManagerError:
            try:
                res = self._run_cmd(["git", "diff", base_branch], cwd=wt_path)
                diff_output = res.stdout
            except GitManagerError:
                diff_output = ""

        # 2. Append untracked files
        try:
            untracked = self._run_cmd(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=wt_path,
            ).stdout.splitlines()

            for rel_file in untracked:
                if not rel_file.strip():
                    continue
                file_full = wt_path / rel_file
                if file_full.is_file():
                    try:
                        content = file_full.read_text(encoding="utf-8", errors="replace")
                        diff_output += f"\n--- /dev/null\n+++ b/{rel_file}\n"
                        for line in content.splitlines():
                            diff_output += f"+{line}\n"
                    except Exception:
                        pass
        except Exception as err:
            logger.warning(f"Error reading untracked files in diff: {err}")

        return diff_output.strip()

    def list_modified_files(
        self,
        worktree_path: Union[str, Path],
        base_branch: str = "main",
    ) -> List[str]:
        """
        Returns list of relative file paths modified, created, or deleted in the worktree.
        """
        wt_path = Path(worktree_path).resolve()
        if not wt_path.exists():
            return []

        modified_set = set()

        # Status porcelain
        try:
            status_lines = self._run_cmd(
                ["git", "status", "--porcelain"],
                cwd=wt_path,
            ).stdout.splitlines()

            for line in status_lines:
                if len(line) >= 3:
                    file_path = line[3:].strip()
                    if file_path:
                        modified_set.add(file_path.replace("\\", "/"))
        except Exception as err:
            logger.warning(f"Error checking git status: {err}")

        # Git diff file list
        try:
            diff_files = self._run_cmd(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=wt_path,
            ).stdout.splitlines()

            for f in diff_files:
                if f.strip():
                    modified_set.add(f.strip().replace("\\", "/"))
        except Exception:
            pass

        return sorted(list(modified_set))

    def apply_patch(
        self,
        worktree_path: Union[str, Path],
        patch_text: str,
    ) -> bool:
        """
        Applies unified patch text to the worktree sandbox.
        """
        wt_path = Path(worktree_path).resolve()
        if not wt_path.exists():
            raise GitManagerError(f"Worktree directory does not exist: {wt_path}")

        if not patch_text.strip():
            return True

        patch_file = wt_path / ".gitonboard_tmp.patch"
        try:
            patch_file.write_text(patch_text, encoding="utf-8")
            self._run_cmd(["git", "apply", "--ignore-space-change", "--ignore-whitespace", str(patch_file)], cwd=wt_path)
            return True
        except GitManagerError as err:
            logger.warning(f"git apply failed, attempting git apply --reject: {err}")
            try:
                self._run_cmd(["git", "apply", "--reject", str(patch_file)], cwd=wt_path)
                return True
            except Exception as e:
                logger.error(f"Failed to apply patch to worktree {wt_path}: {e}")
                return False
        finally:
            if patch_file.exists():
                try:
                    patch_file.unlink()
                except Exception:
                    pass

    def remove_worktree(
        self,
        worktree_path: Union[str, Path],
        source_repo_path: Optional[Union[str, Path]] = None,
    ) -> bool:
        """
        Force removes worktree directory and cleans up Git worktree registration.
        """
        wt_path = Path(worktree_path).resolve()
        if not wt_path.exists():
            return True

        # Attempt git worktree remove --force
        try:
            cwd_path = Path(source_repo_path).resolve() if source_repo_path else wt_path
            self._run_cmd(["git", "worktree", "remove", "--force", str(wt_path)], cwd=cwd_path)
        except Exception as err:
            logger.warning(f"git worktree remove --force command warning: {err}")

        # Force directory removal if still exists
        if wt_path.exists():
            try:
                shutil.rmtree(wt_path, ignore_errors=True)
            except Exception as err:
                logger.error(f"Error removing worktree directory {wt_path}: {err}")

        logger.info(f"Removed Git worktree sandbox: {wt_path}")
        return not wt_path.exists()
