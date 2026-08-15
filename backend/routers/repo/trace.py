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
from backend.llm_service import llm_service

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
        collection = get_chroma_collection(repo_name, current_user, db)
        query_results = collection.query(query_texts=[search_q], n_results=5)
        seed_nodes = []
        if query_results and query_results.get("metadatas") and len(query_results["metadatas"]) > 0:
            try:
                query_layer = get_or_build_model(repo_name, db, current_user)
            except Exception as e:
                logger.error(f"Failed to build model for trace: {e}")
                return {"trace": None, "flow": []}

            from backend.intelligence.rim.enums import EntityType
            for item in query_results["metadatas"][0]:
                fp = item.get("file_path")
                name = item.get("name")
                typ = item.get("type")
                ent_id = None

                for e in query_layer.model.entities.values():
                    if e.name == name and e.metadata.get("file_id") == fp:
                        if (typ == "function" and e.type == EntityType.FUNCTION) or (typ == "class" and e.type == EntityType.CLASS):
                            ent_id = e.id
                            break

                if ent_id:
                    item["id"] = ent_id
                    seed_nodes.append(item)
    except Exception as e:
        logger.error(f"Semantic search failed for trace: {e}")
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
def explain_trace(repo_name: str, req: ExplainTraceRequest):
    prompt = f"Explain the following implementation trace for the feature '{req.feature_query}'. The trace was deterministically generated from the repository's semantic, dependency, and call graphs. Do not add any new nodes or hallucinate execution paths. Explain what each component does in the context of the flow.\n\nTrace Data: {json.dumps(req.trace_data, indent=2)}"

    try:
        explanation = llm_service.generate_explanation(prompt)
        return {"explanation": explanation}
    except Exception as e:
        logger.error(f"Explanation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate explanation")
