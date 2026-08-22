"""
Evidence Collector and Defect Normalizer for Phase 7 Verification.

Adapts and normalizes outputs from existing verification components:
  - StaticVerifier (AST/import checks)
  - DynamicVerifier (pytest/npm test runners)
  - ContractVerifier (acceptance criteria / invariant checks)
  - Judge (multi-vector synthesis)
Into canonical VerificationEvidence and VerificationDefect models without duplicating verification logic.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import uuid

from backend.agent.verification.contracts import (
    DefectCategory,
    DefectSeverity,
    VerificationCheck,
    VerificationDefect,
    VerificationEvidence,
    VerificationStatus,
)
from backend.verification.schemas import Defect as LegacyDefect, VerificationResult as LegacyVerificationResult

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 5000


class VerificationEvidenceCollector:
    """
    Collects, normalizes, and bounds verification evidence and defects.
    """

    def __init__(self, max_summary_chars: int = MAX_SUMMARY_CHARS):
        self.max_summary_chars = max_summary_chars

    def truncate_text(self, text: Optional[str]) -> Optional[str]:
        """Safely truncates long process output to avoid storage bloat."""
        if not text:
            return text
        if len(text) <= self.max_summary_chars:
            return text
        half = self.max_summary_chars // 2
        return (
            text[:half]
            + f"\n\n... [TRUNCATED {len(text) - self.max_summary_chars} CHARACTERS] ...\n\n"
            + text[-half:]
        )

    def normalize_defect(
        self,
        legacy_defect: Any,
        evidence_id: Optional[str] = None,
        default_command: Optional[str] = None,
    ) -> VerificationDefect:
        """
        Converts a legacy Defect or raw dictionary into a canonical VerificationDefect.
        """
        if isinstance(legacy_defect, VerificationDefect):
            return legacy_defect

        if isinstance(legacy_defect, LegacyDefect):
            cat = getattr(legacy_defect, "category", DefectCategory.DYNAMIC_TEST_FAILURE.value)
            sev = getattr(legacy_defect, "severity", DefectSeverity.HIGH.value)
            desc = getattr(legacy_defect, "description", "")
            fpath = getattr(legacy_defect, "file_path", None)
            line = getattr(legacy_defect, "line_number", None)
            sym = getattr(legacy_defect, "symbol", None)
            ev_id = getattr(legacy_defect, "evidence_id", evidence_id)
            return VerificationDefect(
                defect_id=str(uuid.uuid4()),
                type=str(cat),
                severity=str(sev),
                message=desc,
                file=fpath,
                symbol=sym,
                line=line,
                command=default_command,
                evidence_id=ev_id or evidence_id,
            )

        if isinstance(legacy_defect, dict):
            return VerificationDefect(
                defect_id=legacy_defect.get("defect_id") or str(uuid.uuid4()),
                type=legacy_defect.get("category") or legacy_defect.get("type") or DefectCategory.DYNAMIC_TEST_FAILURE.value,
                severity=legacy_defect.get("severity") or DefectSeverity.HIGH.value,
                message=legacy_defect.get("description") or legacy_defect.get("message") or "Unspecified defect",
                file=legacy_defect.get("file_path") or legacy_defect.get("file"),
                symbol=legacy_defect.get("symbol"),
                line=legacy_defect.get("line_number") or legacy_defect.get("line"),
                command=legacy_defect.get("command") or default_command,
                stack=self.truncate_text(legacy_defect.get("stack")),
                evidence_id=legacy_defect.get("evidence_id") or evidence_id,
            )

        # Generic fallback
        return VerificationDefect(
            defect_id=str(uuid.uuid4()),
            type=DefectCategory.EXECUTION_ERROR.value,
            severity=DefectSeverity.HIGH.value,
            message=str(legacy_defect),
            command=default_command,
            evidence_id=evidence_id,
        )

    def build_evidence_from_verifier_result(
        self,
        verification_id: str,
        check: VerificationCheck,
        verifier_result: LegacyVerificationResult | Dict[str, Any],
        duration_ms: float = 0.0,
    ) -> VerificationEvidence:
        """
        Normalizes a LegacyVerificationResult into a VerificationEvidence record.
        """
        evidence_id = str(uuid.uuid4())

        if isinstance(verifier_result, LegacyVerificationResult):
            passed = verifier_result.passed and verifier_result.status == "PASS"
            status = VerificationStatus.PASSED if passed else (
                VerificationStatus.ERROR if verifier_result.status == "ERROR" else VerificationStatus.FAILED
            )
            raw_defects = verifier_result.defects or []
            details = verifier_result.details or {}
            exec_time = verifier_result.execution_time_ms or duration_ms
        else:
            status_str = str(verifier_result.get("status", "")).upper()
            passed = bool(verifier_result.get("passed", False)) and status_str == "PASS"
            status = VerificationStatus.PASSED if passed else (
                VerificationStatus.ERROR if status_str == "ERROR" else VerificationStatus.FAILED
            )
            raw_defects = verifier_result.get("defects", [])
            details = verifier_result.get("details", {})
            exec_time = float(verifier_result.get("execution_time_ms", duration_ms))

        # Extract stdout/stderr summaries from details
        stdout_raw = details.get("stdout") or details.get("output") or details.get("summary")
        stderr_raw = details.get("stderr") or details.get("error")

        normalized_defects = [
            self.normalize_defect(d, evidence_id=evidence_id, default_command=check.command)
            for d in raw_defects
        ]

        return VerificationEvidence(
            verification_id=verification_id,
            check_id=check.check_id,
            status=status,
            command=check.command,
            exit_code=details.get("exit_code"),
            stdout_summary=self.truncate_text(str(stdout_raw)) if stdout_raw else None,
            stderr_summary=self.truncate_text(str(stderr_raw)) if stderr_raw else None,
            defects=normalized_defects,
            duration_ms=exec_time,
        )

    def create_error_evidence(
        self,
        verification_id: str,
        check: VerificationCheck,
        error_message: str,
        status: VerificationStatus = VerificationStatus.ERROR,
        duration_ms: float = 0.0,
    ) -> VerificationEvidence:
        """
        Creates an evidence envelope for exceptions or timeouts encountered during check execution.
        """
        evidence_id = str(uuid.uuid4())
        defect_type = (
            DefectCategory.VERIFICATION_TIMEOUT.value
            if status == VerificationStatus.FAILED and "timeout" in error_message.lower()
            else DefectCategory.EXECUTION_ERROR.value
        )
        defect = VerificationDefect(
            defect_id=str(uuid.uuid4()),
            type=defect_type,
            severity=DefectSeverity.CRITICAL.value if status == VerificationStatus.ERROR else DefectSeverity.HIGH.value,
            message=error_message,
            command=check.command,
            evidence_id=evidence_id,
        )
        return VerificationEvidence(
            verification_id=verification_id,
            check_id=check.check_id,
            status=status,
            command=check.command,
            stderr_summary=self.truncate_text(error_message),
            defects=[defect],
            duration_ms=duration_ms,
        )
