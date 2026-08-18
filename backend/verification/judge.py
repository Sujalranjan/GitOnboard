from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from .schemas import Defect, ExecutionState, VerificationReport, VerificationResult

logger = logging.getLogger(__name__)


class Judge:
    """
    Evidence Aggregator & Judge:
    Synthesizes multi-vector verification results (Static, Dynamic, Contract) into a final
    VerificationReport with an itemized defect manifest and evidence-backed execution state.
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

        # Aggregate evidence items
        aggregated_evidence: List[Dict[str, Any]] = []
        for res in (static_result, dynamic_result, contract_result):
            if res.evidence_manifest:
                for ev in res.evidence_manifest:
                    aggregated_evidence.append({
                        "vector": res.vector_name,
                        **ev
                    })

        # Check vector execution states
        vector_states = {
            static_result.execution_state or static_result.status,
            dynamic_result.execution_state or dynamic_result.status,
            contract_result.execution_state or contract_result.status,
        }

        # Evidence sufficiency rule:
        # A vector claiming PASS with 0 evidence must not produce overall PASS.
        has_concrete_evidence = len(aggregated_evidence) > 0

        if ExecutionState.ERROR.value in vector_states or any(r.status == "ERROR" for r in (static_result, dynamic_result, contract_result)):
            overall_state = ExecutionState.ERROR.value
            passed = False
        elif ExecutionState.FAIL.value in vector_states or len(all_defects) > 0:
            overall_state = ExecutionState.FAIL.value
            passed = False
        elif ExecutionState.MOCKED.value in vector_states:
            overall_state = ExecutionState.MOCKED.value
            passed = False
        elif ExecutionState.UNVERIFIED.value in vector_states or not has_concrete_evidence:
            overall_state = ExecutionState.UNVERIFIED.value
            passed = False
        elif (
            static_result.passed
            and dynamic_result.passed
            and contract_result.passed
            and len(all_defects) == 0
            and has_concrete_evidence
        ):
            overall_state = ExecutionState.PASS.value
            passed = True
        else:
            overall_state = ExecutionState.UNVERIFIED.value
            passed = False

        status = overall_state

        # Executive summary generation
        if overall_state == ExecutionState.PASS.value:
            summary = (
                f"VERIFICATION PASS: Run '{run_id}' satisfied all Static AST symbol checks, "
                f"Dynamic test/build execution, and Implementation Contract requirements with verified evidence."
            )
        elif overall_state == ExecutionState.UNVERIFIED.value:
            summary = (
                f"VERIFICATION UNVERIFIED: Run '{run_id}' lacked sufficient verifiable evidence "
                f"(missing contract, empty test run, or unscanned changeset) to declare PASS."
            )
        elif overall_state == ExecutionState.MOCKED.value:
            summary = f"VERIFICATION MOCKED: Run '{run_id}' evaluated against mock/simulated fixtures."
        elif overall_state == ExecutionState.ERROR.value:
            summary = f"VERIFICATION ERROR: Run '{run_id}' encountered runtime execution errors."
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
            execution_state=overall_state,
            static_result=static_result,
            dynamic_result=dynamic_result,
            contract_result=contract_result,
            defects=all_defects,
            evidence_manifest=aggregated_evidence,
            summary=summary,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            f"Judge aggregated verdict for run '{run_id}': state={overall_state}, status={status}, "
            f"total_defects={len(all_defects)}, evidence_items={len(aggregated_evidence)}"
        )
        return report
