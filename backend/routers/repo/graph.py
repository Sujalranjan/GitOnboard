import logging
from collections import Counter
from typing import Optional, List, Dict, Any, Set
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.database import get_db
from backend.models.user import User
from backend.dependencies.auth import get_current_user
from backend.routers.repo.schemas import GraphQueryRequest
from backend.routers.repo.services.hash_resolution import get_latest_analysis_by_hash
from backend.routers.repo.services.analysis import get_latest_analysis
from backend.intelligence.graphs.graph_query_service import GraphQueryService
from backend.intelligence.rim.serialization import deserialize_rim
from backend.models.repository import AnalysisArtifact
from backend.models.fact_store import (
    FactFile,
    FactSymbol,
    FactRelationship,
    FactRoute,
    FactDatabaseObject,
    FactCapability,
    FactCapabilityMember,
)

logger = logging.getLogger(__name__)

graph_router = APIRouter(tags=["graph"])

# Include modular sub-routers for progressive exploration and legacy graph queries
from backend.routers.repo.graph_progressive import (  # noqa: F401
    router as progressive_router,
    get_knowledge_graph_overview,
    get_knowledge_graph_expand,
    _get_top_level_dir,
    _get_path_segments,
)
from backend.routers.repo.graph_query import (  # noqa: F401
    router as query_router,
    graph_search,
    graph_query,
)

graph_router.include_router(progressive_router)
graph_router.include_router(query_router)


@graph_router.get("/{repo_name}/knowledge-graph")
def get_knowledge_graph(
    repo_name: str,
    view: str = Query("all", description="View mode: all, calls, imports, routes, capabilities, structure"),
    search: Optional[str] = Query(None, description="Search term to highlight/filter nodes"),
    limit: int = Query(400, ge=10, le=1500, description="Max nodes to return"),
    rel_types: Optional[str] = Query(None, description="Comma-separated relationship types to include"),
    node_types: Optional[str] = Query(None, description="Comma-separated node types to include"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the comprehensive Knowledge Graph constructed from the Layer 4 Fact Store.
    Supports filtering by architectural view, relationship types, node types, and text search.
    """
    try:
        repo, analysis = get_latest_analysis(repo_name, db, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[KNOWLEDGE_GRAPH] Failed to resolve repository {repo_name}: {e}")
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    analysis_id = analysis.id
    logger.info(f"[KNOWLEDGE_GRAPH] Loading graph for repo='{repo_name}', analysis_id={analysis_id}, view='{view}'")

    # 1. Fetch Fact Store tables for this analysis
    files = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).all()
    symbols = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis_id).all()
    rels = db.query(FactRelationship).filter(FactRelationship.analysis_id == analysis_id).all()
    routes = db.query(FactRoute).filter(FactRoute.analysis_id == analysis_id).all()
    db_objects = db.query(FactDatabaseObject).filter(FactDatabaseObject.analysis_id == analysis_id).all()
    capabilities = db.query(FactCapability).filter(FactCapability.analysis_id == analysis_id).all()
    cap_members = (
        db.query(FactCapabilityMember)
        .filter(FactCapabilityMember.capability_id.in_([c.id for c in capabilities]))
        .all()
        if capabilities
        else []
    )

    file_map: Dict[str, FactFile] = {f.id: f for f in files}
    sym_map: Dict[str, FactSymbol] = {s.id: s for s in symbols}

    view_str = view if isinstance(view, str) else "all"
    limit_val = limit if isinstance(limit, int) else 400
    search_str = search if isinstance(search, str) else None

    # Summary statistics
    rel_type_counter = Counter(r.rel_type for r in rels)
    sym_type_counter = Counter(s.symbol_type.upper() for s in symbols)

    # 2. Determine allowed relationship types based on view or filter
    allowed_rel_types: Optional[Set[str]] = None
    if isinstance(rel_types, str) and rel_types.strip():
        allowed_rel_types = {t.strip().upper() for t in rel_types.split(",") if t.strip()}
    elif view_str == "calls":
        allowed_rel_types = {"CALLS"}
    elif view_str == "imports":
        allowed_rel_types = {"IMPORTS"}
    elif view_str == "structure":
        allowed_rel_types = {"DECLARES", "CONTAINS", "INHERITS"}
    elif view_str == "routes":
        allowed_rel_types = {"ROUTE_HANDLER", "CALLS", "EXPOSES"}
    elif view_str == "capabilities":
        allowed_rel_types = {"CAPABILITY_MEMBER", "CALLS", "DATABASE_ACCESS"}

    # 3. Collect active edges
    raw_edges: List[Dict[str, Any]] = []
    for r in rels:
        rtype = (r.rel_type or "GENERIC").upper()
        if allowed_rel_types and rtype not in allowed_rel_types:
            continue
        raw_edges.append({
            "id": r.id,
            "source": r.from_symbol_id,
            "target": r.to_symbol_id,
            "type": rtype,
            "evidence_line": r.evidence_line,
            "status": r.status or "CONFIRMED",
        })

    # Add synthetic route handler edges
    for route in routes:
        handler_id = route.handler_symbol_id or route.symbol_id
        if handler_id and (not allowed_rel_types or "ROUTE_HANDLER" in allowed_rel_types):
            route_node_id = f"route:{route.id}"
            raw_edges.append({
                "id": f"e-route-{route.id}",
                "source": route_node_id,
                "target": handler_id,
                "type": "ROUTE_HANDLER",
                "evidence_line": None,
                "status": "CONFIRMED",
            })

    # Add synthetic capability member edges
    for m in cap_members:
        if not allowed_rel_types or "CAPABILITY_MEMBER" in allowed_rel_types:
            cap_node_id = f"cap:{m.capability_id}"
            raw_edges.append({
                "id": f"e-cap-{m.id}",
                "source": cap_node_id,
                "target": m.symbol_id,
                "type": "CAPABILITY_MEMBER",
                "label": m.role or "member",
                "evidence_line": None,
                "status": "CONFIRMED",
            })

    # 4. Filter allowed node types if specified
    allowed_node_types: Optional[Set[str]] = None
    if isinstance(node_types, str) and node_types.strip():
        allowed_node_types = {t.strip().upper() for t in node_types.split(",") if t.strip()}

    # 5. Build full node registry
    all_nodes: Dict[str, Dict[str, Any]] = {}

    for s in symbols:
        stype = (s.symbol_type or "symbol").upper()
        if allowed_node_types and stype not in allowed_node_types:
            continue
        fpath = s.file.path if s.file else (file_map.get(s.file_id).path if s.file_id in file_map else "")
        all_nodes[s.id] = {
            "id": s.id,
            "name": s.name,
            "label": s.name,
            "full_name": s.qualified_name or s.name,
            "type": stype,
            "file": fpath,
            "line_start": s.line_start,
            "line_end": s.line_end,
            "metadata": {"signature_hash": s.signature_hash},
        }

    for f in files:
        if allowed_node_types and "FILE" not in allowed_node_types:
            continue
        basename = f.path.split("/")[-1] if "/" in f.path else f.path
        all_nodes[f.id] = {
            "id": f.id,
            "name": basename,
            "label": basename,
            "full_name": f.path,
            "type": "FILE",
            "file": f.path,
            "language": f.language,
            "size": f.size,
            "metadata": {"is_test": f.is_test, "is_doc": f.is_documentation},
        }

    for route in routes:
        if allowed_node_types and "ROUTE" not in allowed_node_types:
            continue
        route_node_id = f"route:{route.id}"
        all_nodes[route_node_id] = {
            "id": route_node_id,
            "name": f"{route.method} {route.path}",
            "label": f"{route.method} {route.path}",
            "full_name": f"{route.method} {route.path}",
            "type": "ROUTE",
            "method": route.method,
            "path": route.path,
            "metadata": {"handler_symbol_id": route.handler_symbol_id},
        }

    for db_obj in db_objects:
        if allowed_node_types and "DATABASE_OBJECT" not in allowed_node_types:
            continue
        db_id = db_obj.id or f"db:{db_obj.name}"
        all_nodes[db_id] = {
            "id": db_id,
            "name": db_obj.name,
            "label": db_obj.name,
            "full_name": db_obj.name,
            "type": "DATABASE_OBJECT",
            "object_type": db_obj.object_type,
            "metadata": {},
        }

    for cap in capabilities:
        if allowed_node_types and "CAPABILITY" not in allowed_node_types:
            continue
        cap_node_id = f"cap:{cap.id}"
        all_nodes[cap_node_id] = {
            "id": cap_node_id,
            "name": cap.name,
            "label": cap.name,
            "full_name": cap.name,
            "type": "CAPABILITY",
            "capability_type": cap.capability_type,
            "summary": cap.evidence_summary,
            "metadata": {"status": cap.status},
        }

    # 6. Filter edges: both endpoints must exist in all_nodes
    valid_edges: List[Dict[str, Any]] = []
    in_degrees: Counter = Counter()
    out_degrees: Counter = Counter()

    for e in raw_edges:
        src = e["source"]
        tgt = e["target"]
        if src in all_nodes and tgt in all_nodes:
            valid_edges.append(e)
            out_degrees[src] += 1
            in_degrees[tgt] += 1

    # 7. Apply search / focus filter if provided
    selected_node_ids: Set[str] = set()
    if search_str and search_str.strip():
        q = search_str.strip().lower()
        matching_seed_ids = {
            nid for nid, n in all_nodes.items()
            if q in n["name"].lower() or q in n.get("file", "").lower() or q in n.get("full_name", "").lower()
        }
        # Include seed matches + their 1-hop connected neighbors
        selected_node_ids = set(matching_seed_ids)
        for e in valid_edges:
            if e["source"] in matching_seed_ids:
                selected_node_ids.add(e["target"])
            elif e["target"] in matching_seed_ids:
                selected_node_ids.add(e["source"])
    else:
        # If no search, include nodes connected by valid edges first
        for e in valid_edges:
            selected_node_ids.add(e["source"])
            selected_node_ids.add(e["target"])

        # If graph is still small, fill with standalone files or classes up to limit
        if len(selected_node_ids) < limit_val:
            for nid, n in all_nodes.items():
                if n["type"] in ("CLASS", "FILE", "ROUTE", "CAPABILITY"):
                    selected_node_ids.add(nid)
                if len(selected_node_ids) >= limit_val:
                    break

    # 8. Sort nodes by connectivity (highest degree first) if over limit
    node_degrees = {nid: in_degrees[nid] + out_degrees[nid] for nid in selected_node_ids}
    sorted_node_ids = sorted(selected_node_ids, key=lambda nid: node_degrees.get(nid, 0), reverse=True)
    capped_node_ids = set(sorted_node_ids[:limit_val])

    # Filter edges to only those connecting capped nodes
    final_edges: List[Dict[str, Any]] = [
        e for e in valid_edges
        if e["source"] in capped_node_ids and e["target"] in capped_node_ids
    ]

    # Format final nodes
    final_nodes: List[Dict[str, Any]] = []
    final_node_type_counter: Counter = Counter()

    for nid in capped_node_ids:
        n = all_nodes[nid]
        n_copy = dict(n)
        n_copy["in_degree"] = in_degrees.get(nid, 0)
        n_copy["out_degree"] = out_degrees.get(nid, 0)
        n_copy["total_degree"] = in_degrees.get(nid, 0) + out_degrees.get(nid, 0)
        final_nodes.append(n_copy)
        final_node_type_counter[n["type"]] += 1

    # Top connected hub nodes for quick overview
    top_hubs = [
        {
            "id": nid,
            "name": all_nodes[nid]["name"],
            "type": all_nodes[nid]["type"],
            "file": all_nodes[nid].get("file", ""),
            "degree": node_degrees.get(nid, 0),
        }
        for nid in sorted_node_ids[:10]
        if nid in all_nodes
    ]

    # Final relationship counter on returned edges
    final_rel_counter = Counter(e["type"] for e in final_edges)

    return {
        "repo_name": repo.name if hasattr(repo, "name") and repo.name else repo.url.split("/")[-1].replace(".git", ""),
        "repo_hash": repo.repository_hash,
        "analysis_id": analysis_id,
        "view": view,
        "stats": {
            "returned_nodes": len(final_nodes),
            "returned_edges": len(final_edges),
            "raw_total_files": len(files),
            "raw_total_symbols": len(symbols),
            "raw_total_relationships": len(rels),
            "raw_total_routes": len(routes),
            "raw_total_capabilities": len(capabilities),
            "raw_total_database_objects": len(db_objects),
            "relationship_counts": dict(final_rel_counter),
            "total_relationship_counts": dict(rel_type_counter),
            "node_type_counts": dict(final_node_type_counter),
            "top_hubs": top_hubs,
        },
        "nodes": final_nodes,
        "edges": final_edges,
    }


@graph_router.get("/{repo_name}/knowledge-graph/node/{node_id:path}")
def get_knowledge_graph_node(
    repo_name: str,
    node_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve comprehensive details for an individual Knowledge Graph node,
    including its declaration, location, incoming callers/importers, and outgoing callees/imports.
    """
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    analysis_id = analysis.id

    # Try FactSymbol
    symbol = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis_id,
        FactSymbol.id == node_id,
    ).first()

    # Try FactFile
    file_obj = None
    if not symbol:
        file_obj = db.query(FactFile).filter(
            FactFile.analysis_id == analysis_id,
            FactFile.id == node_id,
        ).first()

    # Try FactRoute
    route_obj = None
    if not symbol and not file_obj and node_id.startswith("route:"):
        r_id = node_id.split("route:", 1)[1]
        route_obj = db.query(FactRoute).filter(
            FactRoute.analysis_id == analysis_id,
            FactRoute.id == r_id,
        ).first()

    # Try FactCapability
    cap_obj = None
    if not symbol and not file_obj and not route_obj and node_id.startswith("cap:"):
        c_id = node_id.split("cap:", 1)[1]
        cap_obj = db.query(FactCapability).filter(
            FactCapability.analysis_id == analysis_id,
            FactCapability.id == c_id,
        ).first()

    if not symbol and not file_obj and not route_obj and not cap_obj:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in repository graph")

    # Format primary node info
    if symbol:
        fpath = symbol.file.path if symbol.file else ""
        node_info = {
            "id": symbol.id,
            "name": symbol.name,
            "full_name": symbol.qualified_name or symbol.name,
            "type": symbol.symbol_type.upper(),
            "file": fpath,
            "line_start": symbol.line_start,
            "line_end": symbol.line_end,
            "signature_hash": symbol.signature_hash,
        }
    elif file_obj:
        node_info = {
            "id": file_obj.id,
            "name": file_obj.path.split("/")[-1],
            "full_name": file_obj.path,
            "type": "FILE",
            "file": file_obj.path,
            "language": file_obj.language,
            "size": file_obj.size,
        }
    elif route_obj:
        node_info = {
            "id": f"route:{route_obj.id}",
            "name": f"{route_obj.method} {route_obj.path}",
            "full_name": f"{route_obj.method} {route_obj.path}",
            "type": "ROUTE",
            "method": route_obj.method,
            "path": route_obj.path,
        }
    else:
        node_info = {
            "id": f"cap:{cap_obj.id}",
            "name": cap_obj.name,
            "full_name": cap_obj.name,
            "type": "CAPABILITY",
            "capability_type": cap_obj.capability_type,
            "summary": cap_obj.evidence_summary,
        }

    # Fetch incoming relationships (who points to this node)
    incoming_rels = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.to_symbol_id == node_id,
    ).all()

    # Fetch outgoing relationships (what this node points to)
    outgoing_rels = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.from_symbol_id == node_id,
    ).all()

    # Resolve names for related nodes
    all_sym_ids = {r.from_symbol_id for r in incoming_rels} | {r.to_symbol_id for r in outgoing_rels}
    all_syms = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis_id,
        FactSymbol.id.in_(all_sym_ids),
    ).all() if all_sym_ids else []
    sym_lookup = {s.id: s for s in all_syms}

    all_files = db.query(FactFile).filter(
        FactFile.analysis_id == analysis_id,
        FactFile.id.in_(all_sym_ids),
    ).all() if all_sym_ids else []
    file_lookup = {f.id: f for f in all_files}

    def resolve_ref(nid: str):
        if nid in sym_lookup:
            s = sym_lookup[nid]
            return {"id": s.id, "name": s.name, "type": s.symbol_type.upper(), "file": s.file.path if s.file else ""}
        elif nid in file_lookup:
            f = file_lookup[nid]
            return {"id": f.id, "name": f.path.split("/")[-1], "type": "FILE", "file": f.path}
        return {"id": nid, "name": nid.split("#")[-1] if "#" in nid else nid, "type": "UNKNOWN"}

    incoming_list = [
        {
            "id": r.id,
            "rel_type": r.rel_type,
            "evidence_line": r.evidence_line,
            "source": resolve_ref(r.from_symbol_id),
        }
        for r in incoming_rels
    ]

    outgoing_list = [
        {
            "id": r.id,
            "rel_type": r.rel_type,
            "evidence_line": r.evidence_line,
            "target": resolve_ref(r.to_symbol_id),
        }
        for r in outgoing_rels
    ]

    # Check capability memberships
    member_caps = (
        db.query(FactCapability)
        .join(FactCapabilityMember, FactCapabilityMember.capability_id == FactCapability.id)
        .filter(
            FactCapability.analysis_id == analysis_id,
            FactCapabilityMember.symbol_id == node_id,
        )
        .all()
    )
    cap_list = [{"id": c.id, "name": c.name, "summary": c.evidence_summary} for c in member_caps]

    return {
        "node": node_info,
        "incoming": incoming_list,
        "outgoing": outgoing_list,
        "capabilities": cap_list,
    }

