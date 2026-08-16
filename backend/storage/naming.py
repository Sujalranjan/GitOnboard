"""
Deterministic, secure blob naming utilities for repository storage.
"""
from __future__ import annotations
import posixpath
import re


def sanitize_relative_path(path: str) -> str:
    """
    Normalizes a repository-relative path and guards against directory traversal (../).
    """
    normalized = path.replace("\\\\", "/").replace("\\", "/").strip()
    
    while normalized.startswith("./") or normalized.startswith("/"):
        if normalized.startswith("./"):
            normalized = normalized[2:]
        elif normalized.startswith("/"):
            normalized = normalized[1:]

    parts = []
    for part in normalized.split("/"):
        part = part.strip()
        if not part or part == ".":
            continue
        if part == "..":
            raise ValueError(f"Path traversal detected in relative path: {path!r}")
        parts.append(part)

    if not parts:
        raise ValueError(f"Invalid empty repository relative path: {path!r}")

    return "/".join(parts)


def build_blob_key(repository_id: int, snapshot_id: str, relative_path: str) -> str:
    """
    Constructs a deterministic, isolated object key for a repository snapshot file.

    Format:
        repositories/{repository_id}/snapshots/{snapshot_id}/{cleaned_relative_path}
    """
    clean_snap = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(snapshot_id).strip())
    if not clean_snap:
        clean_snap = "default"

    clean_rel = sanitize_relative_path(relative_path)
    return f"repositories/{repository_id}/snapshots/{clean_snap}/{clean_rel}"
