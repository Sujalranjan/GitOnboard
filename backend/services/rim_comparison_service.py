"""RIM Comparison Research Service — Orchestrates controlled experiments comparing retrieval ± RIM."""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, asdict, field

from sqlalchemy.orm import Session

from backend.ai.schemas import LLMRequest, Message, MessageRole, TokenUsage
from backend.ai.service import get_llm_service
from backend.ai.prompts.repo_qa import REPO_QA_SYSTEM_PROMPT, REPO_QA_USER_TEMPLATE
from backend.intelligence.retrieval import HybridRetriever
from backend.models.user import User
from backend.repository_tools import resolve_repo_root, RepositoryToolLayer
from backend.summary.audit import redact_secrets, sanitize_dict_or_list

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

MAX_CONTEXT_SIZE = 15000  # chars
SNIPPET_CONTEXT_LINES = 3


@dataclass
class RIMExecutionTrace:
    """Full causal chain documenting what RIM discovered and contributed."""
    query: str
    baseline_candidates: List[Dict[str, Any]] = field(default_factory=list)
    rim_seed_entities: List[Dict[str, Any]] = field(default_factory=list)
    rim_relationships_traversed: List[Dict[str, Any]] = field(default_factory=list)
    rim_discovered_entities: List[Dict[str, Any]] = field(default_factory=list)
    files_added_by_rim: List[str] = field(default_factory=list)

    context_without_rim: str = ""
    context_with_rim: str = ""

    llm_input_without_rim: List[Dict[str, str]] = field(default_factory=list)
    llm_input_with_rim: List[Dict[str, str]] = field(default_factory=list)

    llm_output_without_rim: str = ""
    llm_output_with_rim: str = ""

    token_usage_without_rim: Optional[Dict[str, int]] = None
    token_usage_with_rim: Optional[Dict[str, int]] = None

    latency_without_rim_ms: Dict[str, float] = field(default_factory=dict)
    latency_with_rim_ms: Dict[str, float] = field(default_factory=dict)


@dataclass
class RetrievalMetrics:
    """Retrieval-phase metrics."""
    files_retrieved: int
    symbols_retrieved: int
    rim_relationships_count: int = 0
    rim_discovered_files: int = 0
    rim_discovered_symbols: int = 0
    retrieval_latency_ms: float = 0.0


@dataclass
class LLMEfficiencyMetrics:
    """LLM execution and token metrics."""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    context_size_chars: int = 0
    context_assembly_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    total_latency_ms: float = 0.0


@dataclass
class AnswerMetrics:
    """Holder for manual quality evaluation (auto-filled with None for UI scaffolding)."""
    correctness: Optional[str] = None  # "Correct" | "Partially Correct" | "Incorrect"
    grounding: Optional[str] = None    # "Grounded" | "Partially Grounded" | "Hallucinated"
    notes: str = ""


@dataclass
class ComparisonSide:
    """Result of one pipeline (with or without RIM)."""
    answer: str
    retrieval_metrics: RetrievalMetrics
    llm_efficiency_metrics: LLMEfficiencyMetrics
    answer_metrics: AnswerMetrics
    retrieved_files: List[str]
    retrieved_symbols: List[str]
    context_block: str


@dataclass
class ContextDiff:
    """Files retrieved, grouped by side."""
    files_only_without_rim: List[str]
    shared_files: List[str]
    files_only_with_rim: List[str]


@dataclass
class RIMComparisonResult:
    """Complete comparison result for frontend consumption."""
    without_rim: ComparisonSide
    with_rim: ComparisonSide

    repository: str
    branch: Optional[str] = None
    commit: Optional[str] = None
    analysis_id: Optional[int] = None

    context_diff: ContextDiff = field(default_factory=lambda: ContextDiff([], [], []))
    trace: RIMExecutionTrace = field(default_factory=lambda: RIMExecutionTrace(""))


class RIMComparisonService:
    """Orchestrates controlled RIM-on/off comparison experiments."""

    def __init__(self, db: Session, repo_name: str, current_user: User):
        self.db = db
        self.repo_name = repo_name
        self.current_user = current_user
        self.llm_service = get_llm_service()

    async def run_comparison(self, question: str) -> RIMComparisonResult:
        """
        Runs the same question through two identical retrieval/LLM pipelines,
        differing only in expand_with_fact_store (RIM on/off).

        Preserves full execution trace for attribution.
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

        # Initialize retriever (shared between both runs)
        retriever = HybridRetriever(
            db=self.db,
            analysis_id=analysis_id,
            chroma_collection=chroma_collection,
            rrf_k=60
        )

        # Initialize repository tool layer for source reading
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

        # Initialize trace
        trace = RIMExecutionTrace(query=question)

        # 2-3. Run retrieval without RIM (baseline)
        t0 = time.time()
        baseline_candidates = retriever.retrieve(
            query=question,
            top_k=15,
            expand_with_fact_store=False
        )
        retrieval_ms_without_rim = (time.time() - t0) * 1000

        logger.info(f"[RIM DEBUG] WITHOUT RIM retrieval complete: {len(baseline_candidates)} candidates, {retrieval_ms_without_rim:.2f}ms")
        logger.info(f"[RIM DEBUG] Baseline candidate types: {[c.get('match_type') for c in baseline_candidates[:5]]}")
        logger.info(f"[RIM DEBUG] Baseline files: {set(c.get('file_path') for c in baseline_candidates if c.get('file_path'))}")

        trace.baseline_candidates = baseline_candidates

        # 4. Run retrieval with RIM
        t0 = time.time()
        expanded_candidates = retriever.retrieve(
            query=question,
            top_k=15,
            expand_with_fact_store=True
        )
        retrieval_ms_with_rim = (time.time() - t0) * 1000

        logger.info(f"[RIM DEBUG] WITH RIM retrieval complete: {len(expanded_candidates)} candidates, {retrieval_ms_with_rim:.2f}ms")
        logger.info(f"[RIM DEBUG] Expanded candidate types: {[c.get('match_type') for c in expanded_candidates[:5]]}")
        logger.info(f"[RIM DEBUG] Candidates with expansion_reason: {sum(1 for c in expanded_candidates if c.get('expansion_reason'))}")

        # Extract RIM contribution from expansion_reason markers
        rim_discovered = [c for c in expanded_candidates if c.get("expansion_reason")]
        rim_seed_entities = [c for c in expanded_candidates if not c.get("expansion_reason")][:10]

        logger.info(f"[RIM DEBUG] RIM discovered entities: {len(rim_discovered)}, seed entities: {len(rim_seed_entities)}")
        if rim_discovered:
            logger.info(f"[RIM DEBUG] RIM relationships found: {[c.get('expansion_reason') for c in rim_discovered[:3]]}")

        trace.rim_seed_entities = rim_seed_entities
        trace.rim_discovered_entities = rim_discovered
        trace.rim_relationships_traversed = [
            {
                "expansion_reason": c.get("expansion_reason"),
                "rel_type": c.get("rel_type"),
                "name": c.get("name"),
                "file_path": c.get("file_path")
            }
            for c in rim_discovered
        ]

        # Compute file diff
        baseline_files = {c.get("file_path") for c in baseline_candidates if c.get("file_path")}
        expanded_files = {c.get("file_path") for c in expanded_candidates if c.get("file_path")}

        logger.info(f"[RIM DEBUG] File diff: baseline={len(baseline_files)}, expanded={len(expanded_files)}, added_by_rim={len(expanded_files - baseline_files)}")
        logger.info(f"[RIM DEBUG] Files added by RIM: {expanded_files - baseline_files}")

        trace.files_added_by_rim = sorted(list(expanded_files - baseline_files))

        # 5. Assemble context blocks and collect metrics
        without_rim_result = await self._assemble_and_llm(
            question,
            baseline_candidates,
            retrieval_ms_without_rim,
            tool_layer,
            trace
        )

        with_rim_result = await self._assemble_and_llm(
            question,
            expanded_candidates,
            retrieval_ms_with_rim,
            tool_layer,
            trace
        )

        # Store contexts in trace
        trace.context_without_rim = without_rim_result.get("context", "")
        trace.context_with_rim = with_rim_result.get("context", "")

        # 6. Build result
        files_only_without = baseline_files - expanded_files
        files_only_with = expanded_files - baseline_files
        shared = baseline_files & expanded_files

        result = RIMComparisonResult(
            without_rim=ComparisonSide(
                answer=without_rim_result["answer"],
                retrieval_metrics=RetrievalMetrics(
                    files_retrieved=len(baseline_files),
                    symbols_retrieved=sum(1 for c in baseline_candidates if c.get("match_type") not in ["file", "route", "database_table"]),
                    retrieval_latency_ms=retrieval_ms_without_rim
                ),
                llm_efficiency_metrics=LLMEfficiencyMetrics(
                    input_tokens=without_rim_result.get("tokens", {}).get("prompt_tokens"),
                    output_tokens=without_rim_result.get("tokens", {}).get("completion_tokens"),
                    total_tokens=without_rim_result.get("tokens", {}).get("total_tokens"),
                    context_size_chars=len(without_rim_result.get("context", "")),
                    context_assembly_latency_ms=without_rim_result.get("assembly_ms", 0),
                    llm_latency_ms=without_rim_result.get("llm_ms", 0),
                    total_latency_ms=retrieval_ms_without_rim + without_rim_result.get("assembly_ms", 0) + without_rim_result.get("llm_ms", 0)
                ),
                answer_metrics=AnswerMetrics(),
                retrieved_files=sorted(list(baseline_files)),
                retrieved_symbols=[c.get("match_name") or c.get("name") for c in baseline_candidates if c.get("match_type") not in ["file", "route", "database_table"]],
                context_block=without_rim_result.get("context", "")
            ),
            with_rim=ComparisonSide(
                answer=with_rim_result["answer"],
                retrieval_metrics=RetrievalMetrics(
                    files_retrieved=len(expanded_files),
                    symbols_retrieved=sum(1 for c in expanded_candidates if c.get("match_type") not in ["file", "route", "database_table"]),
                    rim_relationships_count=len(trace.rim_relationships_traversed),
                    rim_discovered_files=len(trace.files_added_by_rim),
                    rim_discovered_symbols=sum(1 for c in rim_discovered if c.get("match_type") not in ["file", "route", "database_table"]),
                    retrieval_latency_ms=retrieval_ms_with_rim
                ),
                llm_efficiency_metrics=LLMEfficiencyMetrics(
                    input_tokens=with_rim_result.get("tokens", {}).get("prompt_tokens"),
                    output_tokens=with_rim_result.get("tokens", {}).get("completion_tokens"),
                    total_tokens=with_rim_result.get("tokens", {}).get("total_tokens"),
                    context_size_chars=len(with_rim_result.get("context", "")),
                    context_assembly_latency_ms=with_rim_result.get("assembly_ms", 0),
                    llm_latency_ms=with_rim_result.get("llm_ms", 0),
                    total_latency_ms=retrieval_ms_with_rim + with_rim_result.get("assembly_ms", 0) + with_rim_result.get("llm_ms", 0)
                ),
                answer_metrics=AnswerMetrics(),
                retrieved_files=sorted(list(expanded_files)),
                retrieved_symbols=[c.get("match_name") or c.get("name") for c in expanded_candidates if c.get("match_type") not in ["file", "route", "database_table"]],
                context_block=with_rim_result.get("context", "")
            ),
            repository=self.repo_name,
            branch=repo.default_branch,
            commit=analysis.commit_sha,
            analysis_id=analysis_id,
            context_diff=ContextDiff(
                files_only_without_rim=sorted(list(files_only_without)),
                shared_files=sorted(list(shared)),
                files_only_with_rim=sorted(list(files_only_with))
            ),
            trace=trace
        )

        return result

    async def _assemble_and_llm(
        self,
        question: str,
        candidates: List[Dict[str, Any]],
        retrieval_ms: float,
        tool_layer: RepositoryToolLayer,
        trace: RIMExecutionTrace
    ) -> Dict[str, Any]:
        """Assemble context from candidates and run LLM."""
        # Assemble context block
        t0 = time.time()
        context_block = self._build_context(candidates, tool_layer)
        assembly_ms = (time.time() - t0) * 1000

        # Build LLM request
        system_prompt = REPO_QA_SYSTEM_PROMPT
        user_prompt = REPO_QA_USER_TEMPLATE.format(
            question=question,
            context_block=context_block
        )

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=user_prompt)
        ]

        # Store in trace (redacted)
        trace_messages = [
            {"role": msg.role.value, "content": redact_secrets(msg.content)[:200] + "..."}
            for msg in messages
        ]
        if not trace.llm_input_without_rim:
            trace.llm_input_without_rim = trace_messages
        else:
            trace.llm_input_with_rim = trace_messages

        request = LLMRequest(
            messages=messages,
            model="qwen3:4b-instruct",
            temperature=0.2,
            max_tokens=2000
        )

        # Run LLM
        t0 = time.time()
        try:
            response = await self.llm_service.generate(request)
            llm_ms = (time.time() - t0) * 1000

            answer = response.content
            tokens = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            llm_ms = (time.time() - t0) * 1000
            answer = f"Error: Failed to generate answer ({str(e)[:100]})"
            tokens = {}

        # Store in trace
        if not trace.llm_output_without_rim:
            trace.llm_output_without_rim = answer
            trace.token_usage_without_rim = tokens if tokens.get("total_tokens") else None
            trace.latency_without_rim_ms = {
                "retrieval": retrieval_ms,
                "context_assembly": assembly_ms,
                "llm": llm_ms,
                "total": retrieval_ms + assembly_ms + llm_ms
            }
        else:
            trace.llm_output_with_rim = answer
            trace.token_usage_with_rim = tokens if tokens.get("total_tokens") else None
            trace.latency_with_rim_ms = {
                "retrieval": retrieval_ms,
                "context_assembly": assembly_ms,
                "llm": llm_ms,
                "total": retrieval_ms + assembly_ms + llm_ms
            }

        return {
            "answer": answer,
            "context": context_block,
            "assembly_ms": assembly_ms,
            "llm_ms": llm_ms,
            "tokens": tokens
        }

    def _build_context(self, candidates: List[Dict[str, Any]], tool_layer: RepositoryToolLayer) -> str:
        """Assemble source code context from retrieved candidates."""
        sections = []
        sections.append("=== REPOSITORY CONTEXT ===\n")

        seen_files = set()
        for candidate in candidates[:15]:  # Limit to top 15
            file_path = candidate.get("file_path", "")
            if not file_path or file_path in seen_files:
                continue

            seen_files.add(file_path)

            try:
                # Read snippet
                start_line = max(1, candidate.get("line_start", 1) - SNIPPET_CONTEXT_LINES)
                end_line = (candidate.get("line_end", start_line + 10) + SNIPPET_CONTEXT_LINES)

                snippet_result = tool_layer.read_file(file_path, start_line, end_line)

                if snippet_result and snippet_result.get("content"):
                    sections.append(f"\n**File: {file_path}**")
                    sections.append(f"```\n{snippet_result['content']}\n```")
            except Exception as e:
                logger.debug(f"Failed to read {file_path}: {e}")
                sections.append(f"\n**File: {file_path}** (snippet unavailable)")

            # Respect context size limit
            if sum(len(s) for s in sections) > MAX_CONTEXT_SIZE:
                sections.append("\n(Context limit reached)")
                break

        return "\n".join(sections)
