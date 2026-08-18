"""
Tests for Issue #8 — WorktreeProvisioner._populate_from_fact_store must never
write a FactFile whose recorded `path` contains a directory-traversal
sequence outside the target worktree directory. Uses a mocked DB session and
storage backend (no live Postgres/Azurite needed) to isolate the file-write
path-safety logic itself.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.services.worktree_provisioner import WorktreeProvisioner


def _fake_fact_file(path: str, blob_name: str = "blob-key") -> SimpleNamespace:
    return SimpleNamespace(path=path, blob_name=blob_name)


def _run_populate(tmp_path: Path, fact_files, file_bytes: bytes = b"content"):
    target_dir = tmp_path / "worktree"
    target_dir.mkdir()

    db = MagicMock()
    analysis_query = MagicMock()
    analysis_query.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(id=1)
    fact_file_query = MagicMock()
    fact_file_query.filter.return_value.all.return_value = fact_files

    def query_side_effect(model):
        if model.__name__ == "Analysis":
            return analysis_query
        return fact_file_query

    db.query.side_effect = query_side_effect

    fake_storage = MagicMock()
    fake_storage.object_exists.return_value = True
    fake_storage.get_object.return_value = file_bytes

    provisioner = WorktreeProvisioner(tmp_path / "base")
    repo = SimpleNamespace(id=1)

    with patch("backend.services.worktree_provisioner.get_storage", return_value=fake_storage):
        written = provisioner._populate_from_fact_store(repo, target_dir, db)

    return target_dir, written


def test_populate_from_fact_store_writes_benign_nested_path(tmp_path):
    target_dir, written = _run_populate(
        tmp_path, [_fake_fact_file("archive/legacy/backend/foo.py")]
    )
    assert written == 1
    assert (target_dir / "archive" / "legacy" / "backend" / "foo.py").read_bytes() == b"content"


def test_populate_from_fact_store_skips_traversal_path_without_escaping(tmp_path):
    target_dir, written = _run_populate(
        tmp_path, [_fake_fact_file("../../outside.txt")]
    )
    assert written == 0
    # Nothing must have been written anywhere outside target_dir.
    assert not (tmp_path / "outside.txt").exists()
    assert not (tmp_path.parent / "outside.txt").exists()


def test_populate_from_fact_store_skips_windows_drive_path(tmp_path):
    target_dir, written = _run_populate(
        tmp_path, [_fake_fact_file("C:\\Windows\\System32\\evil.dll")]
    )
    assert written == 0
    assert list(target_dir.iterdir()) == []


def test_populate_from_fact_store_mixed_valid_and_malicious_only_writes_valid(tmp_path):
    target_dir, written = _run_populate(
        tmp_path,
        [
            _fake_fact_file("src/main.py"),
            _fake_fact_file("../../../etc/passwd"),
            _fake_fact_file("src/utils.py"),
        ],
    )
    assert written == 2
    assert (target_dir / "src" / "main.py").exists()
    assert (target_dir / "src" / "utils.py").exists()
