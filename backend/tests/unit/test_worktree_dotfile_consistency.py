"""
Regression coverage for the File Explorer / Terminal filesystem-consistency bug.

Root cause: the repository scanner (feeds the RIM model -> /scan -> File
Explorer), the analysis blob-upload walk (feeds the Fact Store -> terminal
worktree provisioning), and the worktree provisioner's local-cache copy path
each independently filtered out any file whose name started with "."
(`file.startswith(".")` / `f.startswith(".git")`). Because these three
enumeration passes are the *only* things that decide what "belongs" to a
repository, and each applied a different dotfile rule, the File Explorer and
the sandbox terminal could end up looking at different file sets for the same
repository even though both ultimately derive from the same source tree.

These tests build a synthetic source tree (never asserting against any
specific real repository name) and verify that every real repository file --
dotfile or not -- survives both enumeration paths identically.
"""
import os
from pathlib import Path

import pytest

from backend.intelligence.engine.scanner.scanner import RepositoryScanner
from backend.services.worktree_provisioner import WorktreeProvisioner


def _make_fixture_repo(root: Path) -> set:
    """Creates a dynamic fixture repo with ordinary and dotfile content.
    Returns the set of repo-relative POSIX paths that a real terminal's
    `ls -la` / `find . -maxdepth N` would report as real files.
    """
    files = {
        "README.md": "# Fixture\n",
        ".gitignore": "*.pyc\n__pycache__/\n",
        ".editorconfig": "root = true\n",
        ".env.example": "API_KEY=changeme\n",
        ".github/workflows/test.yml": "name: test\n",
        "src/main.py": "def main():\n    pass\n",
    }
    expected = set()
    for rel_path, content in files.items():
        dest = root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        expected.add(rel_path)
    return expected


def test_repository_scanner_includes_dotfiles(tmp_path):
    """The scanner that ultimately backs the File Explorer's /scan hierarchy
    must not silently drop legitimate repository dotfiles."""
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    expected = _make_fixture_repo(source_dir)

    manifest = RepositoryScanner(str(source_dir)).scan()
    scanned_paths = {f.path for f in manifest.files}

    assert expected <= scanned_paths, (
        f"Scanner dropped repository files: {expected - scanned_paths}"
    )


def test_worktree_provisioner_copy_includes_dotfiles(tmp_path):
    """The worktree provisioner's local-cache copy path (used to populate the
    terminal's actual worktree) must copy the exact same file set the
    scanner sees -- no independent dotfile filtering."""
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    expected = _make_fixture_repo(source_dir)

    target_dir = tmp_path / "worktree"
    provisioner = WorktreeProvisioner(base_worktree_dir=tmp_path / "worktrees_base")
    provisioner._copy_directory_contents(source_dir, target_dir)

    copied_paths = set()
    for root, _dirs, filenames in os.walk(target_dir):
        for name in filenames:
            rel = str(Path(root, name).relative_to(target_dir)).replace("\\", "/")
            copied_paths.add(rel)

    assert expected <= copied_paths, (
        f"Worktree provisioner dropped repository files that a real "
        f"terminal's `ls -la` would show: {expected - copied_paths}"
    )


def test_scanner_and_worktree_copy_agree_on_file_set(tmp_path):
    """File Explorer source (scanner-derived) and Terminal source
    (worktree-provisioner-derived) must report the identical relative path
    set for the same source tree -- the core consistency invariant."""
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    _make_fixture_repo(source_dir)

    manifest = RepositoryScanner(str(source_dir)).scan()
    explorer_paths = {f.path for f in manifest.files}

    target_dir = tmp_path / "worktree"
    provisioner = WorktreeProvisioner(base_worktree_dir=tmp_path / "worktrees_base")
    provisioner._copy_directory_contents(source_dir, target_dir)

    terminal_paths = set()
    for root, _dirs, filenames in os.walk(target_dir):
        for name in filenames:
            rel = str(Path(root, name).relative_to(target_dir)).replace("\\", "/")
            terminal_paths.add(rel)

    assert explorer_paths == terminal_paths, (
        f"File Explorer and Terminal disagree on repository contents.\n"
        f"Only in Explorer: {explorer_paths - terminal_paths}\n"
        f"Only in Terminal: {terminal_paths - explorer_paths}"
    )
