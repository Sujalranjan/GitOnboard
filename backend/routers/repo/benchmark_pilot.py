"""Benchmark-only pilot endpoint for Phase 6.4-6.5 A/B testing with three conditions."""
import logging
from typing import Optional, Literal
from pydantic import BaseModel
from datetime import datetime
import time

from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.agent.loop.contracts import AgentLoopConfig
from backend.ai.service import get_llm_service
from backend.intelligence.retrieval import HybridRetriever
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from backend.repository_tools import resolve_repo_root, RepositoryToolLayer
from backend.services.rim_qa_loop import RIMQALoop
from backend.services.rim_qa_protocol import QAProtocolAdapter
from backend.services.rim_tool_dispatch import ToolDispatchTable, TargetEntityResolver
from backend.services.rim_metadata import build_rim_metadata_block
from backend.logging import StructuredLogger
from backend.services.crash_logger import get_crash_logger

logger = logging.getLogger(__name__)

benchmark_pilot_router = APIRouter(tags=["benchmark-pilot"])


class PilotBenchmarkRequest(BaseModel):
    question: str
    condition: Literal["A", "B", "C"]
    run_number: int = 1


class PilotBenchmarkResponse(BaseModel):
    """Single run result for pilot benchmark."""
    run_id: str
    query: str
    condition: str
    repository: str
    commit: Optional[str] = None
    analysis_id: Optional[int] = None
    model: str = ""
    timestamp: str

    # Execution
    latency_ms: float = 0.0
    tool_call_count: int = 0
    files_retrieved: list = []
    symbols_retrieved: list = []

    # RIM-specific
    rim_metadata_available: bool = False
    query_rim_available: bool = False
    rim_facts_used: int = 0

    # Answer and tools
    answer: str = ""
    tool_call_transcript: list = []
    rim_metadata_block: Optional[str] = None

    error: Optional[str] = None


@benchmark_pilot_router.post("/{repo_name}/benchmark/pilot-compare")
async def pilot_benchmark(
    repo_name: str,
    req: PilotBenchmarkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> PilotBenchmarkResponse:
    """
    Phase 6.4-6.5 pilot benchmark: Single-condition Q&A run.

    Supports three experimental conditions:
    - A: Baseline (no RIM metadata, no query_rim)
    - B: RIM metadata only (metadata yes, query_rim no)
    - C: Full RIM (metadata yes, query_rim yes)

    Each run is independent and records:
    - Answer quality
    - Tool usage
    - Retrieval metrics
    - RIM metrics
    """
    run_id = f"{req.condition}-{req.run_number}-{int(time.time()*1000) % 100000}"
    timestamp = datetime.utcnow().isoformat() + "Z"

    try:
        # Initialize structured logger
        structured_log = StructuredLogger(
            session_id=current_user.id if current_user else "unknown",
            repository=repo_name
        )
        request_id = structured_log.log_query(req.question, current_user.email if current_user else None)

        # Resolve repo/analysis
        from backend.routers.repo.services.analysis import get_latest_analysis
        from backend.routers.repo.semantic import get_chroma_collection

        repo, analysis = get_latest_analysis(repo_name, db, current_user)
        analysis_id = analysis.id

        chroma_collection = None
        try:
            chroma_collection = get_chroma_collection(repo_name, current_user, db)
        except Exception as e:
            logger.debug(f"Chroma collection not available: {e}")

        # Initialize shared infrastructure
        llm_service = get_llm_service()
        retriever = HybridRetriever(
            db=db,
            analysis_id=analysis_id,
            chroma_collection=chroma_collection,
            rrf_k=60
        )
        repo_root = resolve_repo_root(repo_name, current_user.id, db)
        tool_layer = RepositoryToolLayer(
            repo_name=repo_name,
            analysis_id=analysis_id,
            db=db,
            repo_root=repo_root,
            user_id=current_user.id
        )

        # Loop config
        config = AgentLoopConfig(
            max_agent_turns=12,
            max_tool_calls=15,
            max_command_executions=0,
            max_execution_seconds=180,
            max_observation_bytes=8000,
            max_repeated_tool_calls=3
        )

        # Determine RIM configuration based on condition
        include_rim_metadata = req.condition in ["B", "C"]
        include_query_rim = req.condition == "C"

        # Build RIM metadata if needed
        rim_metadata_text = None
        if include_rim_metadata:
            logger.info(f"[Pilot] Building RIM metadata for condition {req.condition}")
            t0 = time.perf_counter()
            rim_metadata = build_rim_metadata_block(
                db, analysis_id, req.question, retriever,
                max_seed_entities=3, max_related_per_seed=8, max_block_chars=4000
            )
            metadata_elapsed_ms = (time.perf_counter() - t0) * 1000
            rim_metadata_text = rim_metadata.text
            logger.info(f"[Pilot] RIM metadata built in {metadata_elapsed_ms:.1f}ms")

        # Build tool dispatch table with/without query_rim
        if include_query_rim:
            graph_traverser = FactStoreGraphTraverser(db, analysis_id)
            target_resolver = TargetEntityResolver(db, analysis_id)
            tool_dispatch = ToolDispatchTable(tool_layer, graph_traverser, target_resolver)
        else:
            tool_dispatch = ToolDispatchTable(tool_layer)

        # Build system prompt
        qa_protocol = QAProtocolAdapter()
        prompt_parts = qa_protocol.build_system_prompt(
            tool_specs=tool_dispatch.specs(include_rim=include_query_rim),
            rim_metadata_block=rim_metadata_text
        )

        # Run the Q&A loop
        logger.info(f"[Pilot] Running condition {req.condition} for: {req.question}")
        qa_loop = RIMQALoop(
            llm_service=llm_service,
            tool_dispatch=tool_dispatch,
            config=config,
            system_prompt_parts=prompt_parts,
            structured_logger=structured_log,
            request_id=request_id,
            repository=repo_name,
            mode=f"pilot-{req.condition}"
        )

        t0 = time.perf_counter()
        result = await qa_loop.run(req.question)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            f"[Pilot] Condition {req.condition} complete: {len(result.turns)} turns, "
            f"{result.tool_call_count} tool calls, stop_reason={result.stop_reason}"
        )

        # Extract metrics
        llm_service_info = llm_service.get_service_info()

        return PilotBenchmarkResponse(
            run_id=run_id,
            query=req.question,
            condition=req.condition,
            repository=repo_name,
            commit=getattr(analysis, "commit_hash", None),
            analysis_id=analysis_id,
            model=llm_service_info.get("model", "unknown"),
            timestamp=timestamp,
            latency_ms=elapsed_ms,
            tool_call_count=result.tool_call_count,
            files_retrieved=result.files_read,
            symbols_retrieved=result.symbols_referenced,
            rim_metadata_available=include_rim_metadata,
            query_rim_available=include_query_rim,
            rim_facts_used=len(result.rim_entities_accessed),
            answer=result.answer,
            tool_call_transcript=[
                {
                    "tool": turn.tool_name,
                    "input": turn.tool_input,
                    "output_summary": turn.tool_output[:200] if turn.tool_output else ""
                }
                for turn in result.turns
                if turn.tool_name
            ],
            rim_metadata_block=rim_metadata_text
        )

    except Exception as exc:
        crash_logger = get_crash_logger()
        crash_logger.log_exception(
            exception=exc,
            endpoint=f"POST /api/repos/{repo_name}/benchmark/pilot-compare",
            user_id=current_user.id if current_user else None,
            repository_id=repo_name,
            request_body={"question": req.question, "condition": req.condition},
        )
        logger.error(f"[Pilot] Error in condition {req.condition}: {exc}")

        return PilotBenchmarkResponse(
            run_id=run_id,
            query=req.question,
            condition=req.condition,
            repository=repo_name,
            timestamp=timestamp,
            rim_metadata_available=req.condition in ["B", "C"],
            query_rim_available=req.condition == "C",
            error=str(exc)
        )
