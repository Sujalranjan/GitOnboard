"""
Automated unit tests for GitManager, Verification Mesh (Static, Dynamic, Contract verifiers), and Judge.
"""
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.services.git_manager import GitManager
from backend.verification import (
    ContractVerifier,
    Defect,
    DefectCategory,
    DynamicVerifier,
    Judge,
    StaticVerifier,
    VerificationReport,
    VerificationResult,
)


def test_git_manager_init_and_worktree(tmp_path):
    git_mgr = GitManager(base_worktree_dir=tmp_path / "worktrees")
    assert git_mgr.base_dir.exists()


def test_static_verifier_valid_python(tmp_path):
    # Create sample Python project structure
    py_file = tmp_path / "app.py"
    py_file.write_text("import os\nimport sys\n\ndef main():\n    return 42\n", encoding="utf-8")

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "test_app"\ndependencies = []\n', encoding="utf-8")

    verifier = StaticVerifier()
    res = verifier.verify(tmp_path, modified_files=["app.py"])

    assert res.vector_name == "static"
    assert res.passed is True
    assert len(res.defects) == 0


def test_static_verifier_missing_import(tmp_path):
    py_file = tmp_path / "service.py"
    py_file.write_text("import non_existent_pkg_xyz_999\n", encoding="utf-8")

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "test_app"\ndependencies = []\n', encoding="utf-8")

    verifier = StaticVerifier()
    res = verifier.verify(tmp_path, modified_files=["service.py"])

    assert res.passed is False
    assert len(res.defects) > 0
    assert any(d.category == DefectCategory.STATIC_IMPORT_MISSING.value for d in res.defects)


def test_contract_verifier_omission():
    contract = {
        "affected_components": [
            {"file": "src/pages/api/todos.ts", "symbol": "handler"},
            {"file": "src/components/TodoItem.tsx", "symbol": "TodoItem"},
        ],
        "tests_required": ["Test POST /api/todos returns 201"],
    }

    # Only modified 1 of the 2 required files and 0 tests
    modified_files = ["src/pages/api/todos.ts"]
    git_diff = "--- a/src/pages/api/todos.ts\n+++ b/src/pages/api/todos.ts\n+ export default function handler() {}"

    verifier = ContractVerifier()
    res = verifier.verify(contract, modified_files, git_diff)

    assert res.passed is False
    assert len(res.defects) >= 2
    assert any(d.category == DefectCategory.CONTRACT_OMISSION.value for d in res.defects)


def test_judge_aggregation():
    judge = Judge()

    static_pass = VerificationResult(vector_name="static", status="PASS", passed=True, defects=[])
    dynamic_pass = VerificationResult(vector_name="dynamic", status="PASS", passed=True, defects=[])
    contract_pass = VerificationResult(vector_name="contract", status="PASS", passed=True, defects=[])

    report_pass = judge.aggregate("run_001", static_pass, dynamic_pass, contract_pass)
    assert report_pass.passed is True
    assert report_pass.status == "PASS"

    # Test failure aggregation
    contract_fail = VerificationResult(
        vector_name="contract",
        status="FAIL",
        passed=False,
        defects=[
            Defect(
                category=DefectCategory.CONTRACT_OMISSION.value,
                file_path="src/todo.ts",
                description="Omitted required component",
            )
        ],
    )

    report_fail = judge.aggregate("run_002", static_pass, dynamic_pass, contract_fail)
    assert report_fail.passed is False
    assert report_fail.status == "FAIL"
    assert len(report_fail.defects) == 1
