"""
Centralized canonicalization for repository-relative paths.

Repository-relative paths — RIM entities, the /scan API, File Explorer
responses, diff parsing, static/dynamic verification, and worktree-relative
file access — MUST use POSIX "/" separators everywhere they are persisted or
exchanged between components, regardless of the host OS the backend runs on.
This module is the single place that logic lives; callers must not
hand-roll `.replace("\\\\", "/")` elsewhere.

Absolute filesystem paths (worktree roots on disk, Docker host paths) are a
distinct concern and are intentionally NOT touched by these helpers — they
stay platform-native. See backend/verification/docker_runner.py for
host/container absolute-path translation.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import List, Union

PathLike = Union[str, Path]


class PathTraversalError(ValueError):
    """Raised when a repository-relative path attempts to escape its root."""


def to_posix(path: str) -> str:
    """
    Canonicalizes a path string to POSIX "/" form:
    - Converts "\\\\" to "/"
    - Collapses redundant separators ("a//b" -> "a/b")
    - Resolves "." components ("a/./b" -> "a/b")

    Does NOT resolve ".." components (they are meaningful to callers that
    need to detect/reject traversal — see `assert_no_traversal`/`safe_join`)
    and does NOT strip a leading "/" (callers needing repo-root-relative
    semantics should strip that themselves once, at the boundary, since
    stripping is a policy decision, not a normalization one).
    """
    if not path:
        return path
    normalized = path.replace("\\", "/")
    leading_slash = normalized.startswith("/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    result = "/".join(parts)
    return ("/" + result) if leading_slash else result


def posix_parent(path: str) -> str:
    """
    Returns the parent directory of a repository-relative path, canonicalized
    to POSIX form. Returns "" for a top-level (repo-root) path.
    """
    normalized = to_posix(path).strip("/")
    if not normalized or "/" not in normalized:
        return ""
    return normalized.rsplit("/", 1)[0]


def posix_name(path: str) -> str:
    """Returns the final path component (file or directory name)."""
    normalized = to_posix(path).strip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]


def ancestor_dirs(path: str) -> List[str]:
    """
    Returns every ancestor directory of a repository-relative file/dir path,
    in root-to-leaf order (`path` itself is not included).

    "archive/legacy/backend/tests/foo.py" ->
        ["archive", "archive/legacy", "archive/legacy/backend", "archive/legacy/backend/tests"]
    """
    normalized = to_posix(path).strip("/")
    if not normalized or "/" not in normalized:
        return []
    segments = normalized.split("/")[:-1]
    return ["/".join(segments[: i + 1]) for i in range(len(segments))]


def has_traversal(path: str) -> bool:
    """True if the canonicalized path contains a ".." component."""
    normalized = to_posix(path).strip("/")
    return any(part == ".." for part in normalized.split("/") if part)


def is_drive_or_unc(path: str) -> bool:
    """
    True if `path` looks like a Windows absolute path (drive-qualified, e.g.
    'C:\\x') or a native Windows UNC path ('\\\\host\\share'). Deliberately
    does NOT flag a merely slash-heavy POSIX-style input (e.g. "///") —
    those are handled by ordinary leading-slash stripping in
    `normalize_relative`, not treated as a distinct absolute-path class.
    """
    stripped = path.strip()
    if stripped.startswith("\\\\"):
        return True
    return len(stripped) >= 2 and stripped[1] == ":" and stripped[0].isalpha()


def normalize_relative(path: str) -> str:
    """
    Canonicalizes `path` into a repository-root-relative POSIX path: converts
    separators, strips any leading "/", drops "." components, and collapses
    redundant separators. Raises PathTraversalError if `path` is Windows
    drive-qualified, a UNC path, or contains any ".." component. A bare
    leading "/" (POSIX-style accidental absolute path) is normalized away
    rather than rejected, matching this codebase's existing relative-path
    conventions. Returns "" for a path that normalizes to nothing (e.g. "" or "///").
    """
    if is_drive_or_unc(path):
        raise PathTraversalError(f"Absolute or drive-qualified path not allowed: {path!r}")

    normalized = to_posix(path).lstrip("/")
    parts: List[str] = []
    for part in normalized.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise PathTraversalError(f"Path traversal ('..') not allowed: {path!r}")
        parts.append(part)
    return "/".join(parts)


def safe_join(root: PathLike, relative_path: str) -> Path:
    """
    Joins a repository-relative path onto an absolute `root`, guaranteeing
    the resolved result stays within `root`. Rejects ".." components,
    Windows drive-qualified paths, and UNC paths in `relative_path` via
    `normalize_relative`. Also verifies the *resolved* path (post-symlink)
    stays under `root` as defense in depth. Raises PathTraversalError
    otherwise (including for an empty/all-separator `relative_path`).
    """
    root_resolved = Path(root).resolve()
    clean_rel = normalize_relative(relative_path)
    if not clean_rel:
        raise PathTraversalError(f"Empty repository-relative path: {relative_path!r}")

    candidate = (root_resolved / clean_rel).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        raise PathTraversalError(f"Resolved path escapes root: {relative_path!r}")
    return candidate
