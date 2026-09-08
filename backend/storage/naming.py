"""
Deterministic, secure blob naming utilities for repository storage.
"""
from __future__ import annotations
import re

from backend.utils.repo_paths import PathTraversalError, normalize_relative


def sanitize_relative_path(path: str) -> str:
    """
    Normalizes a repository-relative path and guards against directory
    traversal (`../`), Windows drive-qualified paths, and UNC paths.

    Delegates to backend.utils.repo_paths for the canonicalization/traversal
    logic shared with the rest of the codebase; raises ValueError (this
    module's existing contract) rather than PathTraversalError.
    """
    try:
        clean = normalize_relative(path.strip())
    except PathTraversalError as err:
        raise ValueError(f"Path traversal detected in relative path: {path!r}") from err

    if not clean:
        raise ValueError(f"Invalid empty repository relative path: {path!r}")

    return clean


def build_blob_key(repository_hash: str, snapshot_id: str, relative_path: str) -> str:
    """
    Constructs a deterministic, isolated object key for a repository snapshot file.

    Uses repository_hash (UUID) instead of repository_id for consistency with
    UUID-based repository identification throughout the system.

    Format:
        repositories/{repository_hash}/snapshots/{snapshot_id}/{cleaned_relative_path}
    """
    clean_hash = str(repository_hash).strip()
    if not clean_hash:
        raise ValueError("repository_hash cannot be empty")

    clean_snap = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(snapshot_id).strip())
    if not clean_snap:
        clean_snap = "default"

    clean_rel = sanitize_relative_path(relative_path)
    return f"repositories/{clean_hash}/snapshots/{clean_snap}/{clean_rel}"
