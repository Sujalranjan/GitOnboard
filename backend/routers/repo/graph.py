import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.routers.repo.schemas import GraphQueryRequest
from backend.routers.repo.services.models import get_or_build_model
from backend.intelligence.graphs.graph_query_service import GraphQueryService

logger = logging.getLogger(__name__)

graph_router = APIRouter(tags=["graph"])

@graph_router.get("/{repo_name}/graph/search")
def graph_search(repo_name: str, q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    query_layer = get_or_build_model(repo_name, db, current_user)
    service = GraphQueryService(query_layer.model)
    results = service.search(q)

    logger.info(f"[GRAPH_SEARCH] repo={repo_name}, query={q}, results={len(results)}")
    return {"results": results}

@graph_router.post("/{repo_name}/graph/query")
def graph_query(repo_name: str, req: GraphQueryRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    logger.info(f"[GRAPH_QUERY] repo={repo_name}, node_id={req.node_id}, direction={req.direction}, depth={req.depth}")

    # Step 1: Validate input parameters
    if not req.node_id or not req.node_id.strip():
        raise HTTPException(status_code=400, detail="node_id cannot be empty")

    node_id = req.node_id.strip()

    # Validate direction parameter
    valid_directions = ["incoming", "outgoing", "both"]
    if req.direction not in valid_directions:
        raise HTTPException(
            status_code=400,
            detail=f"direction must be one of {valid_directions} (got '{req.direction}')"
        )

    # Validate depth parameter
    if req.depth < 1:
        raise HTTPException(status_code=400, detail=f"depth must be >= 1 (got {req.depth})")
    if req.depth > 10:
        raise HTTPException(status_code=400, detail=f"depth must be <= 10 (got {req.depth})")

    # Validate max_nodes parameter
    if req.max_nodes < 1:
        raise HTTPException(status_code=400, detail=f"max_nodes must be >= 1 (got {req.max_nodes})")
    if req.max_nodes > 1000:
        raise HTTPException(status_code=400, detail=f"max_nodes must be <= 1000 (got {req.max_nodes})")

    # Validate relationship_type parameter
    valid_rel_types = ["calls", "imports", "depends_on", "inherits", "renders"]
    if req.relationship_type not in valid_rel_types:
        raise HTTPException(
            status_code=400,
            detail=f"relationship_type must be one of {valid_rel_types} (got '{req.relationship_type}')"
        )

    # Step 2: Build model and get service
    query_layer = get_or_build_model(repo_name, db, current_user)
    service = GraphQueryService(query_layer.model)

    # Step 3: Validate node exists in model
    if node_id not in service.model.entities:
        logger.warning(f"[GRAPH_QUERY] Node not found: {node_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' not found in repository graph"
        )

    entity = service.model.entities[node_id]
    logger.info(f"[GRAPH_QUERY] Node found: {entity.name} (type={entity.type})")

    # Step 4: Traverse graph from validated node
    result = service.traverse(
        node_id=node_id,
        direction=req.direction,
        depth=req.depth,
        max_nodes=req.max_nodes,
        relationship_type=req.relationship_type
    )

    logger.info(f"[GRAPH_QUERY] Result: {len(result['nodes'])} nodes, {len(result['edges'])} edges")
    return result
