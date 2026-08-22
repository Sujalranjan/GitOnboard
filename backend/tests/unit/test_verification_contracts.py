"""
Unit tests for Phase 7 verification contracts and models.
"""
from backend.agent.verification.contracts import (
    DefectCategory,
    DefectSeverity,
    VerificationCheck,
    VerificationDefect,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
    VerificationStrategy,
    VerificationType,
)


def test_verification_enums():
    assert VerificationType.STATIC.value == "STATIC"
    assert VerificationType.DYNAMIC.value == "DYNAMIC"
    assert VerificationType.CONTRACT.value == "CONTRACT"
    assert VerificationType.FULL.value == "FULL"

    assert VerificationStatus.PASSED.value == "PASSED"
    assert VerificationStatus.FAILED.value == "FAILED"
    assert VerificationStatus.ERROR.value == "ERROR"
    assert VerificationStatus.CANCELLED.value == "CANCELLED"


def test_verification_defect_model():
    defect = VerificationDefect(
        type=DefectCategory.STATIC_IMPORT_MISSING.value,
        severity=DefectSeverity.HIGH.value,
        message="Cannot import module 'services.auth'",
        file="routes/login.py",
        line=12,
        command="pytest",
    )
    assert defect.type == "STATIC_IMPORT_MISSING"
    assert defect.severity == "HIGH"
    assert defect.file == "routes/login.py"
    assert defect.line == 12


def test_verification_check_model():
    check = VerificationCheck(
        type=VerificationType.STATIC,
        name="Static AST verification",
        required=True,
        timeout=30.0,
    )
    assert check.type == VerificationType.STATIC
    assert check.required is True
    assert check.timeout == 30.0


def test_verification_evidence_model():
    ev = VerificationEvidence(
        verification_id="verif-123",
        check_id="check-456",
        status=VerificationStatus.PASSED,
        command="pytest tests/unit",
        exit_code=0,
        stdout_summary="10 passed in 1.2s",
        duration_ms=1200.0,
    )
    assert ev.verification_id == "verif-123"
    assert ev.status == VerificationStatus.PASSED
    assert ev.exit_code == 0
    assert ev.duration_ms == 1200.0


def test_verification_result_model():
    res = VerificationResult(
        verification_id="verif-1",
        task_id="task-1",
        status=VerificationStatus.PASSED,
        passed=True,
        passed_checks=["Static Check", "Dynamic Check"],
        failed_checks=[],
        duration_ms=450.0,
        summary="All checks passed",
    )
    assert res.task_id == "task-1"
    assert res.passed is True
    assert len(res.passed_checks) == 2
