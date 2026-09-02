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

from backend.agent.loop.contracts import AgentLoopConfig, StopReason
from backend.ai.service import get_llm_service
from backend.ai.tokencount import count_tokens
from backend.intelligence.retrieval import HybridRetriever
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from backend.models.user import User
from backend.repository_tools import resolve_repo_root, RepositoryToolLayer
from backend.summary.audit import redact_secrets, sanitize_dict_or_list
from backend.services.rim_qa_loop import RIMQALoop, QALoopResult
from backend.services.rim_qa_protocol import QAProtocolAdapter
from backend.services.rim_tool_dispatch import ToolDispatchTable, TargetEntityResolver
from backend.services.rim_metadata import build_rim_metadata_block

logger = logging.getLogger(__name__)


@dataclass
class RetrievalMetrics:
    """Retrieval-phase metrics."""
    tool_call_count: int = 0
    files_retrieved: int = 0
    symbols_retrieved: int = 0
    rim_entities_accessed_count: int = 0
    rim_relationship_types_used: List[str] = field(default_factory=list)
    retrieval_latency_ms: float = 0.0
    semantic_degradation: Optional[str] = None  # Reason semantic search unavailable, if any


@dataclass
class LLMEfficiencyMetrics:
    """LLM execution and token metrics (actual + estimated breakdown)."""
    provider: str = ""
    model: str = ""
    actual_prompt_tokens: int = 0
    actual_completion_tokens: int = 0
    actual_total_tokens: int = 0
    estimated_system_tokens: int = 0
    estimated_rim_tokens: int = 0
    estimated_source_tokens: int = 0
    estimated_other_tokens: int = 0
    token_estimation_method: str = "heuristic"
    token_estimation_is_approximate: bool = True
    token_reconciliation_diff: int = 0
    llm_latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    token_counting_latency_ms: float = 0.0
    total_latency_ms: float = 0.0


@dataclass
class AnswerMetrics:
    """Holder for manual quality evaluation (auto-filled with None for UI scaffolding)."""
    correctness: Optional[str] = None
    grounding: Optional[str] = None
    notes: str = ""


@dataclass
class ComparisonSide:
    """Result of one pipeline (with or without RIM)."""
    answer: str
    retrieval_metrics: RetrievalMetrics
    llm_efficiency_metrics: LLMEfficiencyMetrics
    answer_metrics: AnswerMetrics
    rim_metadata_block: Optional[str] = None  # None for baseline, facts text for RIM
    source_context_block: str = ""
    tool_call_transcript: List[Dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""


@dataclass
class RIMTrace:
    """Execution trace: RIM metadata and query_rim call log."""
    rim_metadata_seed_entities: List[Dict[str, Any]] = field(default_factory=list)
    rim_metadata_relationships: List[Dict[str, Any]] = field(default_factory=list)
    query_rim_call_log: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ContextDiff:
    """Files retrieved, grouped by side."""
    files_only_without_rim: List[str] = field(default_factory=list)
    shared_files: List[str] = field(default_factory=list)
    files_only_with_rim: List[str] = field(default_factory=list)


@dataclass
class RIMComparisonResult:
    """Complete comparison result for frontend consumption."""
    without_rim: ComparisonSide
    with_rim: ComparisonSide
    repository: str
    branch: Optional[str] = None
    commit: Optional[str] = None
    analysis_id: Optional[int] = None
    context_diff: ContextDiff = field(default_factory=ContextDiff)
    trace: RIMTrace = field(default_factory=RIMTrace)


class RIMComparisonService:
    """Orchestrates controlled RIM-on/off comparison experiments using agentic loops."""

    def __init__(self, db: Session, repo_name: str, current_user: User):
        self.db = db
        self.repo_name = repo_name
        self.current_user = current_user
        self.llm_service = get_llm_service()

    async def run_comparison(self, question: str) -> RIMComparisonResult:
        """
        Runs the same question through two identical agentic loops,
        differing only in whether RIM metadata + query_rim tool are available.

        Both sides use identical guardrails, retrieval tools, and LLM model.
        Only difference: RIM side has upfront metadata block + query_rim tool.
        """
        # Late binding to avoid circular imports
        from backend.routers.repo.services.analysis import get_latest_analysis
        from backend.routers.repo.semantic import get_chroma_collection

        # 1. Resolve repo, analysis, chroma collection
        try:
            repo, analysis = get_latest_analysis(self.repo_name, self.db, self.current_user)
            analysis_id = analysis.id
        except Exception as e:
            logger.error(f"Failed to resolve repo/analysis for {self.repo_name}: {e}")
            raise

        chroma_collection = None
        try:
            chroma_collection = get_chroma_collection(self.repo_name, self.current_user, self.db)
        except Exception as e:
            logger.debug(f"Chroma collection not available: {e}")

        # Initialize retriever (shared between both runs, seed identification only)
        retriever = HybridRetriever(
            db=self.db,
            analysis_id=analysis_id,
            chroma_collection=chroma_collection,
            rrf_k=60
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

        # 2. Configure agentic loop guardrails
        config = AgentLoopConfig(
            max_agent_turns=12,
            max_tool_calls=15,
            max_command_executions=0,
            max_execution_seconds=180,
            max_observation_bytes=8000,
            max_repeated_tool_calls=3
        )

        # 3. RUN BASELINE — no RIM metadata, no query_rim tool
        logger.info(f"[RIM Comparison] Running baseline (no RIM) for: {question}")
        baseline_dispatch = ToolDispatchTable(tool_layer)  # No RIM tools
        baseline_protocol = QAProtocolAdapter()
        baseline_prompt_parts = baseline_protocol.build_system_prompt(
            tool_specs=baseline_dispatch.specs(include_rim=False),
            rim_metadata_block=None
        )
        baseline_loop = RIMQALoop(
            llm_service=self.llm_service,
            tool_dispatch=baseline_dispatch,
            config=config,
            system_prompt_parts=baseline_prompt_parts
        )

        t0 = time.perf_counter()
        baseline_result = await baseline_loop.run(question)
        baseline_elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            f"[RIM Comparison] Baseline complete: {len(baseline_result.turns)} turns, "
            f"{baseline_result.tool_call_count} tool calls, "
            f"stop_reason={baseline_result.stop_reason}"
        )

        # 4. RUN RIM — with metadata block + query_rim tool
        logger.info(f"[RIM Comparison] Building RIM metadata block...")
        t0_meta = time.perf_counter()
        rim_metadata = build_rim_metadata_block(
            self.db, analysis_id, question, retriever,
            max_seed_entities=3, max_related_per_seed=8, max_block_chars=4000
        )
        metadata_elapsed_ms = (time.perf_counter() - t0_meta) * 1000
        logger.info(f"[RIM Comparison] RIM metadata built in {metadata_elapsed_ms:.1f}ms")

        logger.info(f"[RIM Comparison] Running RIM comparison for: {question}")
        graph_traverser = FactStoreGraphTraverser(self.db, analysis_id)
        target_resolver = TargetEntityResolver(self.db, analysis_id)
        rim_dispatch = ToolDispatchTable(tool_layer, graph_traverser, target_resolver)
        rim_protocol = QAProtocolAdapter()
        rim_prompt_parts = rim_protocol.build_system_prompt(
            tool_specs=rim_dispatch.specs(include_rim=True),
            rim_metadata_block=rim_metadata.text
        )
        rim_loop = RIMQALoop(
            llm_service=self.llm_service,
            tool_dispatch=rim_dispatch,
            config=config,
            system_prompt_parts=rim_prompt_parts
        )

        t0 = time.perf_counter()
        rim_result = await rim_loop.run(question)
        rim_elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            f"[RIM Comparison] RIM complete: {len(rim_result.turns)} turns, "
            f"{rim_result.tool_call_count} tool calls, "
            f"stop_reason={rim_result.stop_reason}"
        )

        # 5. Compute token accounting for both sides
        logger.info("[RIM Comparison] Computing token accounting...")

        baseline_side = await self._assemble_comparison_side(
            question, baseline_result, baseline_prompt_parts, baseline_elapsed_ms,
            retriever=retriever
        )
        rim_side = await self._assemble_comparison_side(
            question, rim_result, rim_prompt_parts, rim_elapsed_ms,
            rim_metadata_block=rim_metadata.text,
            retriever=retriever
        )

        # 6. Build result
        all_baseline_files = set(baseline_result.files_read)
        all_rim_files = set(rim_result.files_read)

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
            trace=RIMTrace(
                rim_metadata_seed_entities=rim_metadata.seed_entities,
                rim_metadata_relationships=rim_metadata.relationships,
                query_rim_call_log=rim_result.rim_entities_accessed
            )
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

        # Compute token accounting
        actual_prompt_tokens = sum(turn.prompt_tokens for turn in loop_result.turns)
        actual_completion_tokens = sum(turn.completion_tokens for turn in loop_result.turns)
        actual_total_tokens = actual_prompt_tokens + actual_completion_tokens

        # Estimate token breakdown
        t0_counting = time.perf_counter()

        estimated_system = await count_tokens(prompt_parts.grounding_and_protocol_text, "ollama", "qwen")
        estimated_other = await count_tokens(prompt_parts.tool_catalog_text + question, "ollama", "qwen")
        estimated_rim = await count_tokens(rim_metadata_block or "", "ollama", "qwen") if rim_metadata_block else None

        # Source tokens are estimated by accumulating tool observations
        source_texts = []
        for turn in loop_result.turns:
            if turn.tool_observation:
                # Use formatted message (actual text sent to LLM) for source token estimation
                obs = turn.tool_observation
                if obs.get("error"):
                    source_texts.append(str(obs.get("error")))
                else:
                    # Use the formatted message that was actually sent to the LLM
                    formatted_msg = obs.get("formatted_message", "")
                    if formatted_msg:
                        source_texts.append(formatted_msg)

        estimated_source = await count_tokens("\n".join(source_texts), "ollama", "qwen") if source_texts else None

        token_counting_ms = (time.perf_counter() - t0_counting) * 1000

        # Reconciliation
        est_total = (estimated_system.count if estimated_system else 0) + \
                   (estimated_other.count if estimated_other else 0) + \
                   (estimated_rim.count if estimated_rim else 0) + \
                   (estimated_source.count if estimated_source else 0)
        reconciliation_diff = actual_prompt_tokens - est_total

        # Build source context block (concatenation of actual tool observations sent to LLM)
        source_context_lines = []
        for turn in loop_result.turns:
            if turn.tool_call and turn.tool_observation:
                tool_name = turn.tool_call.get("tool_name", "")
                # Use formatted message that was actually sent to the LLM
                obs = turn.tool_observation.get("formatted_message", "")
                if obs:
                    source_context_lines.append(f"{obs[:500]}")

        source_context_block = "\n".join(source_context_lines[:100])  # Cap at 100 lines

        # Build tool call transcript
        tool_call_transcript = [
            {
                "turn": turn.turn_index,
                "tool_name": turn.tool_call.get("tool_name", "") if turn.tool_call else None,
                "arguments": turn.tool_call.get("arguments", {}) if turn.tool_call else {},
                "observation_summary": turn.tool_observation.get("formatted_message", "") if turn.tool_observation else ""
            }
            for turn in loop_result.turns
            if turn.tool_call
        ]

        return ComparisonSide(
            answer=loop_result.answer,
            retrieval_metrics=RetrievalMetrics(
                tool_call_count=loop_result.tool_call_count,
                files_retrieved=len(loop_result.files_read),
                symbols_retrieved=len(loop_result.symbols_read),
                rim_entities_accessed_count=len(loop_result.rim_entities_accessed),
                rim_relationship_types_used=loop_result.rim_relationship_types_used,
                retrieval_latency_ms=loop_result.latency_ms.get("tool_total", 0),  # Actual tool execution time only
                semantic_degradation=retriever.semantic_degradation if retriever and hasattr(retriever, 'semantic_degradation') else None
            ),
            llm_efficiency_metrics=LLMEfficiencyMetrics(
                provider=loop_result.turns[0].provider if loop_result.turns else "",
                model=loop_result.turns[0].model if loop_result.turns else "",
                actual_prompt_tokens=actual_prompt_tokens,
                actual_completion_tokens=actual_completion_tokens,
                actual_total_tokens=actual_total_tokens,
                estimated_system_tokens=estimated_system.count if estimated_system else 0,
                estimated_rim_tokens=estimated_rim.count if estimated_rim else 0,
                estimated_source_tokens=estimated_source.count if estimated_source else 0,
                estimated_other_tokens=estimated_other.count if estimated_other else 0,
                token_estimation_method="heuristic",
                token_estimation_is_approximate=True,
                token_reconciliation_diff=reconciliation_diff,
                llm_latency_ms=loop_result.latency_ms.get("llm_total", 0),
                retrieval_latency_ms=loop_result.latency_ms.get("tool_total", 0),
                token_counting_latency_ms=token_counting_ms,
                total_latency_ms=elapsed_ms
            ),
            answer_metrics=AnswerMetrics(),
            rim_metadata_block=rim_metadata_block,
            source_context_block=source_context_block,
            tool_call_transcript=tool_call_transcript,
            stop_reason=loop_result.stop_reason.value if loop_result.stop_reason else "unknown"
        )
