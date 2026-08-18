"""
Tests for Issue #7 — StaticVerifier must parse repository-relative paths with
POSIX semantics regardless of host OS, so a Windows-style ("\\") and a
POSIX-style ("/") modified_files entry for the same logical file behave
identically, and out-of-root ("..") entries are skipped defensively rather
than causing an unexpected filesystem read outside the worktree.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.verification.static_verifier import StaticVerifier


@pytest.fixture()
def worktree(tmp_path: Path) -> Path:
    nested = tmp_path / "archive" / "legacy" / "backend"
    nested.mkdir(parents=True)
    (nested / "foo.py").write_text("import os\n", encoding="utf-8")
    return tmp_path


def test_static_verifier_posix_and_windows_paths_produce_same_result(worktree):
    verifier = StaticVerifier()

    posix_result = verifier.verify(worktree, modified_files=["archive/legacy/backend/foo.py"])
    windows_result = verifier.verify(worktree, modified_files=["archive\\legacy\\backend\\foo.py"])

    assert posix_result.details["target_files_count"] == 1
    assert windows_result.details["target_files_count"] == 1
    assert posix_result.passed == windows_result.passed
    assert len(posix_result.defects) == len(windows_result.defects)


def test_static_verifier_mixed_separators_resolve_to_same_file(worktree):
    verifier = StaticVerifier()
    result = verifier.verify(worktree, modified_files=["archive\\legacy/backend\\foo.py"])
    assert result.details["target_files_count"] == 1


def test_static_verifier_skips_traversal_entries_without_crashing(worktree):
    verifier = StaticVerifier()
    # A malformed/malicious modified_files entry must never be joined
    # directly onto wt_path — it should be skipped, not raise or escape.
    result = verifier.verify(worktree, modified_files=["../../outside.py", "..\\..\\outside.py"])
    assert result.details["target_files_count"] == 0


def test_static_verifier_relative_import_check_uses_posix_parts(worktree):
    """
    `_check_python_relative_import` must split the repository-relative path
    with POSIX semantics — this indirectly exercises the PurePosixPath fix
    for `dir_parts = PurePosixPath(rel_file).parent.parts` by verifying a
    relative import inside a nested (Windows-style-input) file resolves
    against the correct directory rather than crashing or mis-resolving.
    """
    nested = worktree / "archive" / "legacy" / "backend"
    (nested / "helper.py").write_text("x = 1\n", encoding="utf-8")
    (nested / "foo.py").write_text("from .helper import x\n", encoding="utf-8")

    verifier = StaticVerifier()
    result = verifier.verify(worktree, modified_files=["archive\\legacy\\backend\\foo.py"])

    # The relative import resolves to a real file, so no STATIC_SYMBOL_MISSING
    # defect should be raised for it.
    assert not any("helper" in (d.symbol or "") for d in result.defects)
