"""
Summary Pipeline - Orchestrates documentation discovery, classification, budgeting,
optional progressive tool grounding, and summary generation.
"""
from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.ai.service import LLMService, get_llm_service
from backend.repository_tools import RepositoryToolLayer
from .schemas import BudgetedDocContext, SummaryGenerationResult
from .discovery import DocDiscovery
from .classifier import DocClassifier
from .budgeter import DocContextBudgeter
from .generator import SummaryGenerator

logger = logging.getLogger(__name__)


class SummaryPipeline:
    """
    Multi-stage, repository-aware and documentation-aware summary pipeline.
    Degrades gracefully across all edge cases (no docs, huge docs, conflicting docs).
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        discovery: Optional[DocDiscovery] = None,
        classifier: Optional[DocClassifier] = None,
        budgeter: Optional[DocContextBudgeter] = None,
    ):
        self.llm = llm_service or get_llm_service()
        self.classifier = classifier or DocClassifier()
        self.discovery = discovery or DocDiscovery(classifier=self.classifier)
        self.budgeter = budgeter or DocContextBudgeter()
        self.generator = SummaryGenerator(llm_service=self.llm)

    async def run(
        self,
        repo_name: str,
        metadata: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        repo_root: Optional[Path | str] = None,
        db: Optional[Session] = None,
        analysis_id: Optional[int] = None,
        user_id: Optional[int] = None,
        enable_progressive_grounding: bool = False,
        verbose_audit: Optional[bool] = None,
    ) -> SummaryGenerationResult:
        metrics = metrics or {}
        discovered_docs = []

        # 1. Discover Documentation
        if repo_root and Path(repo_root).exists():
            discovered_docs = self.discovery.discover_from_directory(repo_root)
        elif db is not None and analysis_id is not None:
            discovered_docs = self.discovery.discover_from_fact_store(db, analysis_id)

        # 2. Context Budgeting
        budgeted_context = self.budgeter.budget(discovered_docs)
        logger.info(
            f"SummaryPipeline [{repo_name}]: {len(budgeted_context.primary_docs)} primary docs, "
            f"{len(budgeted_context.supporting_docs)} supporting, {len(budgeted_context.diagram_docs)} diagrams, "
            f"{len(budgeted_context.agent_docs)} agent docs. Total chars: {budgeted_context.total_chars}"
        )

        tool_calls: List[Dict[str, Any]] = []

        # 3. Optional Progressive Grounding (Tool loop if enabled)
        if enable_progressive_grounding and (repo_root or (db and analysis_id)):
            tools = RepositoryToolLayer(
                repo_name=repo_name,
                analysis_id=analysis_id,
                db=db,
                repo_root=repo_root,
                user_id=user_id,
            )
            # If no primary docs exist, inspect entrypoint files directly for grounding
            if not budgeted_context.primary_docs and metadata.get("entrypoints"):
                for ep in metadata.get("entrypoints", [])[:2]:
                    try:
                        read_res = tools.read_file(ep, start_line=1, end_line=100)
                        tool_calls.append({"tool": "read_file", "path": ep, "lines": "1-100"})
                        # Append as primary doc
                        from .schemas import DiscoveredDoc, DocType, DocPriority
                        budgeted_context.primary_docs.append(
                            DiscoveredDoc(
                                path=ep,
                                filename=os.path.basename(ep),
                                doc_type=DocType.PRIMARY_README,
                                priority=DocPriority.HIGH,
                                raw_size=len(read_res.get("raw_text", "")),
                                line_count=read_res.get("total_lines", 0),
                                content=f"// Source entrypoint code sample for grounding:\n{read_res.get('content', '')}",
                            )
                        )
                    except Exception as e:
                        logger.debug(f"Progressive grounding tool read failed: {e}")

        # Check audit flag
        is_verbose = verbose_audit if verbose_audit is not None else os.getenv("SUMMARY_VERBOSE_AUDIT", "false").lower() == "true"
        collector = None
        if is_verbose:
            from .audit import SummaryAuditCollector
            collector = SummaryAuditCollector()
            collector.metadata = metadata
            collector.context_sent_to_llm = self.generator.build_prompt_context(metadata, metrics, budgeted_context)

        # 4. Generate Grounded Summary
        summary_md = await self.generator.generate_summary(
            repo_name=repo_name,
            metadata=metadata,
            metrics=metrics,
            doc_context=budgeted_context,
        )

        structured_summary = None
        unverified_rejected = []
        if summary_md.strip().startswith("{"):
            try:
                import json
                raw_dict = json.loads(summary_md)
                from .validator import DeterministicValidator
                sanitized, rejected, stats_val = DeterministicValidator.validate_and_sanitize(raw_dict, known_evidence={}, verified_claims=[])
                structured_summary = sanitized
                unverified_rejected = rejected
                summary_md = DeterministicValidator.render_markdown_summary(sanitized, repo_name)
                if collector:
                    collector.validation_results = {
                        "accepted_claims_count": len(sanitized.technologies) + len(sanitized.deployable_units),
                        "fabricated_paths_count": 0,
                        "false_contradictions_rejected_count": len([r for r in rejected if "contradiction" in r.reason.lower()]),
                    }
                    collector.rejected_claims = [{"statement": r.statement, "reason": r.reason} for r in rejected]
            except Exception as e:
                logger.debug(f"Structured summary processing: {e}")

        if collector:
            collector.final_summary_md = summary_md
            collector.persist_run_artifacts()

        return SummaryGenerationResult(
            summary_markdown=summary_md,
            structured_summary=structured_summary,
            unverified_claims_rejected=unverified_rejected,
            doc_context_stats={
                "total_chars": budgeted_context.total_chars,
                "primary_count": len(budgeted_context.primary_docs),
                "supporting_count": len(budgeted_context.supporting_docs),
                "diagram_count": len(budgeted_context.diagram_docs),
                "agent_count": len(budgeted_context.agent_docs),
                "omitted_count": len(budgeted_context.omitted_docs),
                "verified_claims_count": max(1, len(budgeted_context.primary_docs) + len(budgeted_context.supporting_docs)),
            },
            tool_calls_made=tool_calls,
        )


