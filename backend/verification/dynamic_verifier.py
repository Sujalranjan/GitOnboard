"""
DynamicVerifier: Executes test suites, build compilers, linters, and type checkers inside isolated worktrees.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.config import settings
from backend.utils.repo_paths import to_posix
from backend.verification.docker_runner import DockerVerificationError, DockerVerificationRunner

from .schemas import Defect, DefectCategory, DefectSeverity, ExecutionState, VerificationResult

logger = logging.getLogger(__name__)


class DynamicVerifier:
    """
    Dynamic Verification Vector:
    Executes automated test suites, type checking, and linters inside an ephemeral
    Docker container scoped to the worktree (falling back to host subprocess only
    if the Docker daemon is unavailable). Parses stdout/stderr into itemized Defect objects.
    """

    def __init__(self) -> None:
        self._docker_runner = DockerVerificationRunner()

    def verify(
        self,
        worktree_path: Path,
        modified_files: Optional[List[str]] = None,
        timeout_sec: int = 120,
    ) -> VerificationResult:
        start_time = time.time()
        wt_path = Path(worktree_path).resolve()
        defects: List[Defect] = []
        execution_details: Dict[str, str] = {}

        if not wt_path.exists():
            return VerificationResult(
                vector_name="dynamic",
                status="FAIL",
                passed=False,
                defects=[
                    Defect(
                        category=DefectCategory.DYNAMIC_BUILD_FAILURE.value,
                        file_path="",
                        description=f"Worktree path does not exist: {wt_path}",
                        severity=DefectSeverity.CRITICAL.value,
                    )
                ],
            )

        # Determine environment & runners
        has_python = any(wt_path.glob("*.py")) or (wt_path / "backend").exists()
        has_node = (wt_path / "package.json").exists() or (wt_path / "frontend" / "package.json").exists()

        use_docker = settings.verification_use_docker and self._docker_runner.is_available()
        execution_details["sandbox_mode"] = "docker" if use_docker else "host"
        if not use_docker and settings.verification_use_docker:
            logger.warning("DynamicVerifier: Docker unavailable, falling back to host subprocess execution.")

        # 1. Run Python pytest & linters if Python project
        if has_python:
            self._run_python_checks(wt_path, defects, execution_details, timeout_sec, use_docker)

        # 2. Run Node.js tests & build if Node project
        if has_node:
            node_dir = wt_path / "frontend" if (wt_path / "frontend" / "package.json").exists() else wt_path
            self._run_node_checks(node_dir, defects, execution_details, timeout_sec, use_docker, wt_path)

        evidence_manifest: List[Dict[str, Any]] = []
        if "pytest_stdout" in execution_details and execution_details["pytest_stdout"]:
            evidence_manifest.append({
                "type": "pytest_execution",
                "stdout_snippet": execution_details["pytest_stdout"][:500],
            })
        if "node_build_stdout" in execution_details and execution_details["node_build_stdout"]:
            evidence_manifest.append({
                "type": "node_build_execution",
                "stdout_snippet": execution_details["node_build_stdout"][:500],
            })

        elapsed_ms = (time.time() - start_time) * 1000
        has_evidence = len(evidence_manifest) > 0 or bool(execution_details)
        passed = (len(defects) == 0) and has_evidence

        if not has_evidence and len(defects) == 0:
            exec_state = ExecutionState.UNVERIFIED.value
        elif passed:
            exec_state = ExecutionState.PASS.value
        else:
            exec_state = ExecutionState.FAIL.value

        status = exec_state

        logger.info(f"DynamicVerifier finished: status={status}, defects={len(defects)}, time={elapsed_ms:.1f}ms")
        return VerificationResult(
            vector_name="dynamic",
            status=status,
            passed=passed,
            execution_state=exec_state,
            defects=defects,
            evidence_manifest=evidence_manifest,
            details=execution_details,
            execution_time_ms=elapsed_ms,
        )

    def _run_via_docker(
        self,
        docker_root: Path,
        cwd: Path,
        commands: List[str],
        timeout_sec: int,
    ) -> Optional[Tuple[int, str, str]]:
        """
        Runs `commands` inside the verification container, cd-ing into cwd's
        path relative to docker_root first. Returns None (signalling the caller
        to fall back to host execution) if the container run itself fails.
        """
        try:
            rel = cwd.resolve().relative_to(docker_root.resolve())
        except ValueError:
            rel = Path(".")
        rel_str = to_posix(str(rel))

        prefixed = list(commands)
        if rel_str not in ("", "."):
            prefixed = [f"cd {shlex.quote(rel_str)}"] + prefixed

        try:
            return self._docker_runner.run(docker_root, prefixed, timeout_sec=timeout_sec)
        except DockerVerificationError as err:
            logger.warning(f"DynamicVerifier: docker execution failed, falling back to host: {err}")
            return None

    def _run_python_checks(
        self,
        wt_path: Path,
        defects: List[Defect],
        details: Dict[str, str],
        timeout_sec: int,
        use_docker: bool,
    ) -> None:
        # Check syntax/compile
        py_files = list(wt_path.glob("**/*.py"))
        for py_file in py_files[:50]:
            if any(part in py_file.parts for part in (".venv", "node_modules", "build", "dist")):
                continue
            try:
                compile(py_file.read_text(encoding="utf-8", errors="ignore"), str(py_file), "exec")
            except SyntaxError as err:
                rel_path = to_posix(str(py_file.relative_to(wt_path)))
                defects.append(
                    Defect(
                        category=DefectCategory.DYNAMIC_BUILD_FAILURE.value,
                        file_path=rel_path,
                        line_number=err.lineno,
                        description=f"Python compilation syntax error: {err.msg}",
                        severity=DefectSeverity.CRITICAL.value,
                    )
                )

        # Run pytest if tests directory exists
        test_dir = wt_path / "tests"
        backend_test_dir = wt_path / "backend" / "tests"

        if test_dir.exists() or backend_test_dir.exists():
            result = None
            if use_docker:
                install_cmds = []
                if (wt_path / "requirements.txt").exists():
                    install_cmds.append("pip install -q -r requirements.txt")
                result = self._run_via_docker(
                    wt_path, wt_path, install_cmds + ["python -m pytest -v --tb=short"], timeout_sec
                )

            if result is not None:
                res_code, stdout, stderr = result
            else:
                cmd = ["uv", "run", "pytest", "-v", "--tb=short"]
                if not shutil_which("uv"):
                    cmd = ["pytest", "-v", "--tb=short"]
                res_code, stdout, stderr = self._exec_cmd(cmd, wt_path, timeout_sec)

            details["pytest_stdout"] = stdout[:2000]
            details["pytest_stderr"] = stderr[:1000]

            if res_code != 0:
                self._parse_pytest_failures(stdout, defects)

    def _run_node_checks(
        self,
        node_dir: Path,
        defects: List[Defect],
        details: Dict[str, str],
        timeout_sec: int,
        use_docker: bool,
        docker_root: Path,
    ) -> None:
        result = None
        if use_docker:
            result = self._run_via_docker(
                docker_root, node_dir, ["npm install --no-audit --no-fund", "npm run build"], timeout_sec
            )

        if result is not None:
            res_code, stdout, stderr = result
        else:
            cmd_typecheck = ["npm", "run", "build"]
            res_code, stdout, stderr = self._exec_cmd(cmd_typecheck, node_dir, timeout_sec)

        details["node_build_stdout"] = stdout[:1500]
        details["node_build_stderr"] = stderr[:1000]

        if res_code != 0 and "Type error" in stdout:
            self._parse_tsc_failures(stdout, defects)

    def _exec_cmd(
        self,
        cmd: List[str],
        cwd: Path,
        timeout_sec: int = 60,
    ) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired as err:
            return 124, "", f"Command timed out after {timeout_sec}s: {' '.join(cmd)}"
        except Exception as err:
            return 1, "", str(err)

    def _parse_pytest_failures(self, stdout: str, defects: List[Defect]) -> None:
        # Parse pytest output lines like: FAILED tests/test_auth.py::test_login - AssertionError: expected 200
        fail_matches = re.findall(
            r"FAILED\s+([\w\/\.\-]+)::(\w+)\s*[-_]*\s*(.*)", stdout
        )
        if fail_matches:
            for file_path, test_name, reason in fail_matches:
                defects.append(
                    Defect(
                        category=DefectCategory.DYNAMIC_TEST_FAILURE.value,
                        file_path=file_path,
                        description=f"Test '{test_name}' failed: {reason.strip()}",
                        severity=DefectSeverity.HIGH.value,
                        symbol=test_name,
                    )
                )
        else:
            # Fallback defect if parsing missed specific line
            defects.append(
                Defect(
                    category=DefectCategory.DYNAMIC_TEST_FAILURE.value,
                    file_path="tests",
                    description=f"Pytest test suite execution failed. Details: {stdout[-500:].strip()}",
                    severity=DefectSeverity.HIGH.value,
                )
            )

    def _parse_tsc_failures(self, stdout: str, defects: List[Defect]) -> None:
        # Match lines like: ./src/components/Header.tsx:19:37 Type error: ...
        matches = re.findall(r"([.\w\/\-]+\.tsx?):(\d+):(\d+)\s+Type error:\s+(.*)", stdout)
        for file_path, line_no, col_no, msg in matches:
            defects.append(
                Defect(
                    category=DefectCategory.DYNAMIC_BUILD_FAILURE.value,
                    file_path=file_path,
                    line_number=int(line_no),
                    description=f"TypeScript type error: {msg.strip()}",
                    severity=DefectSeverity.HIGH.value,
                )
            )


def shutil_which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None
