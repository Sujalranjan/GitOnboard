"""
StaticVerifier: Performs static AST, symbol existence, import manifest, and architectural verification.
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .schemas import Defect, DefectCategory, DefectSeverity, ExecutionState, VerificationResult

logger = logging.getLogger(__name__)

# Standard Python library modules to ignore during package manifest checks
PYTHON_STDLIB: Set[str] = {
    "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
    "copy", "dataclasses", "datetime", "decimal", "enum", "functools", "glob",
    "hashlib", "http", "importlib", "inspect", "io", "itertools", "json",
    "logging", "math", "multiprocessing", "os", "pathlib", "pickle", "random",
    "re", "shutil", "signal", "socket", "sqlite3", "ssl", "string", "subprocess",
    "sys", "tempfile", "threading", "time", "traceback", "typing", "unittest",
    "urllib", "uuid", "weakref", "xml", "zipfile", "__future__", "pydantic"
}

# Standard JS/TS built-in or framework modules to ignore
JS_STDLIB: Set[str] = {
    "react", "react-dom", "next", "fs", "path", "http", "https", "util", "crypto",
    "events", "stream", "os", "child_process", "url", "lucide-react", "d3-force", "dagre"
}


class StaticVerifier:
    """
    Static Verification Vector:
    Uses AST analysis and package manifest checks to verify that:
    1. All newly introduced external imports exist in pyproject.toml / requirements.txt / package.json.
    2. All referenced local files and symbols exist in the repository tree.
    """

    def verify(
        self,
        worktree_path: Path,
        modified_files: List[str],
        git_diff: str = "",
    ) -> VerificationResult:
        start_time = time.time()
        wt_path = Path(worktree_path).resolve()
        defects: List[Defect] = []

        if not wt_path.exists():
            return VerificationResult(
                vector_name="static",
                status="FAIL",
                passed=False,
                defects=[
                    Defect(
                        category=DefectCategory.STATIC_SYMBOL_MISSING.value,
                        file_path="",
                        description=f"Worktree directory does not exist: {wt_path}",
                        severity=DefectSeverity.CRITICAL.value,
                    )
                ],
            )

        # 1. Load manifest dependencies
        declared_py_deps = self._get_declared_python_deps(wt_path)
        declared_js_deps = self._get_declared_js_deps(wt_path)

        # 2. Inspect modified files
        target_files = modified_files if modified_files else self._find_all_code_files(wt_path)

        for rel_file in target_files:
            file_full = wt_path / rel_file
            if not file_full.exists() or not file_full.is_file():
                continue

            if rel_file.endswith(".py"):
                self._verify_python_file(
                    wt_path, rel_file, file_full, declared_py_deps, defects
                )
            elif rel_file.endswith((".ts", ".tsx", ".js", ".jsx")):
                self._verify_js_file(
                    wt_path, rel_file, file_full, declared_js_deps, defects
                )

        evidence_manifest: List[Dict[str, Any]] = [
            {
                "type": "static_files_inspected",
                "count": len(target_files),
                "files": target_files[:20],
            },
            {
                "type": "manifest_dependencies_declared",
                "python_deps_count": len(declared_py_deps),
                "js_deps_count": len(declared_js_deps),
            }
        ]

        elapsed_ms = (time.time() - start_time) * 1000
        has_evidence = len(target_files) > 0
        passed = (len(defects) == 0) and has_evidence
        
        if not has_evidence and len(defects) == 0:
            exec_state = ExecutionState.UNVERIFIED.value
        elif passed:
            exec_state = ExecutionState.PASS.value
        else:
            exec_state = ExecutionState.FAIL.value

        status = exec_state

        logger.info(f"StaticVerifier finished: status={status}, defects={len(defects)}, time={elapsed_ms:.1f}ms")
        return VerificationResult(
            vector_name="static",
            status=status,
            passed=passed,
            execution_state=exec_state,
            defects=defects,
            evidence_manifest=evidence_manifest,
            details={
                "target_files_count": len(target_files),
                "declared_python_deps": list(declared_py_deps),
                "declared_js_deps": list(declared_js_deps),
                "evidence_count": len(evidence_manifest),
            },
            execution_time_ms=elapsed_ms,
        )

    def _get_declared_python_deps(self, wt_path: Path) -> Set[str]:
        deps: Set[str] = set()

        # pyproject.toml
        pyproject = wt_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(encoding="utf-8", errors="ignore")
                for match in re.finditer(r'["\']([a-zA-Z0-9_\-]+)(?:[<>=!~].*)?["\']', content):
                    pkg = match.group(1).lower().replace("-", "_")
                    deps.add(pkg)
            except Exception as e:
                logger.warning(f"Error parsing pyproject.toml: {e}")

        # requirements.txt
        reqs = wt_path / "requirements.txt"
        if reqs.exists():
            try:
                content = reqs.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pkg = re.split(r"[<>=!~;\s]", line)[0].lower().replace("-", "_")
                        if pkg:
                            deps.add(pkg)
            except Exception as e:
                logger.warning(f"Error parsing requirements.txt: {e}")

        return deps

    def _get_declared_js_deps(self, wt_path: Path) -> Set[str]:
        deps: Set[str] = set()
        pkg_json = wt_path / "package.json"
        if not pkg_json.exists():
            pkg_json = wt_path / "frontend" / "package.json"

        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                for section in ["dependencies", "devDependencies", "peerDependencies"]:
                    if section in data and isinstance(data[section], dict):
                        for pkg in data[section].keys():
                            deps.add(pkg.lower())
            except Exception as e:
                logger.warning(f"Error parsing package.json: {e}")

        return deps

    def _verify_python_file(
        self,
        wt_path: Path,
        rel_file: str,
        file_full: Path,
        declared_deps: Set[str],
        defects: List[Defect],
    ) -> None:
        try:
            source = file_full.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(rel_file))
        except SyntaxError as err:
            defects.append(
                Defect(
                    category=DefectCategory.STATIC_SYMBOL_MISSING.value,
                    file_path=rel_file,
                    line_number=err.lineno,
                    description=f"Python syntax error: {err.msg}",
                    severity=DefectSeverity.CRITICAL.value,
                )
            )
            return
        except Exception:
            return

        for node in ast.walk(tree):
            # Check Import
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_base = alias.name.split(".")[0]
                    self._check_python_module(
                        wt_path, rel_file, node.lineno, mod_base, declared_deps, defects
                    )
            # Check ImportFrom
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    # Relative import, check target file existence
                    self._check_python_relative_import(wt_path, rel_file, node, defects)
                elif node.module:
                    mod_base = node.module.split(".")[0]
                    self._check_python_module(
                        wt_path, rel_file, node.lineno, mod_base, declared_deps, defects
                    )

    def _check_python_module(
        self,
        wt_path: Path,
        rel_file: str,
        line_no: int,
        mod_base: str,
        declared_deps: Set[str],
        defects: List[Defect],
    ) -> None:
        norm_mod = mod_base.lower().replace("-", "_")

        # Ignore stdlib or local app modules
        if norm_mod in PYTHON_STDLIB or norm_mod in ("backend", "src", "app", "tests"):
            return

        # Check local folder module
        local_dir = wt_path / mod_base
        local_py = wt_path / f"{mod_base}.py"
        if local_dir.exists() or local_py.exists():
            return

        # Check declared dependencies
        if declared_deps and norm_mod not in declared_deps:
            # Check if package is mapped (e.g. yaml -> pyyaml)
            mapped_ok = any(norm_mod in dep or dep in norm_mod for dep in declared_deps)
            if not mapped_ok:
                defects.append(
                    Defect(
                        category=DefectCategory.STATIC_IMPORT_MISSING.value,
                        file_path=rel_file,
                        line_number=line_no,
                        description=f"Imported Python module '{mod_base}' is not declared in pyproject.toml or requirements.txt.",
                        severity=DefectSeverity.HIGH.value,
                        symbol=mod_base,
                    )
                )

    def _check_python_relative_import(
        self,
        wt_path: Path,
        rel_file: str,
        node: ast.ImportFrom,
        defects: List[Defect],
    ) -> None:
        dir_parts = Path(rel_file).parent.parts
        level = node.level or 1
        if len(dir_parts) >= level - 1:
            base_parts = dir_parts[: len(dir_parts) - level + 1]
            mod_sub = node.module.replace(".", "/") if node.module else ""
            target_py = wt_path.joinpath(*base_parts, f"{mod_sub}.py")
            target_dir = wt_path.joinpath(*base_parts, mod_sub)
            if not target_py.exists() and not (target_dir / "__init__.py").exists():
                defects.append(
                    Defect(
                        category=DefectCategory.STATIC_SYMBOL_MISSING.value,
                        file_path=rel_file,
                        line_number=node.lineno,
                        description=f"Relative import target '{node.module}' does not exist in repository.",
                        severity=DefectSeverity.HIGH.value,
                        symbol=node.module,
                    )
                )

    def _verify_js_file(
        self,
        wt_path: Path,
        rel_file: str,
        file_full: Path,
        declared_js_deps: Set[str],
        defects: List[Defect],
    ) -> None:
        try:
            source = file_full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        lines = source.splitlines()

        # Regex to match JS/TS import statements
        import_regex = re.compile(
            r'import\s+(?:[\w\s{},*]+from\s+)?["\']([^"\']+)["\']'
        )

        for line_idx, line in enumerate(lines, start=1):
            match = import_regex.search(line)
            if not match:
                continue

            import_path = match.group(1)

            # Local relative import
            if import_path.startswith((".", "/")):
                self._check_js_relative_import(
                    wt_path, rel_file, line_idx, import_path, defects
                )
            # Alias import @/
            elif import_path.startswith("@/"):
                alias_rel = import_path[2:]
                target_1 = wt_path / alias_rel
                target_2 = wt_path / "frontend" / alias_rel
                target_src = wt_path / "frontend" / "src" / alias_rel
                exists = any(
                    t.exists() or (wt_path / f"{alias_rel}.tsx").exists() or (wt_path / f"{alias_rel}.ts").exists()
                    for t in [target_1, target_2, target_src]
                )
                if not exists:
                    defects.append(
                        Defect(
                            category=DefectCategory.STATIC_SYMBOL_MISSING.value,
                            file_path=rel_file,
                            line_number=line_idx,
                            description=f"Aliased import '{import_path}' could not be resolved to an existing file.",
                            severity=DefectSeverity.MEDIUM.value,
                            symbol=import_path,
                        )
                    )
            # External npm module
            else:
                pkg_name = import_path.split("/")[0]
                if import_path.startswith("@"):
                    parts = import_path.split("/")
                    pkg_name = f"{parts[0]}/{parts[1]}" if len(parts) > 1 else import_path

                if (
                    pkg_name.lower() not in JS_STDLIB
                    and declared_js_deps
                    and pkg_name.lower() not in declared_js_deps
                ):
                    defects.append(
                        Defect(
                            category=DefectCategory.STATIC_IMPORT_MISSING.value,
                            file_path=rel_file,
                            line_number=line_idx,
                            description=f"Imported npm package '{pkg_name}' is not declared in package.json.",
                            severity=DefectSeverity.HIGH.value,
                            symbol=pkg_name,
                        )
                    )

    def _check_js_relative_import(
        self,
        wt_path: Path,
        rel_file: str,
        line_no: int,
        import_path: str,
        defects: List[Defect],
    ) -> None:
        file_dir = (wt_path / rel_file).parent
        resolved = (file_dir / import_path).resolve()

        extensions = ["", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js"]
        exists = any(Path(f"{resolved}{ext}").exists() for ext in extensions)

        if not exists:
            defects.append(
                Defect(
                    category=DefectCategory.STATIC_SYMBOL_MISSING.value,
                    file_path=rel_file,
                    line_number=line_no,
                    description=f"Relative import path '{import_path}' cannot be resolved to an existing file.",
                    severity=DefectSeverity.HIGH.value,
                    symbol=import_path,
                )
            )

    def _find_all_code_files(self, wt_path: Path) -> List[str]:
        results = []
        for root, dirs, files in os.walk(wt_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "__pycache__", "dist", ".next")]
            for file in files:
                if file.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                    full = Path(root) / file
                    results.append(str(full.relative_to(wt_path)).replace("\\", "/"))
        return results
