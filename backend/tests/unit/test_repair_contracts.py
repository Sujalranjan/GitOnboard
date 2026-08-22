"""
Unit Tests for Phase 8 Repair Contracts and Data Models.
"""
from backend.agent.repair.contracts import (
    Defect,
    DiagnosisCategory,
    DiagnosisContext,
    DiagnosisStatus,
    FailureCategory,
    RepairAttempt,
    RepairConfig,
    RepairResult,
    RepairStatus,
)
from backend.agent.verification.contracts import DefectSeverity


def test_repair_status_enums():
    assert RepairStatus.NOT_STARTED == "NOT_STARTED"
    assert RepairStatus.DIAGNOSING == "DIAGNOSING"
    assert RepairStatus.REPAIRING == "REPAIRING"
    assert RepairStatus.REVERIFYING == "REVERIFYING"
    assert RepairStatus.PASSED == "PASSED"
    assert RepairStatus.FAILED == "FAILED"
    assert RepairStatus.BLOCKED == "BLOCKED"
    assert RepairStatus.CANCELLED == "CANCELLED"

    assert DiagnosisStatus.PENDING == "PENDING"
    assert DiagnosisStatus.COMPLETED == "COMPLETED"
    assert DiagnosisStatus.UNRESOLVED == "UNRESOLVED"

    assert FailureCategory.SYNTAX_ERROR == "SYNTAX_ERROR"
    assert FailureCategory.TEST_FAILURE == "TEST_FAILURE"
    assert FailureCategory.CONTRACT_FAILURE == "CONTRACT_FAILURE"


def test_defect_model():
    defect = Defect(
        task_id="task-1",
        category=FailureCategory.SYNTAX_ERROR,
        severity=DefectSeverity.CRITICAL,
        message="invalid syntax at line 12",
        affected_files=["app/main.py"],
        affected_symbols=["run_app"],
        command="pytest",
        exit_code=1,
    )
    assert defect.defect_id is not None
    assert defect.category == FailureCategory.SYNTAX_ERROR
    assert defect.affected_files == ["app/main.py"]
    assert defect.affected_symbols == ["run_app"]
    
    # Test JSON serialization
    serialized = defect.model_dump(mode="json")
    assert serialized["message"] == "invalid syntax at line 12"


def test_diagnosis_context_model():
    defect = Defect(
        task_id="task-1",
        category=FailureCategory.TEST_FAILURE,
        message="AssertionError: expected 200 got 500",
        affected_files=["services/user.py"],
    )
    diag = DiagnosisContext(
        task_id="task-1",
        task_title="User Service API",
        task_description="Implement user service",
        acceptance_criteria=["GET /users returns 200"],
        defects=[defect],
        primary_category=FailureCategory.TEST_FAILURE,
        affected_files=["services/user.py"],
        failing_checks=["Dynamic Test Execution"],
    )
    assert diag.task_id == "task-1"
    assert len(diag.defects) == 1
    assert len(diag.repair_constraints) >= 3


def test_repair_attempt_and_result_models():
    attempt = RepairAttempt(
        task_id="task-1",
        attempt_number=1,
        diagnosis_id="diag-1",
        status=RepairStatus.PASSED,
        changed_files=["services/user.py"],
        diff="--- a/services/user.py\n+++ b/services/user.py\n",
    )
    assert attempt.attempt_number == 1
    assert attempt.status == RepairStatus.PASSED

    result = RepairResult(
        task_id="task-1",
        status=RepairStatus.PASSED,
        passed=True,
        diagnosis_id="diag-1",
        attempts_used=1,
        max_attempts=3,
        changed_files=["services/user.py"],
        history=[attempt],
        summary="Task repaired and verified successfully.",
    )
    assert result.passed is True
    assert result.attempts_used == 1
    assert len(result.history) == 1


def test_repair_config_defaults():
    cfg = RepairConfig()
    assert cfg.max_repair_attempts == 3
    assert cfg.max_agent_iterations_per_attempt == 10
    assert cfg.max_repair_duration_sec == 300.0
    assert cfg.max_repeated_failure_signatures == 2
