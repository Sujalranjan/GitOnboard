import logging
from typing import Optional, Dict, Any
from collections import Counter
from fastapi import APIRouter, Depends, BackgroundTasks, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.routers.repo.services.models import get_or_build_model
from backend.routers.repo.services.tasks import get_task_status, set_task_status
from backend.intelligence.graphs.graph_query_service import GraphQueryService

logger = logging.getLogger(__name__)

intelligence_router = APIRouter(tags=["intelligence"])

@intelligence_router.post("/{repo_name}/index", include_in_schema=False)
def index_repo(repo_name: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_status = get_task_status(repo_name, "index", current_user, db)
    if current_status == "processing":
        return {"status": "processing"}
    if current_status == "completed":
        return {"status": "completed"}
        
    set_task_status(repo_name, "index", "processing", current_user, db)
    
    def background_index():
        from backend.database import SessionLocal
        bg_db = SessionLocal()
        try:
            query_layer = get_or_build_model(repo_name, bg_db, current_user)
            set_task_status(repo_name, "index", "completed", current_user, bg_db)
        except Exception as e:
            logger.error(f"Index failed: {e}")
            set_task_status(repo_name, "index", "failed", current_user, bg_db)
        finally:
            bg_db.close()
            
    background_tasks.add_task(background_index)
    return {"status": "processing"}

@intelligence_router.post("/{repo_name}/symbols/index", include_in_schema=False)
def index_symbols(repo_name: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_status = get_task_status(repo_name, "symbols_index", current_user, db)
    if current_status == "processing":
        return {"status": "processing"}
        
    set_task_status(repo_name, "symbols_index", "processing", current_user, db)
    
    def background_symbols_index():
        from backend.database import SessionLocal
        bg_db = SessionLocal()
        try:
            query_layer = get_or_build_model(repo_name, bg_db, current_user)
            set_task_status(repo_name, "symbols_index", "completed", current_user, bg_db)
        except Exception as e:
            logger.error(f"Symbols index failed: {e}")
            set_task_status(repo_name, "symbols_index", "failed", current_user, bg_db)
        finally:
            bg_db.close()
            
    background_tasks.add_task(background_symbols_index)
    return {"status": "processing"}

@intelligence_router.get("/{repo_name}/features")
def get_features(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        features = sorted(
            query_layer.model.features.values(),
            key=lambda feature: (-float(feature.confidence or 0.0), feature.name.lower())
        )
        relationships = list(query_layer.model.feature_relationships.values())

        feature_map = {}
        for feature in features:
            members = [
                {
                    "item_id": member.item_id,
                    "item_type": member.item_type,
                    "confidence": member.confidence,
                }
                for member in feature.members
            ]
            feature_map[feature.id] = {
                "id": feature.id,
                "name": feature.name,
                "description": feature.description,
                "confidence": feature.confidence,
                "member_count": len(feature.members),
                "evidence_count": len(feature.evidence),
                "members": members,
                "metadata": feature.metadata,
            }

        return {
            "features": list(feature_map.values()),
            "relationships": [rel.model_dump() for rel in relationships],
            "feature_count": len(feature_map),
            "relationship_count": len(relationships),
        }
    except Exception:
        return {"features": [], "relationships": [], "feature_count": 0, "relationship_count": 0}

@intelligence_router.get("/{repo_name}/search")
def search_repo(repo_name: str, q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not q or len(q.strip()) == 0:
        return {"results": []}
    query_layer = get_or_build_model(repo_name, db, current_user)
    results = query_layer.search_entities(q)
    formatted = []
    for r in results:
        formatted.append({
            "file_path": r["file"],
            "match_reasons": [f"Matches {r['type']}: {r['name']}"]
        })
    return {"results": formatted}

@intelligence_router.get("/{repo_name}/symbols/search")
def search_symbols(repo_name: str, q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not q:
        return {"results": []}
    query_layer = get_or_build_model(repo_name, db, current_user)
    q_lower = q.lower()
    results = []
    from backend.intelligence.rim.enums import EntityType
    for e in query_layer.model.entities.values():
        if q_lower in e.name.lower():
            if e.type == EntityType.CLASS:
                results.append({"id": e.id, "type": "Class", "name": e.name, "file_path": e.metadata.get("file_id", e.location.repository_path), "line_number": e.location.start_line})
            elif e.type == EntityType.FUNCTION:
                results.append({"id": e.id, "type": "Function", "name": e.name, "file_path": e.metadata.get("file_id", e.location.repository_path), "line_number": e.location.start_line})
    return {"results": results}

@intelligence_router.api_route("/{repo_name}/context", methods=["GET", "POST"], include_in_schema=False)
def build_context_pack(
    repo_name: str,
    q: Optional[str] = None,
    body: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query_str = q
    if not query_str and body and isinstance(body, dict):
        query_str = body.get("query") or body.get("q") or body.get("feature_query")
    if query_str is None:
        query_str = ""

    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
    except Exception as e:
        logger.error(f"Failed to build model for context pack: {e}")
        return {"context_pack": None}

    from backend.intelligence.rim.enums import EntityType
    
    entity_counts = Counter(e.type.value for e in query_layer.model.entities.values())
    relationship_counts = Counter(r.type.value if hasattr(r.type, "value") else str(r.type) for r in query_layer.model.relationships.values())

    features = sorted(
        query_layer.model.features.values(),
        key=lambda feature: (-float(feature.confidence or 0.0), feature.name.lower())
    )

    feature_summaries = [
        {
            "id": feature.id,
            "name": feature.name,
            "description": feature.description,
            "confidence": feature.confidence,
            "member_count": len(feature.members),
        }
        for feature in features[:5]
    ]

    symbols = []
    graph = {"nodes": [], "edges": []}
    query_service = GraphQueryService(query_layer.model)

    if query_str and query_str.strip():
        symbols = query_service.search(query_str)[:5]
        if symbols:
            graph = query_service.traverse(symbols[0]["id"], direction="both", depth=1, max_nodes=20, relationship_type="calls")

    matched_features = []
    if query_str and query_str.strip():
        query_lower = query_str.lower()
        for feature in features:
            if query_lower in feature.name.lower() or query_lower in feature.description.lower():
                matched_features.append({
                    "id": feature.id,
                    "name": feature.name,
                    "description": feature.description,
                    "confidence": feature.confidence,
                    "member_count": len(feature.members),
                })

    matched_symbol_ids = set()
    for feature in matched_features:
        feature_obj = query_layer.model.features.get(feature["id"])
        if not feature_obj:
            continue
        for member in feature_obj.members:
            if member.item_id in query_layer.model.entities:
                matched_symbol_ids.add(member.item_id)

    for symbol in symbols:
        matched_symbol_ids.add(symbol["id"])

    matched_symbol_list = []
    for symbol_id in matched_symbol_ids:
        entity = query_layer.model.entities.get(symbol_id)
        if not entity:
            continue
        matched_symbol_list.append({
            "id": symbol_id,
            "name": entity.name,
            "type": entity.type.value.lower(),
            "file": entity.location.repository_path,
        })

    matched_symbol_list.sort(key=lambda item: (item["name"].lower(), item["id"]))

    return {
        "context_pack": {
            "query": query_str,
            "repository": {
                "feature_count": len(features),
                "symbol_count": sum(1 for e in query_layer.model.entities.values() if e.type in (EntityType.CLASS, EntityType.FUNCTION, EntityType.METHOD)),
                "entity_counts": dict(entity_counts),
                "relationship_counts": dict(relationship_counts),
            },
            "features": feature_summaries,
            "matched_features": matched_features[:5],
            "matched_symbols": matched_symbol_list[:5],
            "graph": graph,
        }
    }
