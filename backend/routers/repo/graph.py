import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.routers.repo.schemas import GraphQueryRequest
from backend.routers.repo.services.models import get_or_build_model
from backend.intelligence.graphs.graph_query_service import GraphQueryService

logger = logging.getLogger(__name__)

graph_router = APIRouter()

@graph_router.get("/{repo_name}/graph/search")
def graph_search(repo_name: str, q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query_layer = get_or_build_model(repo_name, db, current_user)
    service = GraphQueryService(query_layer.model)
    return {"results": service.search(q)}

@graph_router.post("/{repo_name}/graph/query")
def graph_query(repo_name: str, req: GraphQueryRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query_layer = get_or_build_model(repo_name, db, current_user)
    service = GraphQueryService(query_layer.model)
    result = service.traverse(
        node_id=req.node_id,
        direction=req.direction,
        depth=req.depth,
        max_nodes=req.max_nodes,
        relationship_type=req.relationship_type
    )
    return result
