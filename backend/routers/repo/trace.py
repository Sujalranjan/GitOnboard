import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.routers.repo.schemas import ExplainTraceRequest, TraceRequest
from backend.routers.repo.services.models import get_or_build_model
from backend.routers.repo.semantic import get_chroma_collection
from backend.ai.orchestrator import LLMOrchestrator

logger = logging.getLogger(__name__)

trace_router = APIRouter(tags=["trace"])

@trace_router.post("/{repo_name}/trace")
def trace_feature(
    repo_name: str,
    q: Optional[str] = None,
    req_body: Optional[TraceRequest] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    search_q = q
    if not search_q and req_body:
        search_q = req_body.feature_query or req_body.q or req_body.query

    if not search_q or len(search_q.strip()) == 0:
        return {"trace": None, "flow": []}

    search_q = search_q.strip()

    try:
        collection = None
        try:
            collection = get_chroma_collection(repo_name, current_user, db)
        except Exception:
            pass

        from backend.routers.repo.services.analysis import get_latest_analysis
        analysis_id = None
        try:
            _, latest = get_latest_analysis(repo_name, db, current_user)
            if latest:
                analysis_id = latest.id
        except Exception:
            pass

        from backend.intelligence.retrieval import HybridRetriever
        retriever = HybridRetriever(
            db=db,
            analysis_id=analysis_id,
            chroma_collection=collection,
            rrf_k=60
        )
        retrieved_items = retriever.retrieve(query=search_q, top_k=10, expand_with_fact_store=False)

        seed_nodes = []
        if retrieved_items:
            try:
                query_layer = get_or_build_model(repo_name, db, current_user)
            except Exception as e:
                logger.error(f"Failed to build model for trace: {e}")
                return {"trace": None, "flow": []}

            from backend.intelligence.rim.enums import EntityType
            for item in retrieved_items:
                fp = item.get("file_path")
                name = item.get("match_name", item.get("name"))
                typ = item.get("match_type", item.get("type"))
                ent_id = None

                for e in query_layer.model.entities.values():
                    if e.name == name or (name and e.name.lower() == name.lower()):
                        if not fp or e.metadata.get("file_id") == fp or e.location.repository_path == fp or fp in e.location.repository_path or not e.location.repository_path:
                            ent_id = e.id
                            break

                if not ent_id:
                    for e in query_layer.model.entities.values():
                        if e.name.lower() == str(name).lower():
                            ent_id = e.id
                            break

                if ent_id:
                    item_dict = dict(item)
                    item_dict["id"] = ent_id
                    seed_nodes.append(item_dict)
    except Exception as e:
        logger.error(f"Hybrid retrieval failed for trace: {e}")
        seed_nodes = []

    if not seed_nodes:
        return {"trace": None, "flow": []}

    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
    except Exception as e:
        logger.error(f"Failed to build model for trace: {e}")
        return {"trace": None, "flow": []}

    from backend.intelligence.feature_tracing import DeterministicTracer
    tracer = DeterministicTracer(query_layer.model)
    trace_result = tracer.trace_feature(seed_nodes)

    flow = []
    if isinstance(trace_result, dict):
        flow = trace_result.get("flow", trace_result.get("nodes", []))
    elif isinstance(trace_result, list):
        flow = trace_result

    return {"trace": trace_result, "flow": flow}

@trace_router.post("/{repo_name}/trace/explain")
async def explain_trace(
    repo_name: str,
    req: ExplainTraceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    analysis_id = None
    try:
        from backend.routers.repo.services.analysis import get_latest_analysis
        _, latest = get_latest_analysis(repo_name, db, current_user)
        if latest:
            analysis_id = latest.id
    except Exception:
        pass

    orchestrator = LLMOrchestrator(
        db=db,
        analysis_id=analysis_id,
        repo_name=repo_name,
        user_id=current_user.id
    )

    try:
        result = await orchestrator.explain_trace(
            feature_query=req.feature_query,
            trace_data=req.trace_data
        )
        return result
    except Exception as e:
        logger.error(f"Trace explanation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate explanation")

