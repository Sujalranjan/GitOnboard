"""
diff_parser: Parses unified-diff text (as produced by GitManager.get_diff) into
per-file FileChangeData records for persistence and display.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

FILE_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
OLD_FILE_RE = re.compile(r"^--- (.+)$")
NEW_FILE_RE = re.compile(r"^\+\+\+ (.+)$")


@dataclass
class FileChangeData:
    file_path: str
    change_type: str  # ADDED | MODIFIED | DELETED
    lines_added: int
    lines_removed: int
    diff_patch: str


def _strip_prefix(path: str) -> str:
    path = path.strip()
    if path == "/dev/null":
        return path
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def _split_into_file_blocks(diff_text: str) -> List[List[str]]:
    """
    Splits unified diff text into per-file line blocks. A new block starts at a
    `diff --git` header, or — for the untracked-file appendix GitManager.get_diff()
    produces, which has no `diff --git` header — at a bare `--- ` line, as long as
    we're not already inside a `diff --git` block (whose own `--- `/`+++ ` lines
    belong to the same block).
    """
    blocks: List[List[str]] = []
    current: List[str] = []
    current_has_git_header = False

    for line in diff_text.splitlines():
        is_git_header = line.startswith("diff --git ")
        is_bare_old_marker = line.startswith("--- ") and not current_has_git_header and bool(current)

        if is_git_header or is_bare_old_marker:
            if current:
                blocks.append(current)
            current = [line]
            current_has_git_header = is_git_header
        else:
            current.append(line)

    if current:
        blocks.append(current)

    return blocks


def parse_unified_diff(diff_text: str) -> List[FileChangeData]:
    """
    Splits unified diff text into per-file blocks and computes change type and
    added/removed line counts for each file. Handles both `diff --git` style
    hunks and the plain `--- /dev/null` / `+++ b/<path>` style used for
    untracked-file additions in GitManager.get_diff().
    """
    if not diff_text or not diff_text.strip():
        return []

    results: List[FileChangeData] = []

    for block in _split_into_file_blocks(diff_text):
        header_path: Optional[str] = None
        for line in block:
            m = FILE_HEADER_RE.match(line)
            if m:
                header_path = m.group(2)  # the post-change (b/) side
                break

        old_marker: Optional[str] = None
        new_marker: Optional[str] = None
        for line in block:
            m = OLD_FILE_RE.match(line)
            if m:
                old_marker = _strip_prefix(m.group(1))
            m = NEW_FILE_RE.match(line)
            if m:
                new_marker = _strip_prefix(m.group(1))

        if old_marker is not None or new_marker is not None:
            # --- / +++ lines are authoritative for add/delete detection — the
            # `diff --git` header alone never indicates add vs. modify vs. delete.
            if old_marker == "/dev/null":
                change_type = "ADDED"
                file_path = new_marker
            elif new_marker == "/dev/null":
                change_type = "DELETED"
                file_path = old_marker
            else:
                change_type = "MODIFIED"
                file_path = new_marker or old_marker
        elif header_path:
            # No --- /+++ lines at all (e.g. a pure rename/mode-change hunk).
            change_type = "MODIFIED"
            file_path = header_path
        else:
            continue

        if not file_path or file_path == "/dev/null":
            continue

        lines_added = 0
        lines_removed = 0
        for line in block:
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                lines_added += 1
            elif line.startswith("-"):
                lines_removed += 1

        results.append(
            FileChangeData(
                file_path=file_path,
                change_type=change_type,
                lines_added=lines_added,
                lines_removed=lines_removed,
                diff_patch="\n".join(block),
            )
        )

    return results
