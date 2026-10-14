"""
Persistent Investigation State and Evidence Store for GitOnBoard.

Preserves task progress, evidence cards, visited files, and technical findings outside
LLM message contexts. Operates in-memory and can persist to PostgreSQL Fact Store.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.agent.investigation.schemas import (
    EvidenceCard,
    FindingType,
    InvestigationSubtask,
    SubtaskStatus,
    WorkerTaskResult,
)
from backend.models.fact_store import FactEvidence

logger = logging.getLogger(__name__)


class InvestigationStateStore:
    """
    Persistent store managing investigation tasks and structured evidence cards.
    """

    def __init__(self, investigation_id: str, db: Optional[Session] = None, analysis_id: Optional[int] = None, query: str = ""):
        self.investigation_id = investigation_id
        self.db = db
        self.analysis_id = analysis_id
        self.query = query
        self.tasks: Dict[str, InvestigationSubtask] = {}
        self.evidence: Dict[str, EvidenceCard] = {}
        self.inspected_files: set[str] = set()
        self.files_read: set[str] = set()
        self.files_discovered: set[str] = set()
        self.files_skipped: List[Dict[str, str]] = []
        self.read_failures: List[Dict[str, str]] = []
        self.coverage_gaps: List[str] = []
        self.turns_history: List[Any] = []  # stores QALoopTurn objects for validation

    def create_task(
        self,
        task_id: str,
        title: str,
        description: str,
        target_entities: Optional[List[str]] = None,
        search_strategy: str = "",
        expected_output: str = "",
        completion_criteria: str = "",
        dependencies: Optional[List[str]] = None,
    ) -> InvestigationSubtask:
        """Create and track a new investigation subtask."""
        task = InvestigationSubtask(
            id=task_id,
            title=title,
            description=description,
            target_entities=target_entities or [],
            search_strategy=search_strategy,
            expected_output=expected_output,
            completion_criteria=completion_criteria,
            dependencies=dependencies or [],
            status=SubtaskStatus.PENDING,
        )
        self.tasks[task_id] = task
        return task

    def update_task_status(
        self,
        task_id: str,
        status: SubtaskStatus,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> Optional[InvestigationSubtask]:
        """Update the status of an existing task."""
        task = self.tasks.get(task_id)
        if not task:
            return None
        task.status = status
        if error:
            task.error = error
        if duration_ms > 0:
            task.duration_ms = duration_ms
        return task

    def save_finding(self, card: EvidenceCard) -> None:
        """Save a single evidence card to state and optional DB persistence."""
        self.evidence[card.id] = card
        if card.file_path:
            self.inspected_files.add(card.file_path)

        # Attach to corresponding subtask
        if card.task_id and card.task_id in self.tasks:
            self.tasks[card.task_id].findings.append(card)

        # Optional PostgreSQL persistence into FactEvidence
        if self.db and self.analysis_id:
            try:
                db_ev = FactEvidence(
                    id=f"{self.analysis_id}:{card.id}",
                    analysis_id=self.analysis_id,
                    fact_type=card.finding_type.value,
                    symbol_id=card.symbol_name,
                    location=f"{card.file_path}:{card.line_start or 1}-{card.line_end or 1}",
                    details={
                        "summary": card.summary,
                        "code_excerpt": card.code_excerpt,
                        "confidence": card.confidence,
                        "discovered_dependencies": card.discovered_dependencies,
                        "investigation_id": self.investigation_id,
                        "task_id": card.task_id,
                    },
                )
                self.db.add(db_ev)
                self.db.commit()
            except Exception as e:
                logger.warning(f"[InvestigationStore] Failed to persist FactEvidence: {e}")
                self.db.rollback()

    def record_worker_result(self, result: WorkerTaskResult) -> None:
        """Incorporate worker execution results and file inspection transparency into persistent state."""
        self.update_task_status(result.task_id, result.status, error=result.error, duration_ms=result.duration_ms)
        for f in result.files_inspected:
            self.inspected_files.add(f)
        for f in result.files_read:
            self.files_read.add(f)
        for f in result.files_discovered:
            self.files_discovered.add(f)
        for skip in result.files_skipped:
            if skip not in self.files_skipped:
                self.files_skipped.append(skip)
        for fail in result.read_failures:
            if fail not in self.read_failures:
                self.read_failures.append(fail)
        for gap in result.coverage_gaps:
            if gap not in self.coverage_gaps:
                self.coverage_gaps.append(gap)
        for card in result.findings:
            self.save_finding(card)

    def get_ready_tasks(self) -> List[InvestigationSubtask]:
        """Return tasks whose dependencies have all completed."""
        ready = []
        completed_ids = {t.id for t in self.tasks.values() if t.status == SubtaskStatus.COMPLETED}
        for t in self.tasks.values():
            if t.status == SubtaskStatus.PENDING:
                if not t.dependencies or all(dep in completed_ids for dep in t.dependencies):
                    ready.append(t)
        return ready

    def get_all_findings(self) -> List[EvidenceCard]:
        """Return all discovered evidence cards."""
        return list(self.evidence.values())

    def get_findings_for_tasks(self, task_ids: List[str]) -> List[EvidenceCard]:
        """Return findings discovered by specific tasks."""
        return [c for c in self.evidence.values() if c.task_id in task_ids]

    def format_evidence_dossier(self, max_chars: int = 24000) -> str:
        """
        Format a structured Markdown evidence dossier for the Main LLM synthesizer.
        Includes verified findings, file inspection transparency, and coverage gaps.
        """
        sections: List[str] = []

        if not self.evidence:
            sections.append("### Verified Repository Findings:\nNo verified code findings were recorded.")
        else:
            lines = ["### Verified Repository Findings:\n"]
            # Deduplicate findings by (file_path, line_start, line_end, summary)
            seen_findings = set()
            deduped_cards = []
            for card in self.evidence.values():
                dedup_key = (card.file_path, card.line_start, card.line_end, card.summary.strip().lower())
                if dedup_key not in seen_findings:
                    seen_findings.add(dedup_key)
                    deduped_cards.append(card)

            for card in deduped_cards:
                loc = card.file_path
                if card.line_start and card.line_end:
                    loc += f" (lines {card.line_start}-{card.line_end})"
                elif card.line_start:
                    loc += f" (line {card.line_start})"

                lines.append(f"- **{loc}** [{card.finding_type.value}]: {card.summary}")
                if card.symbol_name:
                    lines.append(f"  * Symbol: `{card.symbol_name}`")
                if card.code_excerpt:
                    excerpt_clean = card.code_excerpt.strip().replace("\n", " ")
                    lines.append(f"  * Excerpt: `{excerpt_clean}`")
                if card.discovered_dependencies:
                    lines.append(f"  * Discovered dependencies: {', '.join(card.discovered_dependencies)}")
            sections.append("\n".join(lines))

        # Contradictions or Discrepancies if recorded
        contradictions = [g for g in self.coverage_gaps if "contradict" in g.lower() or "discrepancy" in g.lower()]
        if contradictions:
            sections.append("### Contradictions & Discrepancies Detected:\n" + "\n".join(f"- {c}" for c in contradictions))

        # File Inspection Transparency & Unresolved Questions
        transparency_lines = ["\n### File Inspection Transparency & Coverage:"]
        if self.files_read:
            transparency_lines.append(f"- **Files Read ({len(self.files_read)}):** " + ", ".join(sorted(self.files_read)[:25]))
        if self.files_discovered:
            transparency_lines.append(f"- **Files Discovered via Search ({len(self.files_discovered)}):** " + ", ".join(sorted(self.files_discovered)[:25]))
        if self.files_skipped:
            skip_desc = [f"{s.get('path', '')} ({s.get('reason', '')})" for s in self.files_skipped[:10]]
            transparency_lines.append(f"- **Relevant Files Skipped ({len(self.files_skipped)}):** " + "; ".join(skip_desc))
        if self.read_failures:
            fail_desc = [f"{f.get('path', '')}: {f.get('error', '')}" for f in self.read_failures[:10]]
            transparency_lines.append(f"- **Read Failures ({len(self.read_failures)}):** " + "; ".join(fail_desc))

        unresolved = [g for g in self.coverage_gaps if g not in contradictions]
        if unresolved:
            transparency_lines.append(f"- **Unresolved Questions & Coverage Gaps:** " + "; ".join(unresolved))

        sections.append("\n".join(transparency_lines))

        dossier = "\n\n".join(sections)
        # Avoid silently truncating critical findings; if exceeding max_chars, preserve all findings and cap ancillary lists
        if len(dossier) > max_chars:
            dossier = dossier[:max_chars] + "\n... [Ancillary inspection details capped for context budget; all verified findings above preserved] ..."
        return dossier

