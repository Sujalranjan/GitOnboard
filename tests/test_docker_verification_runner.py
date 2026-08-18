"""
Unit tests for backend.verification.docker_runner.DockerVerificationRunner, and for
DynamicVerifier's fallback-to-host behavior when Docker is unavailable.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.verification.docker_runner import DockerVerificationError, DockerVerificationRunner


def _docker_daemon_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


DOCKER_AVAILABLE = _docker_daemon_available()


# ──────────────────────────────────────────────────────────────────────────────
# Path translation (pure logic, no Docker daemon required)
# ──────────────────────────────────────────────────────────────────────────────

def test_translate_to_host_path_noop_when_not_set(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "host_data_dir", "")
    runner = DockerVerificationRunner()
    container_path = Path("data") / "worktrees" / "repo_task1"
    assert runner._translate_to_host_path(container_path) == str(container_path)


def test_translate_to_host_path_rebases_onto_host_dir(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "storage_path", "data")
    monkeypatch.setattr(settings, "host_data_dir", "/home/dev/gitonboard/data")
    runner = DockerVerificationRunner()

    container_path = Path("data") / "worktrees" / "repo_task1"
    result = runner._translate_to_host_path(container_path)
    assert result == "/home/dev/gitonboard/data/worktrees/repo_task1"


def test_translate_to_host_path_raises_clearly_when_outside_backend_root(monkeypatch, tmp_path):
    """
    When HOST_DATA_DIR IS set (DooD mode) but the worktree path doesn't fall
    under the configured backend-container data root, translation must fail
    loudly rather than silently handing the host daemon a container-only
    path it can't resolve (or, worse, a coincidentally-valid but wrong one).
    """
    from backend.config import settings

    monkeypatch.setattr(settings, "storage_path", "data")
    monkeypatch.setattr(settings, "backend_container_data_dir", "")
    monkeypatch.setattr(settings, "host_data_dir", "/home/dev/gitonboard/data")
    runner = DockerVerificationRunner()

    outside_path = tmp_path / "not_under_storage"
    with pytest.raises(DockerVerificationError):
        runner._translate_to_host_path(outside_path)


def test_translate_to_host_path_uses_explicit_backend_container_data_dir(monkeypatch, tmp_path):
    """BACKEND_CONTAINER_DATA_DIR, when set, takes precedence over inferring
    the backend-container data root from storage_path."""
    from backend.config import settings

    backend_root = tmp_path / "app_data"
    (backend_root / "worktrees").mkdir(parents=True)
    monkeypatch.setattr(settings, "backend_container_data_dir", str(backend_root))
    monkeypatch.setattr(settings, "host_data_dir", "/home/dev/gitonboard/data")
    runner = DockerVerificationRunner()

    container_path = backend_root / "worktrees" / "repo_task1"
    result = runner._translate_to_host_path(container_path)
    assert result == "/home/dev/gitonboard/data/worktrees/repo_task1"


# ──────────────────────────────────────────────────────────────────────────────
# is_available() / run() failure handling (mocked docker client, no daemon required)
# ──────────────────────────────────────────────────────────────────────────────

def test_is_available_false_when_daemon_unreachable():
    runner = DockerVerificationRunner()
    with patch.object(runner, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("daemon down")
        mock_get_client.return_value = mock_client
        assert runner.is_available() is False


def test_run_raises_docker_verification_error_on_container_failure(tmp_path):
    runner = DockerVerificationRunner()
    with patch.object(runner, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.containers.run.side_effect = RuntimeError("image not found")
        mock_get_client.return_value = mock_client
        with pytest.raises(DockerVerificationError):
            runner.run(tmp_path, ["echo hi"], timeout_sec=5)


def test_run_kills_and_reports_timeout(tmp_path):
    runner = DockerVerificationRunner()
    mock_container = MagicMock()
    mock_container.wait.side_effect = TimeoutError("exceeded")
    mock_container.logs.return_value = b"partial output"

    with patch.object(runner, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_get_client.return_value = mock_client

        exit_code, stdout, stderr = runner.run(tmp_path, ["sleep 999"], timeout_sec=1)

    assert exit_code == 124
    assert "timed out" in stderr
    mock_container.kill.assert_called_once()
    mock_container.remove.assert_called_once_with(force=True)


def test_run_empty_commands_is_noop(tmp_path):
    runner = DockerVerificationRunner()
    exit_code, stdout, stderr = runner.run(tmp_path, [], timeout_sec=5)
    assert (exit_code, stdout, stderr) == (0, "", "")


def test_run_uses_configurable_verification_container_workdir(monkeypatch, tmp_path):
    """VERIFICATION_CONTAINER_WORKDIR must not be hard-coded — the bind mount
    target and working_dir passed to Docker should follow the setting."""
    from backend.config import settings

    monkeypatch.setattr(settings, "verification_container_workdir", "/custom-mount")
    runner = DockerVerificationRunner()
    mock_container = MagicMock()
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b"ok"

    with patch.object(runner, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_get_client.return_value = mock_client

        runner.run(tmp_path, ["echo hi"], timeout_sec=5)

    _, call_kwargs = mock_client.containers.run.call_args
    assert call_kwargs["working_dir"] == "/custom-mount"
    assert list(call_kwargs["volumes"].values())[0]["bind"] == "/custom-mount"


# ──────────────────────────────────────────────────────────────────────────────
# Real container smoke test — only runs when a local Docker daemon is reachable.
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker daemon not available in this environment")
def test_run_executes_trivial_command_in_real_container(tmp_path):
    runner = DockerVerificationRunner()
    exit_code, stdout, stderr = runner.run(tmp_path, ["echo hello-from-container"], timeout_sec=30)
    assert exit_code == 0
    assert "hello-from-container" in stdout


@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker daemon not available in this environment")
def test_run_enforces_timeout_in_real_container(tmp_path):
    runner = DockerVerificationRunner()
    exit_code, stdout, stderr = runner.run(tmp_path, ["sleep 30"], timeout_sec=2)
    assert exit_code == 124
    assert "timed out" in stderr


# ──────────────────────────────────────────────────────────────────────────────
# DynamicVerifier falls back to host subprocess when Docker is unavailable
# ──────────────────────────────────────────────────────────────────────────────

def test_dynamic_verifier_falls_back_to_host_when_docker_unavailable(tmp_path, monkeypatch):
    from backend.config import settings
    from backend.verification.dynamic_verifier import DynamicVerifier

    monkeypatch.setattr(settings, "verification_use_docker", True)

    verifier = DynamicVerifier()
    with patch.object(verifier._docker_runner, "is_available", return_value=False):
        # No python/node project files in tmp_path, so verify() short-circuits
        # before ever needing to exec anything — this just proves is_available()
        # is consulted and the "host" sandbox_mode is recorded rather than raising.
        result = verifier.verify(tmp_path, modified_files=[])

    assert result.details.get("sandbox_mode") == "host"
