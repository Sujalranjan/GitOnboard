"""
Directory-tree construction for the /scan API's `hierarchy` response.

Extracted as a standalone, unit-testable function (rather than an inline
closure inside the route handler) specifically so its correctness — robust
to out-of-order, incomplete, or Windows-style directory input — can be
verified without a full DB/RIM fixture. See tests/test_directory_tree.py.
"""
from __future__ import annotations

from typing import Dict, Iterable, Tuple

from backend.utils.repo_paths import posix_name, posix_parent, to_posix


def ensure_dir_node(hierarchy: dict, dirs_by_path: Dict[str, dict], path: str) -> dict:
    """
    Returns the tree node for canonical directory `path` within `hierarchy` /
    `dirs_by_path`, recursively creating any missing ancestor nodes first.
    Safe against out-of-order, incomplete, or duplicate directory input: a
    node is created at most once per path, and a later "real" entry for a
    path that was already auto-created as an ancestor placeholder simply
    reuses that node. `path` must already be POSIX-canonical (see `to_posix`).
    """
    if path in dirs_by_path:
        return dirs_by_path[path]
    parent_path = posix_parent(path)
    parent_node = ensure_dir_node(hierarchy, dirs_by_path, parent_path) if parent_path else hierarchy
    node = {"name": posix_name(path), "type": "directory", "path": path, "children": []}
    dirs_by_path[path] = node
    parent_node["children"].append(node)
    return node


def build_directory_hierarchy(repo_name: str, dir_paths: Iterable[str]) -> Tuple[dict, Dict[str, dict]]:
    """
    Builds the nested `hierarchy` tree for a flat collection of
    repository-relative directory paths.

    Robust against the inputs that used to silently flatten the tree:
    - Windows-style ("\\") or mixed-separator paths are canonicalized.
    - Any input order is accepted — parents don't need to precede children.
    - Missing intermediary ancestors are reconstructed on demand rather than
      attaching their descendants to the root.
    - Duplicate paths (or a path that arrives after already being
      auto-created as an ancestor placeholder) never produce duplicate nodes.

    Returns (hierarchy_root, dirs_by_path) where `dirs_by_path` maps every
    canonical directory path (including "" for the root) to its tree node —
    callers that also need to attach files (which may reference ancestor
    directories not present in `dir_paths`, e.g. against stale/pre-fix data)
    should keep using `ensure_dir_node(hierarchy, dirs_by_path, parent_path)`
    rather than a plain `dirs_by_path.get(...)` lookup.
    """
    dirs_by_path: Dict[str, dict] = {}
    hierarchy = {"name": repo_name, "type": "directory", "children": [], "path": ""}
    dirs_by_path[""] = hierarchy

    for raw_path in dir_paths:
        d_path = to_posix(raw_path)
        if d_path:
            ensure_dir_node(hierarchy, dirs_by_path, d_path)

    return hierarchy, dirs_by_path
