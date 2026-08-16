"""
Security boundaries and validation for repository tools.
Enforces containment within repository root, protects against path traversal,
rejects binary files, and enforces size/line limits.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Tuple

MAX_READ_LINES = 1000
MAX_READ_BYTES = 250 * 1024  # 250 KB
MAX_SEARCH_RESULTS = 50

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".wasm", ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".exe", ".bin", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".db", ".sqlite", ".sqlite3", ".parquet", ".arrow", ".npy", ".npz",
    ".pdf", ".docx", ".xlsx", ".pptx"
}


class RepositorySecurityError(Exception):
    """Raised when an operation attempts unauthorized access or violates boundaries."""
    pass


def is_binary_file(path: Path) -> bool:
    """Check if a file is binary based on extension and byte inspection."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        pass
    return False


def validate_repo_path(repo_root: Path, relative_path: str, allow_binary: bool = False) -> Path:
    """
    Validate that relative_path is safely contained within repo_root.
    Rejects path traversal (e.g., ../), absolute paths pointing outside root,
    symlinks pointing outside root, and binary files (unless allowed).
    """
    if not repo_root.exists() or not repo_root.is_dir():
        raise RepositorySecurityError(f"Repository root does not exist or is not a directory: {repo_root}")

    resolved_root = repo_root.resolve()

    # Clean path string
    cleaned_rel = relative_path.replace("\\", "/").strip()
    if cleaned_rel.startswith("/"):
        cleaned_rel = cleaned_rel.lstrip("/")

    # Check for obvious traversal tokens
    parts = Path(cleaned_rel).parts
    if ".." in parts:
        raise RepositorySecurityError(f"Path traversal detected: {relative_path}")

    target_path = (resolved_root / cleaned_rel).resolve()

    # Ensure target_path is within resolved_root
    try:
        target_path.relative_to(resolved_root)
    except ValueError:
        raise RepositorySecurityError(f"Path escapes repository root: {relative_path}")

    if not target_path.exists():
        raise FileNotFoundError(f"File not found in repository: {relative_path}")

    if not target_path.is_file():
        raise RepositorySecurityError(f"Target is not a regular file: {relative_path}")

    # Check binary rejection
    if not allow_binary and is_binary_file(target_path):
        raise RepositorySecurityError(f"Binary files cannot be read as text: {relative_path}")

    # Check size limit
    file_size = target_path.stat().st_size
    if file_size > MAX_READ_BYTES:
        raise RepositorySecurityError(
            f"File size ({file_size / 1024:.1f} KB) exceeds maximum allowed read size ({MAX_READ_BYTES / 1024:.1f} KB)"
        )

    return target_path


def clamp_line_range(total_lines: int, start_line: int = 1, end_line: int | None = None) -> Tuple[int, int]:
    """
    Validates and bounds 1-indexed line ranges to prevent unbounded memory usage.
    """
    if total_lines <= 0:
        return 1, 0

    s = max(1, start_line)
    if end_line is None or end_line > total_lines:
        e = min(total_lines, s + MAX_READ_LINES - 1)
    else:
        e = min(total_lines, end_line)

    if s > total_lines:
        raise RepositorySecurityError(f"Start line {s} exceeds total file lines ({total_lines})")

    if e < s:
        raise RepositorySecurityError(f"End line {e} cannot be less than start line {s}")

    if (e - s + 1) > MAX_READ_LINES:
        e = s + MAX_READ_LINES - 1

    return s, e
