"""
FailureDiagnosisController: Converts verification failures into structured diagnosis context.

Core Invariants:
  1. The controller is NOT the bug fixer; it extracts facts, formats evidence, and builds structured diagnosis context.
  2. The controller distinguishes known evidence (facts, stack traces, exit codes) from unknown root causes.
  3. LLM agents receive clean, normalized defect models rather than raw, unparsed backend exceptions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from backend.agent.repair.contracts import (
    Defect,
    DiagnosisCategory,
    DiagnosisContext,
    FailureCategory,
)
from backend.agent.tasks.contracts import TaskExecutionContext
from backend.agent.verification.contracts import (
    DefectCategory,
    DefectSeverity,
    VerificationDefect,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class FailureDiagnosisController:
    """
    Analyzes verification results and transforms raw failure evidence
    into structured DiagnosisContext for the Engineering Agent.
    """

    def __init__(self):
        pass

    def extract_defects(
        self,
        task_id: str,
        verification_result: VerificationResult,
    ) -> List[Defect]:
        """
        Normalizes VerificationDefect and VerificationEvidence records from
        a VerificationResult into canonical Defect objects.
        """
        normalized_defects: List[Defect] = []

        # 1. Map existing VerificationDefects
        for v_defect in verification_result.defects:
            category = self._classify_defect_category(v_defect.type, v_defect.message)
            severity = self._map_severity(v_defect.severity)

            # Find matching evidence if available
            matching_evidence: Optional[VerificationEvidence] = None
            if v_defect.evidence_id:
                for ev in verification_result.evidence:
                    if ev.check_id == v_defect.evidence_id or v_defect.evidence_id in str(ev.defects):
                        matching_evidence = ev
                        break
            elif verification_result.evidence:
                for ev in verification_result.evidence:
                    if v_defect in ev.defects or ev.status in (VerificationStatus.FAILED, VerificationStatus.ERROR):
                        matching_evidence = ev
                        break

            affected_files: List[str] = []
            if v_defect.file:
                affected_files.append(v_defect.file)

            affected_symbols: List[str] = []
            if v_defect.symbol:
                affected_symbols.append(v_defect.symbol)

            defect = Defect(
                task_id=task_id,
                verification_id=verification_result.verification_id,
                category=category,
                severity=severity,
                message=v_defect.message,
                command=v_defect.command or (matching_evidence.command if matching_evidence else None),
                exit_code=matching_evidence.exit_code if matching_evidence else None,
                stdout_summary=matching_evidence.stdout_summary if matching_evidence else None,
                stderr_summary=matching_evidence.stderr_summary if matching_evidence else None,
                stack_trace=v_defect.stack,
                affected_files=affected_files,
                affected_symbols=affected_symbols,
                actual_behavior=v_defect.message,
            )
            normalized_defects.append(defect)

        # 2. If no explicit defects were listed but checks failed, construct defects from failing evidence
        if not normalized_defects:
            for ev in verification_result.evidence:
                if ev.status in (VerificationStatus.FAILED, VerificationStatus.ERROR):
                    category = self._classify_defect_category("CHECK_FAILURE", ev.stderr_summary or ev.stdout_summary or "")
                    msg = ev.stderr_summary or ev.stdout_summary or f"Verification check '{ev.check_id}' failed"
                    defect = Defect(
                        task_id=task_id,
                        verification_id=verification_result.verification_id,
                        category=category,
                        severity=DefectSeverity.HIGH,
                        message=msg[:500],
                        command=ev.command,
                        exit_code=ev.exit_code,
                        stdout_summary=ev.stdout_summary,
                        stderr_summary=ev.stderr_summary,
                        actual_behavior=msg[:300],
                    )
                    normalized_defects.append(defect)

        # 3. Fallback: if still empty (e.g. Judge failed), construct general defect from summary
        if not normalized_defects and not verification_result.passed:
            category = FailureCategory.CONTRACT_FAILURE if "Contract" in verification_result.summary else FailureCategory.UNKNOWN
            normalized_defects.append(
                Defect(
                    task_id=task_id,
                    verification_id=verification_result.verification_id,
                    category=category,
                    severity=DefectSeverity.HIGH,
                    message=verification_result.summary or "Task failed verification without specific defect trace.",
                    actual_behavior=verification_result.summary,
                )
            )

        return normalized_defects

    def diagnose(
        self,
        task_context: TaskExecutionContext,
        verification_result: VerificationResult,
        attempt_number: int = 1,
        repository_context_summary: Optional[str] = None,
    ) -> DiagnosisContext:
        """
        Synthesizes a structured DiagnosisContext from verification output.
        """
        task_id = task_context.task_id
        task_def = task_context.task_definition
        task_title = task_def.title if task_def else task_id
        task_desc = task_def.description if task_def else ""
        acceptance_criteria = list(task_def.acceptance_criteria) if task_def else []

        defects = self.extract_defects(task_id, verification_result)

        # Determine primary category
        primary_category = self._determine_primary_category(defects)

        # Aggregate affected files and symbols
        affected_files_set: Set[str] = set()
        affected_symbols_set: Set[str] = set()
        failing_commands: List[str] = []

        if task_def and task_def.affected_files:
            affected_files_set.update(task_def.affected_files)

        for d in defects:
            affected_files_set.update(d.affected_files)
            affected_symbols_set.update(d.affected_symbols)
            if d.command and d.command not in failing_commands:
                failing_commands.append(d.command)

        for ev in verification_result.evidence:
            if ev.command and ev.status in (VerificationStatus.FAILED, VerificationStatus.ERROR) and ev.command not in failing_commands:
                failing_commands.append(ev.command)

        # Known evidence summary
        known_summary = self._build_known_evidence_summary(
            defects=defects,
            failing_checks=verification_result.failed_checks,
            failing_commands=failing_commands,
        )

        return DiagnosisContext(
            task_id=task_id,
            task_title=task_title,
            task_description=task_desc,
            acceptance_criteria=acceptance_criteria,
            defects=defects,
            primary_category=primary_category,
            affected_files=sorted(list(affected_files_set)),
            affected_symbols=sorted(list(affected_symbols_set)),
            failing_commands=failing_commands,
            failing_checks=list(verification_result.failed_checks),
            repository_context_summary=repository_context_summary,
            repair_attempt_number=attempt_number,
            known_evidence_summary=known_summary,
        )

    def _classify_defect_category(self, type_str: str, message: str) -> FailureCategory:
        type_upper = (type_str or "").upper()
        msg_upper = (message or "").upper()

        if "SYNTAX" in type_upper or "SYNTAXERROR" in msg_upper or "INVALID SYNTAX" in msg_upper:
            return FailureCategory.SYNTAX_ERROR
        if "IMPORT" in type_upper or "MODULENOTFOUND" in msg_upper or "CANNOT IMPORT" in msg_upper:
            return FailureCategory.STATIC_FAILURE
        if "TYPE" in type_upper or "TYPEERROR" in msg_upper:
            return FailureCategory.TYPE_ERROR
        if "TEST" in type_upper or "ASSERTION" in msg_upper or "PYTEST" in msg_upper:
            return FailureCategory.TEST_FAILURE
        if "CONTRACT" in type_upper or "CRITERIA" in msg_upper or "INVARIANT" in msg_upper:
            return FailureCategory.CONTRACT_FAILURE
        if "TIMEOUT" in type_upper or "TIMED OUT" in msg_upper:
            return FailureCategory.TIMEOUT
        if "COMMAND" in type_upper or "EXIT CODE" in msg_upper:
            return FailureCategory.COMMAND_FAILURE
        if "RUNTIME" in type_upper or "EXCEPTION" in msg_upper:
            return FailureCategory.RUNTIME_FAILURE
        if "STATIC" in type_upper or "AST" in msg_upper:
            return FailureCategory.STATIC_FAILURE

        return FailureCategory.UNKNOWN

    def _map_severity(self, sev: Any) -> DefectSeverity:
        if isinstance(sev, DefectSeverity):
            return sev
        sev_str = str(sev).upper()
        if "BLOCK" in sev_str:
            return DefectSeverity.BLOCKER
        if "CRIT" in sev_str or "HIGH" in sev_str:
            return DefectSeverity.HIGH
        if "MED" in sev_str:
            return DefectSeverity.MEDIUM
        return DefectSeverity.LOW

    def _determine_primary_category(self, defects: List[Defect]) -> FailureCategory:
        if not defects:
            return FailureCategory.UNKNOWN

        # Priority order: SYNTAX > STATIC > TEST > CONTRACT > RUNTIME > COMMAND > TYPE > TIMEOUT > UNKNOWN
        priority = [
            FailureCategory.SYNTAX_ERROR,
            FailureCategory.STATIC_FAILURE,
            FailureCategory.TEST_FAILURE,
            FailureCategory.CONTRACT_FAILURE,
            FailureCategory.RUNTIME_FAILURE,
            FailureCategory.COMMAND_FAILURE,
            FailureCategory.TYPE_ERROR,
            FailureCategory.TIMEOUT,
        ]
        defect_categories = {d.category for d in defects}
        for cat in priority:
            if cat in defect_categories:
                return cat
        return defects[0].category

    def _build_known_evidence_summary(
        self,
        defects: List[Defect],
        failing_checks: List[str],
        failing_commands: List[str],
    ) -> str:
        lines: List[str] = []
        if failing_checks:
            lines.append(f"Failed Verification Checks: {', '.join(failing_checks)}")
        if failing_commands:
            lines.append(f"Failing Commands: {', '.join(failing_commands)}")

        lines.append(f"Detected Defects ({len(defects)} item(s)):")
        for idx, d in enumerate(defects[:5], 1):
            file_loc = f" in '{d.affected_files[0]}'" if d.affected_files else ""
            lines.append(f"  [{idx}] [{d.category.value}] {d.message}{file_loc}")

        if len(defects) > 5:
            lines.append(f"  ... and {len(defects) - 5} additional defect(s)")

        return "\n".join(lines)
