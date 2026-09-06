"""
8-Stage Pipeline Endpoint

Exposes the complete intelligence pipeline (Stages 1-8) via REST API.
"""
import logging
import time
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.dependencies.auth import get_current_user
from backend.routers.repo.services.analysis import get_latest_analysis
from backend.routers.repo.services.models import get_or_build_model

logger = logging.getLogger(__name__)

# Request/Response models
class PipelineQueryRequest(BaseModel):
    query: str
    top_k: int = 5


class StageResult(BaseModel):
    status: str
    time: float
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PipelineResponse(BaseModel):
    query: str
    repository_id: int
    stages: Dict[str, StageResult]
    total_time: float


pipeline_router = APIRouter(tags=["pipeline"])


@pipeline_router.post("/{repo_name}/pipeline/query", response_model=PipelineResponse)
def execute_8_stage_pipeline(
    repo_name: str,
    request: PipelineQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PipelineResponse:
    """
    Execute the complete 8-stage intelligence pipeline.

    Stages:
    1. Parse & Analyze (via AnalysisEngine)
    2. FactStore Persistence
    3. BM25 Indexing
    4. Semantic Indexing (SKIPPED - optional)
    5. Hybrid Retrieval
    6. Graph Navigation (NEW)
    7. Context Assembly (NEW)
    8. LLM Grounding (NEW)
    """
    start_time = time.time()
    stages = {}

    try:
        # ====================================================================
        # STAGES 1-5: Use existing pipeline
        # ====================================================================

        stage1_start = time.time()
        try:
            # Get or build the repository model (combines Stages 1-2)
            # Note: get_or_build_model returns QueryLayer, which wraps the actual model
            query_layer = get_or_build_model(repo_name, db, current_user)
            repo, analysis = get_latest_analysis(repo_name, db, current_user)

            # Extract the actual model from QueryLayer
            model = query_layer.model

            stage1_time = time.time() - stage1_start
            stages["stage_1"] = StageResult(
                status="PASS",
                time=stage1_time,
                details={
                    "entities": len(model.entities),
                    "relationships": len(model.relationships),
                }
            )
        except Exception as e:
            logger.error(f"Stage 1 failed: {e}")
            stages["stage_1"] = StageResult(status="FAIL", time=0, error=str(e))
            return _make_response(request.query, repo.id, stages, start_time)

        # Stage 2: FactStore Persistence (already done in get_or_build_model)
        stage2_time = 0.0  # Included in Stage 1
        stages["stage_2"] = StageResult(
            status="PASS",
            time=stage2_time,
            details={"message": "Completed in Stage 1"}
        )

        # Stages 3-5: Hybrid Retrieval
        stage3_start = time.time()
        try:
            from backend.intelligence.retrieval.retriever import HybridRetriever
            retriever = HybridRetriever(db=db, analysis_id=analysis.id)

            if not retriever.bm25_index:
                raise Exception("BM25 index initialization failed")

            stage3_time = time.time() - stage3_start
            stages["stage_3"] = StageResult(
                status="PASS",
                time=stage3_time,
                details={"index_size": "computed"}
            )
        except Exception as e:
            logger.error(f"Stage 3 failed: {e}")
            stages["stage_3"] = StageResult(status="FAIL", time=0, error=str(e))
            return _make_response(request.query, repo.id, stages, start_time)

        # Stage 4: Semantic Indexing (SKIPPED)
        stages["stage_4"] = StageResult(
            status="SKIPPED",
            time=0.0,
            details={"reason": "Optional - takes 30+ minutes"}
        )

        # Stage 5: Hybrid Retrieval
        stage5_start = time.time()
        try:
            retrieval_results = retriever.retrieve(request.query, top_k=request.top_k)
            stage5_time = time.time() - stage5_start
            stages["stage_5"] = StageResult(
                status="PASS",
                time=stage5_time,
                details={
                    "results_count": len(retrieval_results),
                    "query": request.query,
                }
            )
        except Exception as e:
            logger.error(f"Stage 5 failed: {e}")
            stages["stage_5"] = StageResult(status="FAIL", time=0, error=str(e))
            return _make_response(request.query, repo.id, stages, start_time)

        # ====================================================================
        # STAGES 6-8: NEW - Graph, Context, LLM
        # ====================================================================

        # Stage 6: Graph Navigation
        stage6_start = time.time()
        try:
            from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigator

            if not retrieval_results:
                raise Exception("No retrieval results to navigate")

            navigator = GraphNavigator(model=model, max_depth=3, max_edges_per_entity=5)
            graph_result = navigator.navigate(retrieval_results, max_entities=100)

            stage6_time = time.time() - stage6_start
            stages["stage_6"] = StageResult(
                status="PASS",
                time=stage6_time,
                details={
                    "entities_discovered": graph_result.entity_count,
                    "edges": graph_result.edge_count,
                    "traversal_depth": graph_result.traversal_depth,
                }
            )
        except Exception as e:
            logger.error(f"Stage 6 failed: {e}")
            stages["stage_6"] = StageResult(status="FAIL", time=0, error=str(e))
            return _make_response(request.query, repo.id, stages, start_time)

        # Stage 7: Context Assembly
        stage7_start = time.time()
        try:
            from backend.intelligence.engine.orchestration.stage7_context_assembly import ContextAssembler7

            assembler = ContextAssembler7(db=db)
            context, metrics = assembler.assemble(
                query=request.query,
                retrieval_results=retrieval_results,
                graph_result=graph_result,
                repository_id=str(repo.id),
                analysis_id=analysis.id,
            )

            stage7_time = time.time() - stage7_start
            stages["stage_7"] = StageResult(
                status="PASS",
                time=stage7_time,
                details={
                    "files_selected": len(context.relevant_files or []),
                    "symbols_selected": len(context.relevant_symbols or []),
                    "context_size_kb": metrics.context_size_kb,
                }
            )
        except Exception as e:
            logger.error(f"Stage 7 failed: {e}")
            stages["stage_7"] = StageResult(status="FAIL", time=0, error=str(e))
            return _make_response(request.query, repo.id, stages, start_time)

        # Stage 8: LLM Grounding
        stage8_start = time.time()
        try:
            from backend.intelligence.engine.orchestration.stage8_grounding import stage8_sync_wrapper

            answer, grounding = stage8_sync_wrapper(context, request.query)

            stage8_time = time.time() - stage8_start
            stages["stage_8"] = StageResult(
                status="PASS",
                time=stage8_time,
                details={
                    "answer_preview": answer[:200] + "..." if len(answer) > 200 else answer,
                    "grounding_status": grounding.grounding_status,
                    "grounded_entities": len(grounding.grounded_entities),
                }
            )
        except Exception as e:
            logger.error(f"Stage 8 failed: {e}")
            stages["stage_8"] = StageResult(status="FAIL", time=0, error=str(e))
            return _make_response(request.query, repo.id, stages, start_time)

        return _make_response(request.query, repo.id, stages, start_time)

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        return PipelineResponse(
            query=request.query,
            repository_id=0,
            stages={},
            total_time=time.time() - start_time,
        )


def _make_response(query: str, repo_id: int, stages: Dict[str, StageResult], start_time: float) -> PipelineResponse:
    """Helper to construct response."""
    return PipelineResponse(
        query=query,
        repository_id=repo_id,
        stages=stages,
        total_time=time.time() - start_time,
    )
