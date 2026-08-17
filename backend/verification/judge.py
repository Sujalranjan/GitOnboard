"""
Judge: Aggregates evidence from Static, Dynamic, and Contract verifiers into a unified VerificationReport.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from .schemas import Defect, VerificationReport, VerificationResult

logger = logging.getLogger(__name__)


class Judge:
    """
    Evidence Aggregator & Judge:
    Synthesizes multi-vector verification results (Static, Dynamic, Contract) into a final
    VerificationReport with an itemized defect manifest.
    """

    def aggregate(
        self,
        run_id: str,
        static_result: VerificationResult,
        dynamic_result: VerificationResult,
        contract_result: VerificationResult,
    ) -> VerificationReport:
        # Combine all defects from all vectors
        all_defects: List[Defect] = []
        all_defects.extend(static_result.defects)
        all_defects.extend(dynamic_result.defects)
        all_defects.extend(contract_result.defects)

        # Overall verdict: PASS only if ALL vector results passed with 0 defects
        passed = (
            static_result.passed
            and dynamic_result.passed
            and contract_result.passed
            and len(all_defects) == 0
        )
        status = "PASS" if passed else "FAIL"

        # Executive summary generation
        if passed:
            summary = (
                f"VERIFICATION PASS: Run '{run_id}' satisfied all Static AST symbol checks, "
                f"Dynamic test/build execution, and Implementation Contract requirements with zero defects."
            )
        else:
            vector_statuses = (
                f"Static: {static_result.status}, Dynamic: {dynamic_result.status}, Contract: {contract_result.status}"
            )
            summary = (
                f"VERIFICATION FAIL: Run '{run_id}' failed with {len(all_defects)} detected defect(s). [{vector_statuses}]"
            )

        report = VerificationReport(
            run_id=run_id,
            status=status,
            passed=passed,
            static_result=static_result,
            dynamic_result=dynamic_result,
            contract_result=contract_result,
            defects=all_defects,
            summary=summary,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(f"Judge aggregated verdict for run '{run_id}': status={status}, total_defects={len(all_defects)}")
        return report
