"""
Unit tests for VerificationResultAggregator in Phase 7.
"""
from backend.agent.verification.contracts import (
    DefectCategory,
    DefectSeverity,
    VerificationCheck,
    VerificationDefect,
    VerificationEvidence,
    VerificationStatus,
    VerificationType,
)
from backend.agent.verification.result import VerificationResultAggregator
from backend.verification.schemas import ExecutionState, VerificationReport, VerificationResult as LegacyVerificationResult


def test_result_aggregator_all_passed():
    aggregator = VerificationResultAggregator()
    check1 = VerificationCheck(type=VerificationType.STATIC, name="Static AST", required=True)
    check2 = VerificationCheck(type=VerificationType.DYNAMIC, name="Dynamic Tests", required=True)

    ev1 = VerificationEvidence(
        verification_id="v-1", check_id=check1.check_id, status=VerificationStatus.PASSED
    )
    ev2 = VerificationEvidence(
        verification_id="v-1", check_id=check2.check_id, status=VerificationStatus.PASSED
    )

    judge_report = VerificationReport(
        run_id="run-1",
        status="PASS",
        passed=True,
        execution_state=ExecutionState.PASS.value,
        static_result=LegacyVerificationResult(vector_name="static", status="PASS", passed=True),
        dynamic_result=LegacyVerificationResult(vector_name="dynamic", status="PASS", passed=True),
        contract_result=LegacyVerificationResult(vector_name="contract", status="PASS", passed=True),
        summary="Judge passed",
    )

    result = aggregator.aggregate(
        task_id="task-1",
        checks=[check1, check2],
        evidence_list=[ev1, ev2],
        judge_report=judge_report,
        duration_ms=250.0,
    )
    assert result.status == VerificationStatus.PASSED
    assert result.passed is True
    assert len(result.passed_checks) == 2
    assert len(result.failed_checks) == 0
    assert len(result.defects) == 0


def test_result_aggregator_rejects_missing_evidence():
    aggregator = VerificationResultAggregator()
    check1 = VerificationCheck(type=VerificationType.STATIC, name="Static AST", required=True)

    # Empty evidence list
    result = aggregator.aggregate(
        task_id="task-1",
        checks=[check1],
        evidence_list=[],
        judge_report={"passed": True, "status": "PASS"},
    )
    # Invariant: cannot pass without persisted evidence
    assert result.status == VerificationStatus.FAILED
    assert result.passed is False


def test_result_aggregator_handles_defects_and_judge_failure():
    aggregator = VerificationResultAggregator()
    check1 = VerificationCheck(type=VerificationType.DYNAMIC, name="Dynamic Tests", required=True)

    defect = VerificationDefect(
        type=DefectCategory.DYNAMIC_TEST_FAILURE.value,
        message="Tests failed",
        severity=DefectSeverity.HIGH.value,
    )
    ev1 = VerificationEvidence(
        verification_id="v-2",
        check_id=check1.check_id,
        status=VerificationStatus.FAILED,
        defects=[defect],
    )

    judge_report = VerificationReport(
        run_id="run-2",
        status="FAIL",
        passed=False,
        execution_state=ExecutionState.FAIL.value,
        static_result=LegacyVerificationResult(vector_name="static", status="PASS", passed=True),
        dynamic_result=LegacyVerificationResult(vector_name="dynamic", status="FAIL", passed=False),
        contract_result=LegacyVerificationResult(vector_name="contract", status="PASS", passed=True),
        summary="Judge failed",
    )

    result = aggregator.aggregate(
        task_id="task-2",
        checks=[check1],
        evidence_list=[ev1],
        judge_report=judge_report,
    )
    assert result.status == VerificationStatus.FAILED
    assert result.passed is False
    assert len(result.defects) == 1
    assert "Dynamic Tests" in result.failed_checks


def test_result_aggregator_cancellation():
    aggregator = VerificationResultAggregator()
    check1 = VerificationCheck(type=VerificationType.STATIC, name="Static AST", required=True)
    result = aggregator.aggregate(
        task_id="task-3",
        checks=[check1],
        evidence_list=[],
        cancellation_reason="User cancelled verification",
    )
    assert result.status == VerificationStatus.CANCELLED
    assert result.passed is False
    assert "User cancelled" in result.summary
