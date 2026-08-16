import pytest
from backend.storage.naming import sanitize_relative_path, build_blob_key


def test_sanitize_relative_path_normal():
    assert sanitize_relative_path("src/auth/login.py") == "src/auth/login.py"
    assert sanitize_relative_path("./src/auth/login.py") == "src/auth/login.py"
    assert sanitize_relative_path("/src/auth/login.py") == "src/auth/login.py"
    assert sanitize_relative_path(r"src\auth\login.py") == "src/auth/login.py"


def test_sanitize_relative_path_traversal_prevention():
    with pytest.raises(ValueError, match="Path traversal detected"):
        sanitize_relative_path("../secret.txt")

    with pytest.raises(ValueError, match="Path traversal detected"):
        sanitize_relative_path("src/../../secret.txt")

    with pytest.raises(ValueError, match="Path traversal detected"):
        sanitize_relative_path(r"..\secret.txt")


def test_sanitize_relative_path_empty_error():
    with pytest.raises(ValueError, match="Invalid empty repository relative path"):
        sanitize_relative_path("")

    with pytest.raises(ValueError, match="Invalid empty repository relative path"):
        sanitize_relative_path("///")


def test_build_blob_key_deterministic():
    key = build_blob_key(repository_id=42, snapshot_id="abc123commit", relative_path="src/main.py")
    assert key == "repositories/42/snapshots/abc123commit/src/main.py"


def test_build_blob_key_special_chars_sanitized():
    key = build_blob_key(repository_id=1, snapshot_id="feature/branch@1", relative_path="./tests/test_auth.py")
    assert key == "repositories/1/snapshots/feature_branch_1/tests/test_auth.py"
