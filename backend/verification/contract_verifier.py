"""
ContractVerifier: Adversarially validates unified git diffs against ground-truth ImplementationContracts.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .schemas import Defect, DefectCategory, DefectSeverity, ExecutionState, VerificationResult

logger = logging.getLogger(__name__)


class ContractVerifier:
    """
    Contract Verification Vector:
    Compares the unified git diff and modified file list against the ImplementationContract
    to detect omitted components, missing test coverage, or unaddressed acceptance criteria.
    """

    def verify(
        self,
        contract: Union[Dict[str, Any], Any],
        modified_files: List[str],
        git_diff: str = "",
    ) -> VerificationResult:
        start_time = time.time()
        defects: List[Defect] = []
        evidence_manifest: List[Dict[str, Any]] = []

        if not contract:
            return VerificationResult(
                vector_name="contract",
                status=ExecutionState.UNVERIFIED.value,
                passed=False,
                execution_state=ExecutionState.UNVERIFIED.value,
                defects=[],
                evidence_manifest=[],
                details={"message": "No contract provided for verification; marked UNVERIFIED"},
                execution_time_ms=0.0,
            )

        # Normalize contract dict structure
        contract_data = self._normalize_contract(contract)

        # 1. Check Affected Components Coverage
        affected_components = contract_data.get("affected_components", [])
        norm_modified = {f.replace("\\", "/").lower() for f in modified_files}

        for comp in affected_components:
            comp_file = comp.get("file", "").replace("\\", "/").lower()
            symbol = comp.get("symbol")
            if not comp_file:
                continue

            # Check if component file exists in modified file list or git diff
            matched = any(comp_file in f or f in comp_file for f in norm_modified)
            if not matched and git_diff:
                matched = comp_file in git_diff.lower()

            if not matched:
                defects.append(
                    Defect(
                        category=DefectCategory.CONTRACT_OMISSION.value,
                        file_path=comp.get("file", ""),
                        description=f"Implementation Contract required modifying component '{comp.get('file')}', but file was not touched in git changeset.",
                        severity=DefectSeverity.HIGH.value,
                        symbol=symbol,
                        evidence_id=comp.get("evidence_ids", [None])[0] if comp.get("evidence_ids") else None,
                    )
                )

        # 2. Check Required Tests Coverage
        tests_required = contract_data.get("tests_required", [])
        has_test_changes = any(
            "test" in f or f.startswith("tests/") or f.endswith("_test.py") or f.endswith(".test.ts")
            for f in norm_modified
        )

        if tests_required and not has_test_changes:
            for test_req in tests_required[:3]:
                defects.append(
                    Defect(
                        category=DefectCategory.CONTRACT_OMISSION.value,
                        file_path="tests",
                        description=f"Implementation Contract required test: '{test_req}', but no test files were created or modified in changeset.",
                        severity=DefectSeverity.HIGH.value,
                    )
                )

        # 3. Check Acceptance Criteria / Invariants
        acceptance_criteria = contract_data.get("acceptance_criteria", [])
        if acceptance_criteria and git_diff:
            diff_lower = git_diff.lower()
            for criterion in acceptance_criteria:
                crit_text = criterion if isinstance(criterion, str) else criterion.get("description", "")
                # Check key invariant terms (e.g. expiration, validate, error, 400, 401, token)
                if "expir" in crit_text.lower() and "expir" not in diff_lower and "ttl" not in diff_lower:
                    defects.append(
                        Defect(
                            category=DefectCategory.CONTRACT_INVARIANT_VIOLATION.value,
                            file_path="changeset",
                            description=f"Contract criterion requires expiration check ('{crit_text}'), but no expiration logic was found in diff.",
                            severity=DefectSeverity.HIGH.value,
                        )
                    )

        # Build evidence items
        if affected_components:
            evidence_manifest.append({
                "type": "affected_components_checked",
                "count": len(affected_components),
                "items": [c.get("file") for c in affected_components if isinstance(c, dict)],
            })
        if tests_required:
            evidence_manifest.append({
                "type": "tests_required_checked",
                "count": len(tests_required),
                "items": tests_required,
            })
        if acceptance_criteria:
            evidence_manifest.append({
                "type": "acceptance_criteria_checked",
                "count": len(acceptance_criteria),
            })

        elapsed_ms = (time.time() - start_time) * 1000
        has_evidence = len(evidence_manifest) > 0 or bool(git_diff)
        passed = (len(defects) == 0) and has_evidence
        
        if not has_evidence and len(defects) == 0:
            exec_state = ExecutionState.UNVERIFIED.value
        elif passed:
            exec_state = ExecutionState.PASS.value
        else:
            exec_state = ExecutionState.FAIL.value

        status = exec_state

        logger.info(f"ContractVerifier finished: status={status}, defects={len(defects)}, time={elapsed_ms:.1f}ms")
        return VerificationResult(
            vector_name="contract",
            status=status,
            passed=passed,
            execution_state=exec_state,
            defects=defects,
            evidence_manifest=evidence_manifest,
            details={
                "affected_components_checked": len(affected_components),
                "tests_required_checked": len(tests_required),
                "evidence_count": len(evidence_manifest),
            },
            execution_time_ms=elapsed_ms,
        )

    def _normalize_contract(self, contract: Any) -> Dict[str, Any]:
        if isinstance(contract, dict):
            return contract
        # Pydantic model or SQLAlchemy model
        data = {}
        for attr in ["affected_components", "tests_required", "security_considerations", "acceptance_criteria"]:
            if hasattr(contract, attr):
                val = getattr(contract, attr)
                data[attr] = val if val is not None else []
        return data
