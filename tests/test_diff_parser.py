"""
Unit tests for backend.services.diff_parser.parse_unified_diff.
"""
from __future__ import annotations

from backend.services.diff_parser import parse_unified_diff


def test_empty_diff_returns_no_changes():
    assert parse_unified_diff("") == []
    assert parse_unified_diff("   \n  ") == []


def test_modified_file_diff():
    diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def main():\n"
        "-    pass\n"
        "+    print('hello')\n"
        "+    return True\n"
    )
    changes = parse_unified_diff(diff)
    assert len(changes) == 1
    c = changes[0]
    assert c.file_path == "src/app.py"
    assert c.change_type == "MODIFIED"
    assert c.lines_added == 2
    assert c.lines_removed == 1
    assert "print('hello')" in c.diff_patch


def test_added_file_diff_git_style():
    diff = (
        "diff --git a/new_module.py b/new_module.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/new_module.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def hello():\n"
        "+    return 'hi'\n"
    )
    changes = parse_unified_diff(diff)
    assert len(changes) == 1
    c = changes[0]
    assert c.file_path == "new_module.py"
    assert c.change_type == "ADDED"
    assert c.lines_added == 2
    assert c.lines_removed == 0


def test_added_untracked_file_appendix_style():
    # Matches the untracked-file appendix format GitManager.get_diff() appends.
    diff = "\n--- /dev/null\n+++ b/tests/test_implementation.py\n+def test_verification_pass(): assert True\n"
    changes = parse_unified_diff(diff)
    assert len(changes) == 1
    c = changes[0]
    assert c.file_path == "tests/test_implementation.py"
    assert c.change_type == "ADDED"
    assert c.lines_added == 1
    assert c.lines_removed == 0


def test_deleted_file_diff():
    diff = (
        "diff --git a/old_module.py b/old_module.py\n"
        "deleted file mode 100644\n"
        "--- a/old_module.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-def gone():\n"
        "-    pass\n"
    )
    changes = parse_unified_diff(diff)
    assert len(changes) == 1
    c = changes[0]
    assert c.file_path == "old_module.py"
    assert c.change_type == "DELETED"
    assert c.lines_added == 0
    assert c.lines_removed == 2


def test_multiple_files_in_one_diff():
    diff = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/b.py b/b.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/b.py\n"
        "@@ -0,0 +1 @@\n"
        "+content\n"
    )
    changes = parse_unified_diff(diff)
    assert len(changes) == 2
    paths = {c.file_path: c for c in changes}
    assert paths["a.py"].change_type == "MODIFIED"
    assert paths["b.py"].change_type == "ADDED"
