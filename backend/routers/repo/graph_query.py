"""
Legacy / hash-based graph query and search endpoints.
Extracted from backend.routers.repo.graph to maintain modularity.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.intelligence.graphs.graph_query_service import GraphQueryService
from backend.intelligence.rim.serialization import deserialize_rim
from backend.models.repository import AnalysisArtifact
from backend.models.user import User
from backend.routers.repo.schemas import GraphQueryRequest
from backend.routers.repo.services.hash_resolution import get_latest_analysis_by_hash

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-query"])


@router.get("/{repo_hash}/graph/search")
def graph_search(repo_hash: str, q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    try:
        repo, analysis = get_latest_analysis_by_hash(repo_hash, db, current_user)
    except HTTPException:
        raise

    artifact = db.query(AnalysisArtifact).filter(
        AnalysisArtifact.analysis_id == analysis.id,
        AnalysisArtifact.type == "rim_model"
    ).first()

    if not artifact or not artifact.data:
        raise HTTPException(status_code=404, detail=f"No model found for analysis {analysis.id}")

    model = deserialize_rim(artifact.data)
    service = GraphQueryService(model)
    results = service.search(q)

    logger.info(f"[GRAPH_SEARCH] repo_hash={repo_hash}, query={q}, results={len(results)}")
    return {"results": results}


@router.post("/{repo_hash}/graph/query")
def graph_query(repo_hash: str, req: GraphQueryRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    logger.info(f"[GRAPH_QUERY] repo_hash={repo_hash}, node_id={req.node_id}, direction={req.direction}, depth={req.depth}")

    if not req.node_id or not req.node_id.strip():
        raise HTTPException(status_code=400, detail="node_id cannot be empty")

    node_id = req.node_id.strip()

    valid_directions = ["incoming", "outgoing", "both"]
    if req.direction not in valid_directions:
        raise HTTPException(
            status_code=400,
            detail=f"direction must be one of {valid_directions} (got '{req.direction}')"
        )

    if req.depth < 1 or req.depth > 10:
        raise HTTPException(status_code=400, detail=f"depth must be between 1 and 10 (got {req.depth})")

    if req.max_nodes < 1 or req.max_nodes > 1000:
        raise HTTPException(status_code=400, detail=f"max_nodes must be between 1 and 1000 (got {req.max_nodes})")

    valid_rel_types = ["calls", "imports", "depends_on", "inherits", "renders"]
    if req.relationship_type not in valid_rel_types:
        raise HTTPException(
            status_code=400,
            detail=f"relationship_type must be one of {valid_rel_types} (got '{req.relationship_type}')"
        )

    try:
        repo, analysis = get_latest_analysis_by_hash(repo_hash, db, current_user)
    except HTTPException:
        raise

    artifact = db.query(AnalysisArtifact).filter(
        AnalysisArtifact.analysis_id == analysis.id,
        AnalysisArtifact.type == "rim_model"
    ).first()

    if not artifact or not artifact.data:
        raise HTTPException(status_code=404, detail=f"No model found for analysis {analysis.id}")

    model = deserialize_rim(artifact.data)
    service = GraphQueryService(model)

    if node_id not in service.model.entities:
        logger.warning(f"[GRAPH_QUERY] Node not found: {node_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' not found in repository graph"
        )

    entity = service.model.entities[node_id]
    logger.info(f"[GRAPH_QUERY] Node found: {entity.name} (type={entity.type})")

    result = service.traverse(
        node_id=node_id,
        direction=req.direction,
        depth=req.depth,
        max_nodes=req.max_nodes,
        relationship_type=req.relationship_type
    )

    logger.info(f"[GRAPH_QUERY] Result: {len(result['nodes'])} nodes, {len(result['edges'])} edges")
    return result
