"""
Arm 3 Execution: GitOnboard Agent Runner.
Runs the active production QALoop, ToolDispatchTable, and QAProtocolAdapter under identical
conditions to the real application, recording turn-by-turn trajectory and tool efficiency.
"""
from __future__ import annotations
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.agent.loop.contracts import AgentLoopConfig
from backend.ai.service import LLMService, get_llm_service
from backend.evaluation.schemas import QuestionBenchmarkSpec, TrajectoryTurn
from backend.repository_tools.tools import RepositoryToolLayer
from backend.services.qa_loop import QALoop, QALoopResult
from backend.services.qa_protocol import QAProtocolAdapter
from backend.services.tool_dispatch import ToolDispatchTable, TargetEntityResolver
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from backend.services.rim_metadata import build_rim_metadata_block

logger = logging.getLogger(__name__)


async def run_gitonboard_agent(
    spec: QuestionBenchmarkSpec,
    tool_layer: RepositoryToolLayer,
    llm_service: Optional[LLMService] = None,
    max_turns: int = 10,
    temperature: float = 0.0,
) -> Tuple[str, List[TrajectoryTurn], List[str], str, float, int, int]:
    """
    Executes question through canonical GitOnboard QALoop agent.
    Includes:
    - Iterative tool calls (read_file, search_repository, search_code, get_code_relationships)
    - FactStore graph traversal
    - 4-stage validation and retry gates
    - Complete turn trajectory recording
    """
    service = llm_service or get_llm_service()
    db = getattr(tool_layer, "db", None)
    analysis_id = getattr(tool_layer, "analysis_id", None)

    # 1. Build tool dispatch table (with get_code_relationships if db & analysis_id present)
    if db is not None and analysis_id is not None:
        graph_traverser = FactStoreGraphTraverser(db, analysis_id)
        target_resolver = TargetEntityResolver(db, analysis_id)
        tool_dispatch = ToolDispatchTable(tool_layer, graph_traverser, target_resolver)
        include_rim = True
    else:
        tool_dispatch = ToolDispatchTable(tool_layer)
        include_rim = False

    # 2. Build metadata block if RIM is active
    rim_metadata_text = ""
    if include_rim and db is not None and analysis_id is not None:
        try:
            rim_metadata = build_rim_metadata_block(
                db=db, analysis_id=analysis_id, question=spec.question
            )
            rim_metadata_text = rim_metadata.text if rim_metadata else ""
        except Exception as e:
            logger.warning(f"Failed to build RIM metadata for benchmark: {e}")

    # 3. Build system prompt using QAProtocolAdapter
    model_name = getattr(service.providers[0], "default_model", None) if getattr(service, "providers", None) else None
    provider_name = getattr(service.providers[0], "provider_name", None) if getattr(service, "providers", None) else None

    protocol_adapter = QAProtocolAdapter(model_id=model_name, provider=provider_name)
    prompt_parts = protocol_adapter.build_system_prompt(
        tool_specs=tool_dispatch.specs(include_rim=include_rim),
        rim_metadata_block=rim_metadata_text,
    )

    # 4. Initialize QALoop with loop limits
    config = AgentLoopConfig(
        max_turns=max_turns,
        max_tool_calls_per_turn=1,
        total_max_tool_calls=max_turns,
    )

    qa_loop = QALoop(
        llm_service=service,
        tool_dispatch=tool_dispatch,
        config=config,
        system_prompt_parts=prompt_parts,
        model=model_name,
        provider=provider_name,
        repository=spec.repository,
        mode="rim" if include_rim else "baseline",
    )

    # 5. Execute Loop and Record Trajectory
    t0 = time.perf_counter()
    loop_result: QALoopResult = await qa_loop.run(spec.question)
    total_duration = (time.perf_counter() - t0) * 1000

    # 6. Transform QALoop turns into structured TrajectoryTurns
    trajectory: List[TrajectoryTurn] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for turn in loop_result.turns:
        t_call = turn.tool_call or {}
        t_obs = turn.tool_observation or {}

        total_prompt_tokens += turn.prompt_tokens
        total_completion_tokens += turn.completion_tokens

        obs_data = t_obs.get("data")
        obs_preview = str(obs_data)[:200] if obs_data else str(t_obs.get("error", ""))[:200]

        trajectory.append(
            TrajectoryTurn(
                turn_index=turn.turn_index,
                tool_name=t_call.get("tool_name"),
                arguments=t_call.get("arguments", {}),
                observation_preview=obs_preview,
                is_success=bool(t_obs.get("success", True)),
                prompt_tokens=turn.prompt_tokens,
                completion_tokens=turn.completion_tokens,
                duration_ms=round(turn.duration_ms, 2),
            )
        )

    # Aggregate all unique files accessed across read_file, search_repository, search_code, get_code_relationships
    accessed_files: List[str] = []
    for f in loop_result.files_read:
        if f not in accessed_files:
            accessed_files.append(f)
    for f in loop_result.files_searched:
        if f not in accessed_files:
            accessed_files.append(f)

    # Also inspect target locations from get_code_relationships
    for entity in loop_result.rim_entities_accessed:
        loc = entity.get("location")
        if loc and loc not in accessed_files:
            accessed_files.append(loc)

    return (
        loop_result.answer,
        trajectory,
        accessed_files,
        model_name or "unknown",
        round(total_duration, 2),
        total_prompt_tokens,
        total_completion_tokens,
    )
