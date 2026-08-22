"""
Unit Tests for RepairAttemptTracker and Bounded Limits.
"""
from backend.agent.repair.contracts import (
    Defect,
    DiagnosisContext,
    FailureCategory,
    RepairConfig,
    RepairStatus,
)
from backend.agent.repair.limits import RepairAttemptTracker
from backend.agent.verification.contracts import VerificationResult, VerificationStatus


def test_repair_limits_attempt_budget():
    tracker = RepairAttemptTracker(config=RepairConfig(max_repair_attempts=2))

    # Attempt 1 -> Allowed
    allowed, att1, err = tracker.start_attempt(task_id="task-1", diagnosis_id="diag-1")
    assert allowed is True
    assert att1.attempt_number == 1
    assert err is None

    # Complete Attempt 1
    tracker.record_attempt_completion(
        task_id="task-1",
        attempt=att1,
        changed_files=["app.py"],
        diff="--- diff",
        verification_result=VerificationResult(
            verification_id="v1",
            task_id="task-1",
            status=VerificationStatus.FAILED,
            passed=False,
            summary="Failed again",
        ),
    )
    assert att1.status == RepairStatus.FAILED

    # Attempt 2 -> Allowed
    allowed, att2, err = tracker.start_attempt(task_id="task-1", diagnosis_id="diag-2")
    assert allowed is True
    assert att2.attempt_number == 2

    tracker.record_attempt_completion(
        task_id="task-1",
        attempt=att2,
        changed_files=["app.py"],
        diff="--- diff 2",
        verification_result=VerificationResult(
            verification_id="v2",
            task_id="task-1",
            status=VerificationStatus.FAILED,
            passed=False,
            summary="Failed second time",
        ),
    )

    # Attempt 3 -> REJECTED (Exceeded limit of 2)
    allowed, att3, err = tracker.start_attempt(task_id="task-1", diagnosis_id="diag-3")
    assert allowed is False
    assert att3 is None
    assert "Maximum repair attempts (2) exhausted" in err


def test_repair_limits_repeated_failure_signature_detection():
    tracker = RepairAttemptTracker(config=RepairConfig(max_repeated_failure_signatures=2))

    diag_ctx = DiagnosisContext(
        task_id="task-repeat",
        primary_category=FailureCategory.SYNTAX_ERROR,
        failing_checks=["Static Check"],
        affected_files=["bad.py"],
        defects=[Defect(task_id="task-repeat", message="syntax error at line 1")],
    )

    # First occurrence -> OK
    ok1, reason1 = tracker.record_and_check_signature("task-repeat", diag_ctx, diff="diff-1")
    assert ok1 is True
    assert reason1 is None

    # Second identical occurrence -> BLOCKED
    ok2, reason2 = tracker.record_and_check_signature("task-repeat", diag_ctx, diff="diff-1")
    assert ok2 is False
    assert "Repeated identical failure signature detected 2 times" in reason2
