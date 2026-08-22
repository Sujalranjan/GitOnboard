"""
Verification Result Aggregator for Phase 7 Verification-Driven Execution.

Synthesizes multiple VerificationEvidence records, itemized defects, and the Judge's verdict
into an authoritative VerificationResult envelope.

Strict Invariant Enforced:
  A task can ONLY reach PASSED when:
    1. All required verification checks completed successfully.
    2. Non-empty, verified evidence is persisted.
    3. Zero critical/unresolved defects remain.
    4. The Judge produces an explicit PASS verdict.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import uuid

from backend.agent.verification.contracts import (
    VerificationCheck,
    VerificationDefect,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
)
from backend.verification.schemas import ExecutionState, VerificationReport

logger = logging.getLogger(__name__)


class VerificationResultAggregator:
    """
    Aggregates check evidence, itemized defects, and Judge synthesis into a canonical VerificationResult.
    """

    def aggregate(
        self,
        task_id: str,
        checks: List[VerificationCheck],
        evidence_list: List[VerificationEvidence],
        judge_report: Optional[VerificationReport | Dict[str, Any]] = None,
        duration_ms: float = 0.0,
        cancellation_reason: Optional[str] = None,
    ) -> VerificationResult:
        """
        Synthesizes the overall VerificationResult.
        """
        verification_id = str(uuid.uuid4())
        all_defects: List[VerificationDefect] = []
        passed_checks: List[str] = []
        failed_checks: List[str] = []

        # Tally individual check evidence
        for ev in evidence_list:
            all_defects.extend(ev.defects)
            check_name = ev.check_id
            for c in checks:
                if c.check_id == ev.check_id:
                    check_name = c.name
                    break

            if ev.status == VerificationStatus.PASSED:
                passed_checks.append(check_name)
            else:
                failed_checks.append(check_name)

        # Handle cancellation
        if cancellation_reason:
            summary = f"Verification CANCELLED for task '{task_id}': {cancellation_reason}"
            return VerificationResult(
                verification_id=verification_id,
                task_id=task_id,
                status=VerificationStatus.CANCELLED,
                passed=False,
                checks=checks,
                passed_checks=passed_checks,
                failed_checks=failed_checks,
                defects=all_defects,
                evidence=evidence_list,
                duration_ms=duration_ms,
                summary=summary,
            )

        # Parse Judge Report
        judge_dict: Optional[Dict[str, Any]] = None
        judge_passed = False
        judge_state = ExecutionState.UNVERIFIED.value

        if isinstance(judge_report, VerificationReport):
            judge_dict = judge_report.model_dump()
            judge_passed = judge_report.passed
            judge_state = judge_report.execution_state
        elif isinstance(judge_report, dict):
            judge_dict = judge_report
            judge_passed = bool(judge_report.get("passed", False))
            judge_state = judge_report.get("execution_state") or (
                ExecutionState.PASS.value if judge_passed else ExecutionState.FAIL.value
            )

        # Evaluate Strict Invariant:
        # 1. All required checks must have passed evidence
        required_checks = [c for c in checks if c.required]
        required_check_ids = {c.check_id for c in required_checks}
        passed_check_ids = {ev.check_id for ev in evidence_list if ev.status == VerificationStatus.PASSED}
        all_required_passed = required_check_ids.issubset(passed_check_ids)

        # 2. Must have concrete evidence items
        has_evidence = len(evidence_list) > 0

        # 3. Overall status decision
        has_error = any(ev.status == VerificationStatus.ERROR for ev in evidence_list)
        has_failed_check = len(failed_checks) > 0 or not all_required_passed

        if has_error:
            status = VerificationStatus.ERROR
            passed = False
        elif has_failed_check or not judge_passed or len(all_defects) > 0 or not has_evidence:
            status = VerificationStatus.FAILED
            passed = False
        else:
            status = VerificationStatus.PASSED
            passed = True

        # Generate summary
        if passed:
            summary = (
                f"VERIFICATION PASSED: Task '{task_id}' satisfied all {len(checks)} verification checks "
                f"with verified evidence. Judge verdict: PASS."
            )
        elif status == VerificationStatus.ERROR:
            summary = (
                f"VERIFICATION ERROR: Task '{task_id}' encountered runtime error during verification. "
                f"{len(all_defects)} defect(s) recorded."
            )
        else:
            reasons = []
            if not all_required_passed:
                reasons.append(f"required checks not satisfied ({len(failed_checks)} failed)")
            if not judge_passed:
                reasons.append(f"Judge returned {judge_state}")
            if len(all_defects) > 0:
                reasons.append(f"{len(all_defects)} defect(s) detected")
            if not has_evidence:
                reasons.append("zero evidence items persisted")
            summary = f"VERIFICATION FAILED: Task '{task_id}' failed criteria: {', '.join(reasons)}."

        logger.info(
            f"VerificationResultAggregator: task='{task_id}' verdict={status.value} "
            f"passed={passed} defects={len(all_defects)} evidence={len(evidence_list)}"
        )

        return VerificationResult(
            verification_id=verification_id,
            task_id=task_id,
            status=status,
            passed=passed,
            checks=checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            defects=all_defects,
            evidence=evidence_list,
            duration_ms=duration_ms,
            judge_result=judge_dict,
            summary=summary,
        )
