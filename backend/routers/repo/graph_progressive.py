"""
Progressive exploration endpoints for Knowledge Graph (/overview and /expand).
Extracted from backend.routers.repo.graph to maintain modularity.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.models.fact_store import (
    FactCapability,
    FactCapabilityMember,
    FactFile,
    FactRelationship,
    FactRoute,
    FactSymbol,
)
from backend.models.user import User
from backend.routers.repo.services.analysis import get_latest_analysis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-progressive"])


def _get_top_level_dir(path: str) -> str:
    """Extract the first directory segment from a file path."""
    parts = path.replace("\\", "/").strip("/").split("/")
    return parts[0] if len(parts) > 1 else "__root__"


def _get_path_segments(path: str) -> List[str]:
    """Return all directory segments of a path (excludes filename)."""
    parts = path.replace("\\", "/").strip("/").split("/")
    return parts[:-1]  # all except the filename


@router.get("/{repo_name}/knowledge-graph/overview")
def get_knowledge_graph_overview(
    repo_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return a lightweight high-level overview graph for progressive exploration.

    The initial view shows:
    - Synthetic top-level directory nodes (e.g. 'backend/', 'frontend/', 'tests/')
    - Capability nodes (cross-cutting features detected by Layer 6)
    - Route count summary nodes (API surface)

    Each directory node is marked expandable=True. Clicking one calls /expand/{node_id}.
    This allows large repositories (50k+ nodes) to be explored progressively without
    loading the entire graph into the browser at once.
    """
    try:
        repo, analysis = get_latest_analysis(repo_name, db, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GRAPH_OVERVIEW] Failed to resolve repository {repo_name}: {e}")
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    analysis_id = analysis.id
    logger.info(f"[GRAPH_OVERVIEW] Loading overview for repo='{repo_name}', analysis_id={analysis_id}")

    # Fetch only what we need for the overview
    files = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).all()
    capabilities = db.query(FactCapability).filter(FactCapability.analysis_id == analysis_id).all()
    routes = db.query(FactRoute).filter(FactRoute.analysis_id == analysis_id).all()
    symbols = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis_id).all()

    # Group files by their first directory segment to create synthetic folder nodes
    folder_file_counts: Dict[str, int] = {}
    folder_symbol_counts: Dict[str, int] = {}

    # Track which files/symbols belong to each top-level folder
    file_to_folder: Dict[str, str] = {}
    for f in files:
        folder = _get_top_level_dir(f.path)
        folder_file_counts[folder] = folder_file_counts.get(folder, 0) + 1
        file_to_folder[f.id] = folder

    for s in symbols:
        fid = s.file_id
        if fid and fid in file_to_folder:
            folder = file_to_folder[fid]
            folder_symbol_counts[folder] = folder_symbol_counts.get(folder, 0) + 1

    overview_nodes: List[Dict[str, Any]] = []
    overview_edges: List[Dict[str, Any]] = []

    # 1. Folder nodes (one per top-level directory)
    folder_names = sorted(folder_file_counts.keys())
    for folder in folder_names:
        node_id = f"dir:{folder}"
        file_count = folder_file_counts.get(folder, 0)
        sym_count = folder_symbol_counts.get(folder, 0)
        overview_nodes.append({
            "id": node_id,
            "name": folder if folder != "__root__" else "(root files)",
            "label": folder if folder != "__root__" else "(root)",
            "full_name": folder,
            "type": "DIRECTORY",
            "file_count": file_count,
            "symbol_count": sym_count,
            "expandable": True,
            "expanded": False,
            "metadata": {"folder": folder},
        })

    # 2. Capability nodes (always show - they are high-value cross-cutting nodes)
    for cap in capabilities:
        cap_node_id = f"cap:{cap.id}"
        overview_nodes.append({
            "id": cap_node_id,
            "name": cap.name,
            "label": cap.name,
            "full_name": cap.name,
            "type": "CAPABILITY",
            "capability_type": cap.capability_type,
            "summary": cap.evidence_summary,
            "expandable": False,
            "expanded": False,
            "metadata": {"status": cap.status},
        })

    # 3. Add edges: if a capability member belongs to a file in a folder,
    #    connect that folder -> capability
    cap_members = (
        db.query(FactCapabilityMember)
        .filter(FactCapabilityMember.capability_id.in_([c.id for c in capabilities]))
        .all()
        if capabilities else []
    )
    sym_map: Dict[str, str] = {s.id: s.file_id for s in symbols if s.file_id}
    cap_folder_edges_seen: Set[str] = set()
    for m in cap_members:
        file_id = sym_map.get(m.symbol_id)
        if file_id and file_id in file_to_folder:
            folder = file_to_folder[file_id]
            folder_node_id = f"dir:{folder}"
            cap_node_id = f"cap:{m.capability_id}"
            edge_key = f"{folder_node_id}->{cap_node_id}"
            if edge_key not in cap_folder_edges_seen:
                cap_folder_edges_seen.add(edge_key)
                overview_edges.append({
                    "id": f"e-overview-{edge_key}",
                    "source": folder_node_id,
                    "target": cap_node_id,
                    "type": "CAPABILITY_MEMBER",
                    "status": "CONFIRMED",
                })

    repo_name_str = repo.name if hasattr(repo, "name") and repo.name else repo.url.split("/")[-1].replace(".git", "")
    return {
        "repo_name": repo_name_str,
        "analysis_id": analysis_id,
        "mode": "overview",
        "stats": {
            "total_files": len(files),
            "total_symbols": len(symbols),
            "total_capabilities": len(capabilities),
            "total_routes": len(routes),
            "top_level_folders": len(folder_file_counts),
        },
        "nodes": overview_nodes,
        "edges": overview_edges,
    }


@router.get("/{repo_name}/knowledge-graph/expand/{node_id:path}")
def get_knowledge_graph_expand(
    repo_name: str,
    node_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Expand a directory or file node to reveal its direct children.

    - Expanding a directory node (id starts with 'dir:') returns:
      - Subdirectory nodes one level deeper
      - File nodes directly inside that directory (not deeper)
      - Relationships between the returned files (IMPORTS, etc.)

    - Expanding a file node (id starts with a fact-store file ID) returns:
      - All symbols declared in that file
      - Relationships originating from those symbols (CALLS, IMPORTS, INHERITS, etc.)
      - Neighboring file nodes if referenced

    The caller appends the returned nodes/edges to the existing graph without
    replacing it, preserving the current layout and camera position.
    """
    try:
        repo, analysis = get_latest_analysis(repo_name, db, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GRAPH_EXPAND] Failed to resolve repository {repo_name}: {e}")
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    analysis_id = analysis.id
    logger.info(f"[GRAPH_EXPAND] Expanding node_id='{node_id}' for repo='{repo_name}', analysis_id={analysis_id}")

    new_nodes: List[Dict[str, Any]] = []
    new_edges: List[Dict[str, Any]] = []

    if node_id.startswith("dir:"):
        # ── DIRECTORY EXPANSION ──────────────────────────────────────────────
        folder_path = node_id[4:]  # strip "dir:" prefix

        # All files in this analysis
        all_files = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).all()

        # Find files whose path starts with this folder
        prefix = (folder_path + "/") if folder_path != "__root__" else ""
        matched_files = [
            f for f in all_files
            if (f.path.replace("\\", "/").startswith(prefix) if prefix else "/" not in f.path.replace("\\", "/").strip("/"))
        ]

        # Group into direct children: immediate sub-folders or files at exactly one level deeper
        direct_children_folders: Dict[str, int] = {}  # subfolder_name -> file count
        direct_files: List[Any] = []

        for f in matched_files:
            relative = f.path.replace("\\", "/").strip("/")
            if prefix:
                relative = relative[len(prefix):]
            parts = relative.split("/")
            if len(parts) == 1:
                # File directly in this folder
                direct_files.append(f)
            elif len(parts) > 1:
                # Goes deeper — add immediate sub-folder
                sub = parts[0]
                direct_children_folders[sub] = direct_children_folders.get(sub, 0) + 1

        # Emit sub-folder nodes
        for sub_folder, count in sorted(direct_children_folders.items()):
            child_path = f"{folder_path}/{sub_folder}" if folder_path != "__root__" else sub_folder
            child_id = f"dir:{child_path}"
            new_nodes.append({
                "id": child_id,
                "name": sub_folder,
                "label": sub_folder,
                "full_name": child_path,
                "type": "DIRECTORY",
                "file_count": count,
                "expandable": True,
                "expanded": False,
                "metadata": {"folder": child_path},
            })
            new_edges.append({
                "id": f"e-dir-{node_id}->{child_id}",
                "source": node_id,
                "target": child_id,
                "type": "CONTAINS",
                "status": "CONFIRMED",
            })

        # Emit direct file nodes (cap at 80 to stay performant)
        for f in direct_files[:80]:
            basename = f.path.split("/")[-1] if "/" in f.path else f.path
            new_nodes.append({
                "id": f.id,
                "name": basename,
                "label": basename,
                "full_name": f.path,
                "type": "FILE",
                "file": f.path,
                "language": f.language,
                "size": f.size,
                "expandable": True,
                "expanded": False,
                "metadata": {"is_test": f.is_test, "is_doc": f.is_documentation},
            })
            new_edges.append({
                "id": f"e-dir-file-{node_id}->{f.id}",
                "source": node_id,
                "target": f.id,
                "type": "CONTAINS",
                "status": "CONFIRMED",
            })

        # Add import-level edges between the returned files (IMPORTS between them)
        file_ids = {f.id for f in direct_files[:80]}
        if file_ids:
            import_rels = (
                db.query(FactRelationship)
                .filter(
                    FactRelationship.analysis_id == analysis_id,
                    FactRelationship.rel_type == "IMPORTS",
                    FactRelationship.from_symbol_id.in_(file_ids),
                    FactRelationship.to_symbol_id.in_(file_ids),
                )
                .limit(200)
                .all()
            )
            for r in import_rels:
                new_edges.append({
                    "id": r.id,
                    "source": r.from_symbol_id,
                    "target": r.to_symbol_id,
                    "type": "IMPORTS",
                    "evidence_line": r.evidence_line,
                    "status": r.status or "CONFIRMED",
                })

    elif node_id.startswith("cap:"):
        # ── CAPABILITY EXPANSION ─────────────────────────────────────────────
        cap_id = node_id[4:]
        cap_members = (
            db.query(FactCapabilityMember)
            .filter(FactCapabilityMember.capability_id == cap_id)
            .all()
        )
        sym_ids = [m.symbol_id for m in cap_members]
        symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.id.in_(sym_ids),
        ).all()
        sym_file_ids = {s.file_id for s in symbols if s.file_id}
        files_map = {}
        if sym_file_ids:
            for f in db.query(FactFile).filter(FactFile.id.in_(sym_file_ids)).all():
                files_map[f.id] = f

        for s in symbols:
            stype = (s.symbol_type or "symbol").upper()
            fpath = files_map[s.file_id].path if s.file_id and s.file_id in files_map else ""
            new_nodes.append({
                "id": s.id,
                "name": s.name,
                "label": s.name,
                "full_name": s.qualified_name or s.name,
                "type": stype,
                "file": fpath,
                "line_start": s.line_start,
                "line_end": s.line_end,
                "expandable": False,
                "expanded": False,
                "metadata": {},
            })
            new_edges.append({
                "id": f"e-cap-member-{node_id}->{s.id}",
                "source": node_id,
                "target": s.id,
                "type": "CAPABILITY_MEMBER",
                "status": "CONFIRMED",
            })

    else:
        # ── FILE EXPANSION ───────────────────────────────────────────────────
        file_obj = db.query(FactFile).filter(
            FactFile.analysis_id == analysis_id,
            FactFile.id == node_id,
        ).first()

        if not file_obj:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

        # Get symbols in this file
        symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.file_id == node_id,
        ).all()

        sym_ids = {s.id for s in symbols}

        for s in symbols:
            stype = (s.symbol_type or "symbol").upper()
            new_nodes.append({
                "id": s.id,
                "name": s.name,
                "label": s.name,
                "full_name": s.qualified_name or s.name,
                "type": stype,
                "file": file_obj.path,
                "line_start": s.line_start,
                "line_end": s.line_end,
                "expandable": False,
                "expanded": False,
                "metadata": {},
            })
            new_edges.append({
                "id": f"e-file-sym-{node_id}->{s.id}",
                "source": node_id,
                "target": s.id,
                "type": "DECLARES",
                "status": "CONFIRMED",
            })

        # Relationships between symbols in this file
        if sym_ids:
            internal_rels = (
                db.query(FactRelationship)
                .filter(
                    FactRelationship.analysis_id == analysis_id,
                    FactRelationship.from_symbol_id.in_(sym_ids),
                    FactRelationship.to_symbol_id.in_(sym_ids),
                )
                .limit(300)
                .all()
            )
            for r in internal_rels:
                new_edges.append({
                    "id": r.id,
                    "source": r.from_symbol_id,
                    "target": r.to_symbol_id,
                    "type": (r.rel_type or "GENERIC").upper(),
                    "evidence_line": r.evidence_line,
                    "status": r.status or "CONFIRMED",
                })

            outgoing_rels = (
                db.query(FactRelationship)
                .filter(
                    FactRelationship.analysis_id == analysis_id,
                    FactRelationship.from_symbol_id.in_(sym_ids),
                    ~FactRelationship.to_symbol_id.in_(sym_ids),
                    FactRelationship.rel_type.in_(["CALLS", "IMPORTS", "INHERITS"]),
                )
                .limit(50)
                .all()
            )
            out_target_ids = {r.to_symbol_id for r in outgoing_rels}
            out_targets = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis_id,
                FactSymbol.id.in_(out_target_ids),
            ).all() if out_target_ids else []
            out_target_map = {s.id: s for s in out_targets}
            out_file_ids = {s.file_id for s in out_targets if s.file_id}
            out_files = {}
            if out_file_ids:
                for f in db.query(FactFile).filter(FactFile.id.in_(out_file_ids)).all():
                    out_files[f.id] = f

            for s in out_targets:
                if s.id not in sym_ids:
                    stype = (s.symbol_type or "symbol").upper()
                    fpath = out_files[s.file_id].path if s.file_id and s.file_id in out_files else ""
                    new_nodes.append({
                        "id": s.id,
                        "name": s.name,
                        "label": s.name,
                        "full_name": s.qualified_name or s.name,
                        "type": stype,
                        "file": fpath,
                        "line_start": s.line_start,
                        "line_end": s.line_end,
                        "expandable": False,
                        "expanded": False,
                        "metadata": {},
                    })

            for r in outgoing_rels:
                if r.to_symbol_id in out_target_map:
                    new_edges.append({
                        "id": r.id,
                        "source": r.from_symbol_id,
                        "target": r.to_symbol_id,
                        "type": (r.rel_type or "GENERIC").upper(),
                        "evidence_line": r.evidence_line,
                        "status": r.status or "CONFIRMED",
                    })

    return {
        "expanded_node_id": node_id,
        "new_nodes": new_nodes,
        "new_edges": new_edges,
    }
