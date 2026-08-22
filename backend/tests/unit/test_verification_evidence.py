"""
Unit tests for VerificationEvidenceCollector in Phase 7.
"""
from backend.agent.verification.contracts import (
    DefectCategory,
    DefectSeverity,
    VerificationCheck,
    VerificationStatus,
    VerificationType,
)
from backend.agent.verification.evidence import VerificationEvidenceCollector
from backend.verification.schemas import Defect as LegacyDefect, VerificationResult as LegacyVerificationResult


def test_evidence_collector_truncation():
    collector = VerificationEvidenceCollector(max_summary_chars=100)
    long_text = "A" * 500
    truncated = collector.truncate_text(long_text)
    assert len(truncated) < 500
    assert "[TRUNCATED" in truncated


def test_evidence_collector_normalizes_legacy_defect():
    collector = VerificationEvidenceCollector()
    legacy = LegacyDefect(
        category="STATIC_SYMBOL_MISSING",
        file_path="main.py",
        line_number=20,
        description="Symbol 'run_server' is missing",
        severity="HIGH",
    )
    defect = collector.normalize_defect(legacy, evidence_id="ev-100", default_command="verify_static")
    assert defect.type == "STATIC_SYMBOL_MISSING"
    assert defect.file == "main.py"
    assert defect.line == 20
    assert defect.message == "Symbol 'run_server' is missing"
    assert defect.evidence_id == "ev-100"


def test_evidence_collector_builds_evidence_from_passing_result():
    collector = VerificationEvidenceCollector()
    check = VerificationCheck(
        type=VerificationType.STATIC,
        name="Static AST Check",
        command="static_verify",
    )
    legacy_res = LegacyVerificationResult(
        vector_name="static",
        status="PASS",
        passed=True,
        execution_state="PASS",
        defects=[],
        details={"output": "All AST checks passed", "exit_code": 0},
        execution_time_ms=120.0,
    )
    evidence = collector.build_evidence_from_verifier_result(
        verification_id="v-1",
        check=check,
        verifier_result=legacy_res,
    )
    assert evidence.verification_id == "v-1"
    assert evidence.check_id == check.check_id
    assert evidence.status == VerificationStatus.PASSED
    assert evidence.exit_code == 0
    assert evidence.stdout_summary == "All AST checks passed"
    assert len(evidence.defects) == 0


def test_evidence_collector_builds_evidence_from_failing_result():
    collector = VerificationEvidenceCollector()
    check = VerificationCheck(
        type=VerificationType.DYNAMIC,
        name="Dynamic Test Execution",
        command="pytest",
    )
    legacy_defect = LegacyDefect(
        category="DYNAMIC_TEST_FAILURE",
        file_path="tests/test_auth.py",
        description="AssertionError: 401 != 200",
        severity="HIGH",
    )
    legacy_res = LegacyVerificationResult(
        vector_name="dynamic",
        status="FAIL",
        passed=False,
        execution_state="FAIL",
        defects=[legacy_defect],
        details={"error": "1 failed in 0.5s", "exit_code": 1},
        execution_time_ms=500.0,
    )
    evidence = collector.build_evidence_from_verifier_result(
        verification_id="v-2",
        check=check,
        verifier_result=legacy_res,
    )
    assert evidence.status == VerificationStatus.FAILED
    assert evidence.exit_code == 1
    assert len(evidence.defects) == 1
    assert evidence.defects[0].type == "DYNAMIC_TEST_FAILURE"
    assert evidence.defects[0].file == "tests/test_auth.py"
