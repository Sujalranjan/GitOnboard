"""
Unit Tests for FailureDiagnosisController.
"""
from backend.agent.planning.contracts import PlanTask
from backend.agent.repair.contracts import FailureCategory
from backend.agent.repair.diagnosis import FailureDiagnosisController
from backend.agent.tasks.contracts import TaskExecutionContext
from backend.agent.verification.contracts import (
    DefectCategory,
    DefectSeverity,
    VerificationCheck,
    VerificationDefect,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
    VerificationType,
)


def test_diagnosis_controller_extracts_syntax_defect():
    controller = FailureDiagnosisController()

    v_defect = VerificationDefect(
        type="SYNTAX_ERROR",
        severity=DefectSeverity.CRITICAL,
        message="invalid syntax at line 5",
        file="app/calc.py",
        symbol="add",
        line=5,
    )
    v_evidence = VerificationEvidence(
        verification_id="verif-1",
        check_id="check-1",
        status=VerificationStatus.FAILED,
        command="pytest",
        exit_code=1,
        stderr_summary="SyntaxError: invalid syntax at line 5",
        defects=[v_defect],
    )
    verif_res = VerificationResult(
        verification_id="verif-1",
        task_id="task-1",
        status=VerificationStatus.FAILED,
        passed=False,
        failed_checks=["Static AST & Import Integrity"],
        defects=[v_defect],
        evidence=[v_evidence],
        summary="Static verification failed",
    )

    task_def = PlanTask(
        task_id="task-1",
        step_number=1,
        title="Implement calculator",
        description="Add calculator.py",
        affected_files=["app/calc.py"],
        acceptance_criteria=["calc.py exists"],
    )
    task_ctx = TaskExecutionContext(
        agent_run_id="run-1",
        plan_id="plan-1",
        task_id="task-1",
        repository_id="repo-1",
        task_definition=task_def,
    )

    diag_ctx = controller.diagnose(task_ctx, verif_res, attempt_number=1)

    assert diag_ctx.task_id == "task-1"
    assert diag_ctx.primary_category == FailureCategory.SYNTAX_ERROR
    assert "app/calc.py" in diag_ctx.affected_files
    assert len(diag_ctx.defects) == 1
    assert diag_ctx.defects[0].category == FailureCategory.SYNTAX_ERROR
    assert "invalid syntax" in diag_ctx.known_evidence_summary


def test_diagnosis_controller_extracts_test_failure():
    controller = FailureDiagnosisController()

    v_defect = VerificationDefect(
        type="DYNAMIC_TEST_FAILURE",
        severity=DefectSeverity.HIGH,
        message="AssertionError: assert 4 == 5",
        file="tests/test_calc.py",
        symbol="test_add",
    )
    v_evidence = VerificationEvidence(
        verification_id="verif-2",
        check_id="check-2",
        status=VerificationStatus.FAILED,
        command="pytest tests/test_calc.py",
        exit_code=1,
        stdout_summary="FAILED tests/test_calc.py::test_add",
        defects=[v_defect],
    )
    verif_res = VerificationResult(
        verification_id="verif-2",
        task_id="task-2",
        status=VerificationStatus.FAILED,
        passed=False,
        failed_checks=["Dynamic Test Execution"],
        defects=[v_defect],
        evidence=[v_evidence],
        summary="Dynamic test execution failed",
    )

    task_def = PlanTask(
        task_id="task-2",
        step_number=1,
        title="Implement calculator test",
        description="Add test",
        affected_files=["tests/test_calc.py"],
        acceptance_criteria=["tests pass"],
    )
    task_ctx = TaskExecutionContext(
        agent_run_id="run-1",
        plan_id="plan-1",
        task_id="task-2",
        repository_id="repo-1",
        task_definition=task_def,
    )

    diag_ctx = controller.diagnose(task_ctx, verif_res, attempt_number=1)

    assert diag_ctx.primary_category == FailureCategory.TEST_FAILURE
    assert "tests/test_calc.py" in diag_ctx.affected_files
    assert diag_ctx.failing_commands == ["pytest tests/test_calc.py"]


def test_diagnosis_controller_fallback_on_unspecified_failure():
    controller = FailureDiagnosisController()

    verif_res = VerificationResult(
        verification_id="verif-3",
        task_id="task-3",
        status=VerificationStatus.FAILED,
        passed=False,
        summary="Contract verification failed: missing required criteria.",
    )
    task_def = PlanTask(
        task_id="task-3",
        step_number=1,
        title="Contract check",
        description="Verify contract",
    )
    task_ctx = TaskExecutionContext(
        agent_run_id="run-1",
        plan_id="plan-1",
        task_id="task-3",
        repository_id="repo-1",
        task_definition=task_def,
    )

    diag_ctx = controller.diagnose(task_ctx, verif_res, attempt_number=1)

    assert diag_ctx.primary_category == FailureCategory.CONTRACT_FAILURE
    assert len(diag_ctx.defects) == 1
    assert "Contract verification failed" in diag_ctx.defects[0].message
