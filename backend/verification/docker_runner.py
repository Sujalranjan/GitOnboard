"""
DockerVerificationRunner: Executes verification build/test/lint commands inside an
ephemeral, resource-limited Docker container instead of on the host, so that
LLM-generated code from arbitrary target repositories never runs directly on the
host machine during the dynamic-verification step.

Scope: verification execution ONLY. The agent's code-writing step and the
human-facing SandboxManager terminal both remain plain host/worktree execution,
per the frozen agent.md / implementation-contract.md design.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple

from backend.config import settings
from backend.utils.repo_paths import to_posix

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 120
MEM_LIMIT = "1g"
NANO_CPUS = 1_000_000_000  # 1 CPU
PIDS_LIMIT = 256

# Minimal, safe environment for the verification container. Host secrets and
# host-specific variables (see backend.services.env_sanitizer) are never passed through.
CONTAINER_ENV = {"CI": "true", "PYTHONUNBUFFERED": "1"}


class DockerVerificationError(Exception):
    """Raised when the Docker daemon is unreachable or the container fails to run."""
    pass


class DockerVerificationRunner:
    """
    Runs shell commands inside a fresh, non-privileged, resource-capped container
    with the worktree bind-mounted read-write at /workspace. Always removes the
    container afterward.
    """

    def __init__(self, image: Optional[str] = None):
        self.image = image or settings.verification_docker_image
        self._client = None

    def _get_client(self):
        if self._client is None:
            import docker  # local import: keeps docker-py optional until actually needed

            self._client = docker.from_env()
        return self._client

    def is_available(self) -> bool:
        try:
            self._get_client().ping()
            return True
        except Exception as err:
            logger.warning(f"DockerVerificationRunner: Docker daemon unavailable: {err}")
            return False

    def _translate_to_host_path(self, container_path: Path) -> str:
        """
        When the backend itself runs inside a container (docker-compose.yml
        mounts /var/run/docker.sock into it — Docker-outside-of-Docker), a bind
        mount handed to the HOST Docker daemon must be a path that exists on the
        HOST filesystem, not inside the backend container. `settings.host_data_dir`
        (HOST_DATA_DIR, set by docker-compose.yml from `${PWD}/data`) gives the
        host-side equivalent of `settings.backend_container_data_dir`
        (BACKEND_CONTAINER_DATA_DIR, e.g. /app/data) — translate accordingly.

        No-op when HOST_DATA_DIR isn't set (i.e. the backend is running
        directly on the host, where container paths already ARE host paths).
        Raises DockerVerificationError — rather than silently guessing — if
        HOST_DATA_DIR *is* set but `container_path` doesn't fall under the
        configured backend-container data root, since mounting the wrong
        path (or a container-only path the host daemon can't see at all)
        fails opaquely or, worse, mounts an unintended host directory.
        """
        if not settings.host_data_dir:
            return str(container_path)

        backend_root = Path(
            settings.backend_container_data_dir or settings.storage_path
        ).resolve()
        try:
            rel = container_path.resolve().relative_to(backend_root)
        except ValueError:
            raise DockerVerificationError(
                f"Cannot translate worktree path '{container_path}' to a host path: it "
                f"is not under the configured backend-container data root "
                f"'{backend_root}'. Set BACKEND_CONTAINER_DATA_DIR to the path where "
                f"./data is mounted inside the backend container (e.g. /app/data), "
                f"matching the volume mount in docker-compose.yml."
            )

        # HOST_DATA_DIR is a literal host path string (may be Windows-style);
        # join with plain string formatting rather than PosixPath, which would
        # otherwise treat backslashes as literal filename characters.
        host_data_dir = settings.host_data_dir.rstrip("/\\")
        sep = "\\" if "\\" in host_data_dir else "/"
        return host_data_dir + sep + to_posix(str(rel)).replace("/", sep)

    def _warn_if_likely_misconfigured_dood(self) -> None:
        """
        Non-fatal diagnostic for the most common DooD misconfiguration: the
        backend is itself running inside a container (/.dockerenv present)
        but HOST_DATA_DIR was never set, so `_translate_to_host_path` will
        treat container-only paths as if they were host paths — the sibling
        verification container then can't find the mounted worktree at all.
        """
        if not settings.host_data_dir and Path("/.dockerenv").exists():
            logger.warning(
                "DockerVerificationRunner: backend appears to be running inside a "
                "container (/.dockerenv present) but HOST_DATA_DIR is not set — "
                "verification container bind mounts will likely fail to resolve on "
                "the host Docker daemon. Set HOST_DATA_DIR (see docker-compose.yml)."
            )

    def run(
        self,
        worktree_path: Path,
        commands: List[str],
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> Tuple[int, str, str]:
        """
        Runs `commands` sequentially (stopping at the first failure) inside a
        fresh container. Returns (exit_code, stdout, stderr). stdout/stderr are
        combined since Docker's blocking log stream interleaves them by default.
        """
        if not commands:
            return 0, "", ""

        self._warn_if_likely_misconfigured_dood()

        client = self._get_client()
        wt_path = Path(worktree_path).resolve()
        host_wt_path = self._translate_to_host_path(wt_path)
        shell_script = " && ".join(commands)

        container = None
        try:
            container = client.containers.run(
                self.image,
                command=["/bin/bash", "-lc", shell_script],
                working_dir=settings.verification_container_workdir,
                volumes={host_wt_path: {"bind": settings.verification_container_workdir, "mode": "rw"}},
                environment=CONTAINER_ENV,
                mem_limit=MEM_LIMIT,
                nano_cpus=NANO_CPUS,
                pids_limit=PIDS_LIMIT,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                detach=True,
            )

            try:
                result = container.wait(timeout=timeout_sec)
                exit_code = result.get("StatusCode", 1)
            except Exception as wait_err:
                logger.warning(
                    f"DockerVerificationRunner: container exceeded {timeout_sec}s, killing: {wait_err}"
                )
                try:
                    container.kill()
                except Exception:
                    pass
                logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                return 124, logs, f"Verification container timed out after {timeout_sec}s"

            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            return exit_code, logs, ""
        except Exception as err:
            logger.error(f"DockerVerificationRunner: container execution failed: {err}")
            raise DockerVerificationError(str(err)) from err
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception as cleanup_err:
                    logger.debug(f"DockerVerificationRunner: cleanup error: {cleanup_err}")
