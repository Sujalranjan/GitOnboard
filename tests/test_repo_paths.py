"""
Unit tests for backend.utils.repo_paths — the centralized repository-relative
path canonicalization utility introduced to fix the Windows "\\" vs POSIX "/"
mismatches in RIM entities, /scan, diff parsing, and verification, and to
provide a single containment-safe join for anything that writes files onto a
worktree/repo root from a caller-supplied relative path.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.utils.repo_paths import (
    PathTraversalError,
    ancestor_dirs,
    has_traversal,
    is_drive_or_unc,
    normalize_relative,
    posix_name,
    posix_parent,
    safe_join,
    to_posix,
)


# ──────────────────────────────────────────────────────────────────────────────
# to_posix: pure separator/component normalization
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("archive/legacy/backend/tests/foo.py", "archive/legacy/backend/tests/foo.py"),
        ("archive\\legacy\\backend\\tests\\foo.py", "archive/legacy/backend/tests/foo.py"),
        ("archive\\legacy/backend\\tests/foo.py", "archive/legacy/backend/tests/foo.py"),
        ("archive//legacy///backend/tests/foo.py", "archive/legacy/backend/tests/foo.py"),
        ("archive/./legacy/./backend/tests/foo.py", "archive/legacy/backend/tests/foo.py"),
        ("", ""),
        ("foo.py", "foo.py"),
    ],
)
def test_to_posix_normalizes_mixed_and_windows_paths(raw, expected):
    assert to_posix(raw) == expected


def test_to_posix_preserves_leading_slash():
    assert to_posix("/archive/legacy") == "/archive/legacy"


# ──────────────────────────────────────────────────────────────────────────────
# posix_parent / posix_name
# ──────────────────────────────────────────────────────────────────────────────

def test_posix_parent_and_name_nested():
    path = "archive/legacy/backend/tests/foo.py"
    assert posix_parent(path) == "archive/legacy/backend/tests"
    assert posix_name(path) == "foo.py"


def test_posix_parent_top_level_is_empty():
    assert posix_parent("README.md") == ""
    assert posix_name("README.md") == "README.md"


def test_posix_parent_from_windows_input_matches_posix_input():
    assert posix_parent("archive\\legacy\\backend") == posix_parent("archive/legacy/backend")
    assert posix_parent("archive\\legacy\\backend") == "archive/legacy"


# ──────────────────────────────────────────────────────────────────────────────
# ancestor_dirs: Issue #1 — full ancestor chain, not just immediate parent
# ──────────────────────────────────────────────────────────────────────────────

def test_ancestor_dirs_full_chain():
    assert ancestor_dirs("archive/legacy/backend/tests/intelligence/analysis/test_analysis.py") == [
        "archive",
        "archive/legacy",
        "archive/legacy/backend",
        "archive/legacy/backend/tests",
        "archive/legacy/backend/tests/intelligence",
        "archive/legacy/backend/tests/intelligence/analysis",
    ]


def test_ancestor_dirs_top_level_file_has_no_ancestors():
    assert ancestor_dirs("README.md") == []


def test_ancestor_dirs_windows_input_matches_posix_input():
    assert ancestor_dirs("archive\\legacy\\backend\\foo.py") == ancestor_dirs("archive/legacy/backend/foo.py")


# ──────────────────────────────────────────────────────────────────────────────
# is_drive_or_unc / normalize_relative
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw",
    ["C:\\Windows\\System32", "C:/Windows/System32", "D:\\data", r"\\host\share\x"],
)
def test_is_drive_or_unc_true(raw):
    assert is_drive_or_unc(raw) is True


@pytest.mark.parametrize("raw", ["archive/legacy", "src/main.py", "///", ""])
def test_is_drive_or_unc_false(raw):
    assert is_drive_or_unc(raw) is False


def test_normalize_relative_strips_leading_slash_and_dot_segments():
    assert normalize_relative("./src/auth/login.py") == "src/auth/login.py"
    assert normalize_relative("/src/auth/login.py") == "src/auth/login.py"
    assert normalize_relative("src\\auth\\login.py") == "src/auth/login.py"


@pytest.mark.parametrize(
    "bad",
    ["../secret.txt", "src/../../secret.txt", "..\\secret.txt", "a/b/../../../c"],
)
def test_normalize_relative_rejects_traversal(bad):
    with pytest.raises(PathTraversalError):
        normalize_relative(bad)


@pytest.mark.parametrize("bad", ["C:\\Windows\\System32", r"\\host\share\x"])
def test_normalize_relative_rejects_drive_and_unc(bad):
    with pytest.raises(PathTraversalError):
        normalize_relative(bad)


def test_has_traversal():
    assert has_traversal("a/../b") is True
    assert has_traversal("a\\..\\b") is True
    assert has_traversal("a/b/c") is False
    assert has_traversal("") is False


# ──────────────────────────────────────────────────────────────────────────────
# safe_join: Issue #8 — containment security
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def root_dir():
    return Path(tempfile.mkdtemp(prefix="gitonboard_safe_join_"))


def test_safe_join_normal_case(root_dir):
    result = safe_join(root_dir, "archive/legacy/foo.py")
    assert result == (root_dir.resolve() / "archive" / "legacy" / "foo.py")


@pytest.mark.parametrize(
    "malicious",
    [
        "../../outside.txt",
        "..\\..\\outside.txt",
        "foo/../../outside.txt",
        "foo/..\\../outside.txt",
        "C:\\Windows\\System32\\evil.dll",
        "C:/Windows/System32/evil.dll",
        r"\\attacker-host\share\payload.exe",
        "",
        "///",
    ],
)
def test_safe_join_rejects_traversal_and_absolute_variants(root_dir, malicious):
    with pytest.raises(PathTraversalError):
        safe_join(root_dir, malicious)


def test_safe_join_result_always_under_root(root_dir):
    result = safe_join(root_dir, "a/b/c/d.txt")
    result.relative_to(root_dir.resolve())  # raises ValueError (test failure) if not contained
