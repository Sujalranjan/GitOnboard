"""
Tests for Issues #1-#3 (incomplete ancestor directory creation, Windows "\\"
vs POSIX "/" mismatch in /scan, and missing-intermediary tree flattening).

Covers both halves of the fix:
1. backend.intelligence.engine.analyzers.symbol.SymbolAnalyzer creates a
   DIRECTORY entity for every ancestor directory of an analyzed file, not
   just its immediate parent.
2. backend.routers.repo.services.hierarchy.build_directory_hierarchy builds
   a correct, non-flattened tree regardless of input order, missing
   ancestors, duplicates, or Windows-style separators.
"""
from __future__ import annotations

from backend.intelligence.engine.analyzers.symbol import SymbolAnalyzer
from backend.intelligence.engine.parser.providers.base import ParsedFile
from backend.intelligence.rim.enums import EntityType
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.rim.repository import RepositoryModel
from backend.routers.repo.services.hierarchy import build_directory_hierarchy


def _empty_repository_model() -> RepositoryModel:
    return RepositoryModel(metadata=RepositoryMetadata(name="test-repo", path="."))


# ──────────────────────────────────────────────────────────────────────────────
# Issue #1: SymbolAnalyzer must register every ancestor DIRECTORY entity
# ──────────────────────────────────────────────────────────────────────────────

def _directory_paths(repository: RepositoryModel) -> set:
    return {
        e.location.repository_path
        for e in repository.entities.values()
        if e.type == EntityType.DIRECTORY
    }


def test_symbol_analyzer_creates_full_ancestor_chain_for_deeply_nested_file():
    file_path = "archive/legacy/backend/tests/intelligence/analysis/test_analysis.py"
    parsed = ParsedFile(file_path="x.py", language="Python", source="x = 1\n", ast=None)
    repository = _empty_repository_model()

    SymbolAnalyzer().analyze(repository, {file_path: parsed})

    assert _directory_paths(repository) == {
        "archive",
        "archive/legacy",
        "archive/legacy/backend",
        "archive/legacy/backend/tests",
        "archive/legacy/backend/tests/intelligence",
        "archive/legacy/backend/tests/intelligence/analysis",
    }


def test_symbol_analyzer_no_duplicate_directory_entities_for_sibling_files():
    parsed = ParsedFile(file_path="x.py", language="Python", source="x = 1\n", ast=None)
    repository = _empty_repository_model()

    SymbolAnalyzer().analyze(
        repository,
        {
            "archive/legacy/backend/foo.py": parsed,
            "archive/legacy/backend/bar.py": parsed,
        },
    )

    dir_ids = [e.id for e in repository.entities.values() if e.type == EntityType.DIRECTORY]
    assert len(dir_ids) == len(set(dir_ids))
    assert _directory_paths(repository) == {"archive", "archive/legacy", "archive/legacy/backend"}


def test_symbol_analyzer_top_level_file_creates_no_directories():
    parsed = ParsedFile(file_path="x.py", language="Python", source="x = 1\n", ast=None)
    repository = _empty_repository_model()

    SymbolAnalyzer().analyze(repository, {"README_stub.py": parsed})

    assert _directory_paths(repository) == set()


# ──────────────────────────────────────────────────────────────────────────────
# Issues #2/#3: hierarchy builder — order independence, missing ancestors,
# Windows-style input, duplicates
# ──────────────────────────────────────────────────────────────────────────────

def _find(node: dict, path: str):
    if node.get("path") == path:
        return node
    for child in node.get("children", []):
        found = _find(child, path)
        if found:
            return found
    return None


def _all_paths(node: dict) -> set:
    paths = {node.get("path", "")}
    for child in node.get("children", []):
        paths |= _all_paths(child)
    return paths


def test_build_hierarchy_normal_order():
    hierarchy, _ = build_directory_hierarchy(
        "repo", ["archive", "archive/legacy", "archive/legacy/backend"]
    )
    node = _find(hierarchy, "archive/legacy/backend")
    assert node is not None
    assert _find(hierarchy, "archive/legacy") is not None
    # No accidental duplication or attachment to root.
    assert len(hierarchy["children"]) == 1
    assert hierarchy["children"][0]["path"] == "archive"


def test_build_hierarchy_out_of_order_input_produces_same_tree():
    ordered, _ = build_directory_hierarchy(
        "repo", ["archive", "archive/legacy", "archive/legacy/backend", "archive/legacy/backend/tests"]
    )
    reversed_order, _ = build_directory_hierarchy(
        "repo", ["archive/legacy/backend/tests", "archive/legacy/backend", "archive/legacy", "archive"]
    )
    assert _all_paths(ordered) == _all_paths(reversed_order)


def test_build_hierarchy_missing_intermediary_ancestors_are_reconstructed():
    # Only the deepest directory is given — "archive" and "archive/legacy"
    # are never explicitly listed, matching a RIM built before the Issue #1 fix.
    hierarchy, dirs_by_path = build_directory_hierarchy("repo", ["archive/legacy/backend/tests"])

    assert "archive" in dirs_by_path
    assert "archive/legacy" in dirs_by_path
    assert "archive/legacy/backend" in dirs_by_path
    assert "archive/legacy/backend/tests" in dirs_by_path

    # "tests" must be nested under "backend", not attached directly to root.
    assert len(hierarchy["children"]) == 1
    root_child = hierarchy["children"][0]
    assert root_child["path"] == "archive"
    legacy = root_child["children"][0]
    assert legacy["path"] == "archive/legacy"
    backend = legacy["children"][0]
    assert backend["path"] == "archive/legacy/backend"
    tests = backend["children"][0]
    assert tests["path"] == "archive/legacy/backend/tests"


def test_build_hierarchy_duplicate_paths_no_duplicate_nodes():
    hierarchy, dirs_by_path = build_directory_hierarchy(
        "repo", ["archive/legacy", "archive/legacy", "archive", "archive/legacy"]
    )
    archive_node = dirs_by_path["archive"]
    assert len(archive_node["children"]) == 1


def test_build_hierarchy_windows_style_input_matches_posix_input():
    posix_tree, _ = build_directory_hierarchy(
        "repo", ["archive/legacy/backend/tests"]
    )
    windows_tree, _ = build_directory_hierarchy(
        "repo", ["archive\\legacy\\backend\\tests"]
    )
    assert _all_paths(posix_tree) == _all_paths(windows_tree)


def test_build_hierarchy_deeply_nested_acceptance_criteria_path():
    """Acceptance criteria #1/#2: the full example path from the spec must
    appear under the correct ancestor chain."""
    target = "archive/legacy/backend/tests/intelligence/analysis/test_analysis.py"
    ancestor_only = target.rsplit("/", 1)[0]  # the directory containing it
    hierarchy, dirs_by_path = build_directory_hierarchy("repo", [ancestor_only])

    node = dirs_by_path[ancestor_only]
    assert node["path"] == "archive/legacy/backend/tests/intelligence/analysis"

    # Walk the chain from root down and confirm each hop is correct.
    chain = [
        "archive",
        "archive/legacy",
        "archive/legacy/backend",
        "archive/legacy/backend/tests",
        "archive/legacy/backend/tests/intelligence",
        "archive/legacy/backend/tests/intelligence/analysis",
    ]
    current = hierarchy
    for expected_path in chain:
        assert len(current["children"]) == 1, f"expected exactly one child under {current.get('path')!r}"
        current = current["children"][0]
        assert current["path"] == expected_path
