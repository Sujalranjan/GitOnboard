"""
RIM Comparison Research Service v2 — Agentic Q&A loop-based comparison.

Orchestrates controlled experiments using sequential agentic loops instead of
single-shot retrieval. Both baseline and RIM sides use identical loop infrastructure
with only tool sets and system prompts differing.
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from backend.agent.loop.contracts import StopReason
from backend.ai.service import get_llm_service
from backend.ai.tokencount import count_tokens
from backend.config import settings
from backend.intelligence.retrieval import HybridRetriever
from backend.models.user import User
from backend.repository_tools import resolve_repo_root, RepositoryToolLayer
from backend.summary.audit import redact_secrets, sanitize_dict_or_list
from backend.services.qa_loop import QALoopResult
from backend.services.llm_analysis_service import build_analysis_service
from backend.services.rim_metadata import build_rim_metadata_block
from backend.logging import StructuredLogger
from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import ContextAssemblyRequest
from backend.agent.context.formatter import RepositoryContextFormatter

logger = logging.getLogger(__name__)


from backend.services.rim_comparison_models import (
    RetrievalMetrics,
    LLMEfficiencyMetrics,
    AnswerMetrics,
    ComparisonSide,
    RIMTrace,
    ContextDiff,
    RIMComparisonResult,
)
from backend.services.rim_comparison_metrics import (
    combine_context_blocks,
    assemble_comparison_side,
)

__all__ = [
    "RetrievalMetrics",
    "LLMEfficiencyMetrics",
    "AnswerMetrics",
    "ComparisonSide",
    "RIMTrace",
    "ContextDiff",
    "RIMComparisonResult",
    "RIMComparisonService",
    "combine_context_blocks",
    "assemble_comparison_side",
]


class RIMComparisonService:
    """Orchestrates controlled RIM-on/off comparison experiments using agentic loops."""

    def __init__(self, db: Session, repo_name: str, current_user: User):
        self.db = db
        self.repo_name = repo_name
        self.current_user = current_user
        self.llm_service = get_llm_service()

    async def get_shared_setup(self, question: str):
        """Shared setup for both baseline and RIM runs."""
        structured_log = StructuredLogger(
            session_id=self.current_user.id if self.current_user else "unknown",
            repository=self.repo_name
        )
        request_id = structured_log.log_query(question, self.current_user.email if self.current_user else None)

        from backend.routers.repo.services.analysis import get_latest_analysis
        from backend.routers.repo.semantic import get_chroma_collection

        repo, analysis = get_latest_analysis(self.repo_name, self.db, self.current_user)
        analysis_id = analysis.id

        chroma_collection = None
        try:
            chroma_collection = get_chroma_collection(self.repo_name, self.current_user, self.db)
        except Exception as e:
            logger.debug(f"Chroma collection not available: {e}")

        retriever = HybridRetriever(
            db=self.db,
            analysis_id=analysis_id,
            chroma_collection=chroma_collection,
            rrf_k=60,
            enable_graph_expansion=True,
            graph_expansion_depth=2,
            graph_expansion_nodes_per_hop=3,
            graph_expansion_max_total=30,
        )

        repo_root = resolve_repo_root(self.repo_name, self.current_user.id, self.db)
        tool_layer = RepositoryToolLayer(
            repo_name=self.repo_name,
            analysis_id=analysis_id,
            db=self.db,
            repo_root=repo_root,
            user_id=self.current_user.id
        )

        logger.info(f"[RIM Comparison] Assembling repository context for: {question}")
        t0_ctx = time.perf_counter()
        assembler = ContextAssembler()
        context_request = ContextAssemblyRequest(
            repository_id=self.repo_name,
            requirement=question,
            analysis_id=analysis_id,
            worktree_path=repo_root,
        )
        repository_context = assembler.assemble(context_request, db=self.db)
        context_elapsed_ms = (time.perf_counter() - t0_ctx) * 1000

        formatter = RepositoryContextFormatter()

        def file_reader(file_path: str) -> Optional[str]:
            try:
                result = tool_layer.read_file(file_path)
                if result and isinstance(result, dict):
                    return result.get('raw_text') or result.get('content')
                elif isinstance(result, str):
                    return result
                return None
            except Exception as e:
                logger.debug(f"Failed to read {file_path}: {e}")
                return None

        repository_context_block = formatter.format_to_system_prompt_block(
            repository_context,
            max_chars=6000,
            include_evidence_provenance=False,
            file_reader=file_reader,
        )

        return {
            'structured_log': structured_log,
            'request_id': request_id,
            'analysis_id': analysis_id,
            'retriever': retriever,
            'tool_layer': tool_layer,
            'repository_context_block': repository_context_block,
        }

    async def run_baseline_only(self, question: str, setup: dict):
        """Run baseline analysis only and return comparison side."""
        logger.info(f"[RIM Comparison] Running baseline (no RIM) for: {question}")

        # Select model and provider based on deployment mode
        baseline_model = (
            settings.openrouter_model if settings.deployment_type == "PROD"
            else settings.model_local_default  # Use default Qwen model for LOCAL (qwen3:4b-instruct)
        )
        baseline_provider = "openrouter" if settings.deployment_type == "PROD" else "ollama"

        baseline_analysis_service = build_analysis_service(
            llm_service=self.llm_service,
            db=self.db,
            repo_name=self.repo_name,
            analysis_id=setup['analysis_id'],
            user_id=self.current_user.id,
            model=baseline_model,
            provider=baseline_provider,
            tool_layer=setup['tool_layer'],
            rim_metadata_block=setup['repository_context_block'],
            structured_logger=setup['structured_log'],
            request_id=setup['request_id'],
            repository=self.repo_name,
            mode="baseline",
        )

        t0 = time.perf_counter()
        baseline_result = await baseline_analysis_service.run(question, include_rim=False)
        baseline_elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            f"[RIM Comparison] Baseline complete: {len(baseline_result.turns)} turns, "
            f"{baseline_result.tool_call_count} tool calls, stop_reason={baseline_result.stop_reason}"
        )

        return await self._assemble_comparison_side(
            question, baseline_result, baseline_analysis_service.last_prompt_parts, baseline_elapsed_ms,
            rim_metadata_block=setup['repository_context_block'],
            retriever=setup['retriever']
        )

    async def run_rim_only(self, question: str, setup: dict, repository_context_block: str):
        """Run RIM analysis only and return comparison side."""
        logger.info(f"[RIM Comparison] Building RIM metadata block...")
        t0_meta = time.perf_counter()
        rim_metadata = build_rim_metadata_block(
            self.db, setup['analysis_id'], question, setup['retriever'],
            max_seed_entities=3, max_related_per_seed=8, max_block_chars=4000
        )
        metadata_elapsed_ms = (time.perf_counter() - t0_meta) * 1000
        logger.info(f"[RIM Comparison] RIM metadata built in {metadata_elapsed_ms:.1f}ms")

        combined_rim_block = self._combine_context_blocks(repository_context_block, rim_metadata.text)
        logger.info(f"[RIM Comparison] Running RIM analysis for: {question}")

        # Select model and provider based on deployment mode
        rim_model = (
            settings.gemini_model if settings.deployment_type == "PROD"
            else settings.model_local_default  # Use same default Qwen model for LOCAL
        )
        rim_provider = "gemini" if settings.deployment_type == "PROD" else "ollama"

        rim_analysis_service = build_analysis_service(
            llm_service=self.llm_service,
            db=self.db,
            repo_name=self.repo_name,
            analysis_id=setup['analysis_id'],
            user_id=self.current_user.id,
            model=rim_model,
            provider=rim_provider,
            tool_layer=setup['tool_layer'],
            rim_metadata_block=combined_rim_block,
            structured_logger=setup['structured_log'],
            request_id=setup['request_id'],
            repository=self.repo_name,
            mode="rim",
        )

        t0 = time.perf_counter()
        rim_result = await rim_analysis_service.run(question, include_rim=True)
        rim_elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            f"[RIM Comparison] RIM complete: {len(rim_result.turns)} turns, "
            f"{rim_result.tool_call_count} tool calls, stop_reason={rim_result.stop_reason}"
        )

        return await self._assemble_comparison_side(
            question, rim_result, rim_analysis_service.last_prompt_parts, rim_elapsed_ms,
            rim_metadata_block=combined_rim_block,
            retriever=setup['retriever']
        ), rim_metadata

    async def run_comparison(self, question: str) -> RIMComparisonResult:
        """
        Runs the same question through two identical agentic loops,
        differing only in whether RIM metadata + query_rim tool are available.

        Both sides use identical guardrails, retrieval tools, and LLM model.
        Only difference: RIM side has upfront metadata block + query_rim tool.
        """
        # Initialize structured logger for this session
        structured_log = StructuredLogger(
            session_id=self.current_user.id if self.current_user else "unknown",
            repository=self.repo_name
        )

        # Log incoming query (returns request_id)
        request_id = structured_log.log_query(question, self.current_user.email if self.current_user else None)

        # Late binding to avoid circular imports
        from backend.routers.repo.services.analysis import get_latest_analysis
        from backend.routers.repo.semantic import get_chroma_collection

        # 1. Resolve repo, analysis, chroma collection
        try:
            repo, analysis = get_latest_analysis(self.repo_name, self.db, self.current_user)
            analysis_id = analysis.id
        except Exception as e:
            logger.error(f"Failed to resolve repo/analysis for {self.repo_name}: {e}")
            structured_log.log_error("analysis_resolution", e, {"repository": self.repo_name})
            raise

        chroma_collection = None
        try:
            chroma_collection = get_chroma_collection(self.repo_name, self.current_user, self.db)
        except Exception as e:
            logger.debug(f"Chroma collection not available: {e}")

        # Initialize retriever (shared between both runs, seed identification only)
        # Enable graph expansion for RIM to find connected repository entities
        retriever = HybridRetriever(
            db=self.db,
            analysis_id=analysis_id,
            chroma_collection=chroma_collection,
            rrf_k=60,
            enable_graph_expansion=True,
            graph_expansion_depth=2,
            graph_expansion_nodes_per_hop=3,
            graph_expansion_max_total=30,
        )

        # Initialize repository tool layer (shared)
        try:
            repo_root = resolve_repo_root(self.repo_name, self.current_user.id, self.db)
            tool_layer = RepositoryToolLayer(
                repo_name=self.repo_name,
                analysis_id=analysis_id,
                db=self.db,
                repo_root=repo_root,
                user_id=self.current_user.id
            )
        except Exception as e:
            logger.error(f"Failed to initialize RepositoryToolLayer: {e}")
            raise

        # 2. Assemble repository context using ContextAssembler
        logger.info(f"[RIM Comparison] Assembling repository context for: {question}")
        t0_ctx = time.perf_counter()
        assembler = ContextAssembler()
        context_request = ContextAssemblyRequest(
            repository_id=self.repo_name,
            requirement=question,
            analysis_id=analysis_id,
            worktree_path=repo_root,
        )
        repository_context = assembler.assemble(context_request, db=self.db)
        context_elapsed_ms = (time.perf_counter() - t0_ctx) * 1000
        logger.info(
            f"[RIM Comparison] Repository context assembled in {context_elapsed_ms:.1f}ms: "
            f"{len(repository_context.evidence)} evidence items, "
            f"completeness={repository_context.contract.completeness.value}"
        )

        # Format context for system prompt injection
        formatter = RepositoryContextFormatter()

        # Create file reader that uses RepositoryToolLayer to read source code
        def file_reader(file_path: str) -> Optional[str]:
            try:
                result = tool_layer.read_file(file_path)
                if result and isinstance(result, dict):
                    return result.get('raw_text') or result.get('content')
                elif isinstance(result, str):
                    return result
                return None
            except Exception as e:
                logger.debug(f"Failed to read {file_path}: {e}")
                return None

        repository_context_block = formatter.format_to_system_prompt_block(
            repository_context,
            max_chars=6000,
            include_evidence_provenance=False,
            file_reader=file_reader,
        )

        # 3. RUN BASELINE — with repository context (no RIM relationships)
        logger.info(f"[RIM Comparison] Running baseline (no RIM) for: {question}")

        # Select model and provider based on deployment mode
        baseline_model = (
            settings.openrouter_model if settings.deployment_type == "PROD"
            else settings.model_local_default  # Use default Qwen model for LOCAL (qwen3:4b-instruct)
        )
        baseline_provider = "openrouter" if settings.deployment_type == "PROD" else "ollama"

        baseline_analysis_service = build_analysis_service(
            llm_service=self.llm_service,
            db=self.db,
            repo_name=self.repo_name,
            analysis_id=analysis_id,
            user_id=self.current_user.id,
            model=baseline_model,
            provider=baseline_provider,
            tool_layer=tool_layer,
            rim_metadata_block=repository_context_block,
            structured_logger=structured_log,
            request_id=request_id,
            repository=self.repo_name,
            mode="baseline",
        )

        t0 = time.perf_counter()
        baseline_result = await baseline_analysis_service.run(question, include_rim=False)
        baseline_elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            f"[RIM Comparison] Baseline complete: {len(baseline_result.turns)} turns, "
            f"{baseline_result.tool_call_count} tool calls, "
            f"stop_reason={baseline_result.stop_reason}"
        )

        # 4. RUN RIM — with repository context + RIM relationships + query_rim tool
        logger.info(f"[RIM Comparison] Building RIM metadata block...")
        t0_meta = time.perf_counter()
        rim_metadata = build_rim_metadata_block(
            self.db, analysis_id, question, retriever,
            max_seed_entities=3, max_related_per_seed=8, max_block_chars=4000
        )
        metadata_elapsed_ms = (time.perf_counter() - t0_meta) * 1000
        logger.info(f"[RIM Comparison] RIM metadata built in {metadata_elapsed_ms:.1f}ms")

        # Combine repository context with RIM metadata for RIM side
        combined_rim_block = self._combine_context_blocks(repository_context_block, rim_metadata.text)

        logger.info(f"[RIM Comparison] Running RIM comparison for: {question}")

        # Select model and provider based on deployment mode
        rim_model = (
            settings.gemini_model if settings.deployment_type == "PROD"
            else settings.model_local_default  # Use same default Qwen model for LOCAL
        )
        rim_provider = "gemini" if settings.deployment_type == "PROD" else "ollama"

        rim_analysis_service = build_analysis_service(
            llm_service=self.llm_service,
            db=self.db,
            repo_name=self.repo_name,
            analysis_id=analysis_id,
            user_id=self.current_user.id,
            model=rim_model,
            provider=rim_provider,
            tool_layer=tool_layer,
            rim_metadata_block=combined_rim_block,
            structured_logger=structured_log,
            request_id=request_id,
            repository=self.repo_name,
            mode="rim",
        )

        t0 = time.perf_counter()
        rim_result = await rim_analysis_service.run(question, include_rim=True)
        rim_elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            f"[RIM Comparison] RIM complete: {len(rim_result.turns)} turns, "
            f"{rim_result.tool_call_count} tool calls, "
            f"stop_reason={rim_result.stop_reason}"
        )

        # 5. Compute token accounting for both sides
        logger.info("[RIM Comparison] Computing token accounting...")

        baseline_side = await self._assemble_comparison_side(
            question, baseline_result, baseline_analysis_service.last_prompt_parts, baseline_elapsed_ms,
            rim_metadata_block=repository_context_block,
            retriever=retriever
        )
        rim_side = await self._assemble_comparison_side(
            question, rim_result, rim_analysis_service.last_prompt_parts, rim_elapsed_ms,
            rim_metadata_block=combined_rim_block,
            retriever=retriever
        )

        # 6. Build result
        all_baseline_files = set(baseline_result.files_read)
        all_rim_files = set(rim_result.files_read)

        # Build comprehensive RIM trace showing navigation flow
        # Populate from rim_metadata which now includes graph expansion tracking
        rim_trace = RIMTrace(
            enabled=True,
            query=question,
            anchor_count=len(rim_metadata.anchor_entities),
            anchors=rim_metadata.anchor_entities,
            expansion_count=rim_metadata.total_nodes_expanded,
            expanded_entities=rim_metadata.expanded_entities,
            graph_depth=rim_metadata.expansion_depth,
            total_nodes_expanded=rim_metadata.total_nodes_expanded,
            relationship_types=list(set(r.get("type", "") for r in rim_metadata.relationships if r.get("type"))),
            relationships=rim_metadata.relationships,
            selected_files=[],  # Will be populated from context assembly
            selected_symbols=[],  # Will be populated from context assembly
            source_locations=[],  # Will be populated from source reader
            # Legacy fields (preserved for backward compatibility)
            rim_metadata_seed_entities=rim_metadata.seed_entities,
            rim_metadata_relationships=rim_metadata.relationships,
            query_rim_call_log=rim_result.rim_entities_accessed
        )

        result = RIMComparisonResult(
            without_rim=baseline_side,
            with_rim=rim_side,
            repository=self.repo_name,
            branch=getattr(analysis, "branch", None),
            commit=getattr(analysis, "commit_hash", None),
            analysis_id=analysis_id,
            context_diff=ContextDiff(
                files_only_without_rim=sorted(list(all_baseline_files - all_rim_files)),
                shared_files=sorted(list(all_baseline_files & all_rim_files)),
                files_only_with_rim=sorted(list(all_rim_files - all_baseline_files))
            ),
            trace=rim_trace
        )

        # Log metrics before returning
        baseline_metrics = baseline_side.retrieval_metrics
        rim_metrics = rim_side.retrieval_metrics
        structured_log.log_metrics(
            question=question,
            baseline_metrics={
                "tool_call_count": baseline_metrics.tool_call_count,
                "files_retrieved": baseline_metrics.files_retrieved,
                "symbols_retrieved": baseline_metrics.symbols_retrieved,
                "retrieval_latency_ms": baseline_metrics.retrieval_latency_ms
            },
            rim_metrics={
                "tool_call_count": rim_metrics.tool_call_count,
                "files_retrieved": rim_metrics.files_retrieved,
                "symbols_retrieved": rim_metrics.symbols_retrieved,
                "rim_entities_accessed_count": rim_metrics.rim_entities_accessed_count,
                "retrieval_latency_ms": rim_metrics.retrieval_latency_ms,
                "semantic_degradation": rim_metrics.semantic_degradation
            },
            failure_detected=False
        )

        # Log completion
        structured_log.log_completion(
            success=True,
            summary={
                "repository": self.repo_name,
                "analysis_id": analysis_id,
                "baseline_turns": len(baseline_result.turns),
                "rim_turns": len(rim_result.turns),
                "baseline_tool_calls": baseline_result.tool_call_count,
                "rim_tool_calls": rim_result.tool_call_count,
                "files_in_context": len(all_baseline_files | all_rim_files)
            }
        )

        logger.info(f"[RIM Comparison] Complete: {self.repo_name}, {analysis_id}")
        return result

    async def _assemble_comparison_side(
        self,
        question: str,
        loop_result: QALoopResult,
        prompt_parts,
        elapsed_ms: float,
        rim_metadata_block: Optional[str] = None,
        retriever: Optional[HybridRetriever] = None,
    ) -> ComparisonSide:
        """Assemble ComparisonSide from loop result with token accounting."""
        return await assemble_comparison_side(
            question=question,
            loop_result=loop_result,
            prompt_parts=prompt_parts,
            elapsed_ms=elapsed_ms,
            rim_metadata_block=rim_metadata_block,
            retriever=retriever,
        )

    @staticmethod
    def _combine_context_blocks(repository_context_block: str, rim_metadata_block: str) -> str:
        """Combine repository context and RIM metadata blocks for RIM side."""
        return combine_context_blocks(repository_context_block, rim_metadata_block)
