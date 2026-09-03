import logging
from typing import Dict, List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.models.repository import AnalysisArtifact, Analysis
from backend.dependencies.auth import get_current_user
from backend.routers.repo.services.analysis import get_latest_analysis
from backend.routers.repo.services.models import get_or_build_model
from backend.services.indexing_health_service import get_indexing_health

logger = logging.getLogger(__name__)

health_router = APIRouter(tags=["health"])

@health_router.get("/{repo_name}/health/findings")
def get_health_findings(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "findings").first()
    return {"findings": art.data if art else []}

@health_router.get("/{repo_name}/health/cycles")
def get_health_cycles(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "cycles").first()
    return {"cycles": art.data if art else []}

@health_router.get("/{repo_name}/health/scores")
def get_health_scores(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    
    findings_art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "findings").first()
    findings = findings_art.data if findings_art else []
    
    deduction = 0.0
    
    for f in findings:
        severity = f.get("severity", "INFO").upper()
        if severity in ["CRITICAL", "ERROR"]:
            deduction += 5.0
        elif severity == "WARNING":
            deduction += 2.0
        else:
            deduction += 0.5
            
    m_score = max(0.0, 100.0 - deduction * 0.4)
    r_score = max(0.0, 100.0 - deduction * 0.3)
    s_score = max(0.0, 100.0 - deduction * 0.3)
    
    final_score = (m_score * 0.4) + (r_score * 0.3) + (s_score * 0.3)
    
    if final_score > 90:
        status = "Excellent"
    elif final_score > 75:
        status = "Good"
    elif final_score > 50:
        status = "Fair"
    else:
        status = "Needs Work"
        
    return {
        "health_score": round(final_score),
        "status": status,
        "categories": {
            "maintainability": {
                "score": m_score,
                "weight": 0.4,
                "explanation": "Code maintainability based on complexity and structure."
            },
            "reliability": {
                "score": r_score,
                "weight": 0.3,
                "explanation": "Likelihood of bugs and runtime issues."
            },
            "security": {
                "score": s_score,
                "weight": 0.3,
                "explanation": "Security vulnerabilities and safe coding practices."
            }
        }
    }

@health_router.get("/{repo_name}/health/metrics")
def get_health_metrics(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "metrics").first()
    return art.data if art else {}

@health_router.get("/{repo_name}/health/layers")
def get_health_layers(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Derive layers from entity types: group files/dirs by top-level directory
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        from backend.intelligence.rim.enums import EntityType
        layer_map: Dict[str, List[str]] = {}
        for e in query_layer.model.entities.values():
            if e.type == EntityType.FILE:
                parts = Path(e.location.repository_path).parts
                layer = parts[0] if len(parts) > 1 else "root"
                layer_map.setdefault(layer, []).append(e.location.repository_path)
        layers = [{"module_id": k, "files": v, "file_count": len(v)} for k, v in layer_map.items()]
        return {"layers": layers}
    except HTTPException:
        return {"layers": []}

@health_router.get("/{repo_name}/health/dependencies")
def get_health_dependencies(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        from backend.intelligence.rim.enums import RelationshipType
        edges = [
            {"source": r.source_id, "target": r.target_id, "type": r.type.value}
            for r in query_layer.model.relationships.values()
            if r.type == RelationshipType.DEPENDS_ON or r.type == RelationshipType.IMPORTS
        ]
        return {"edges": edges}
    except HTTPException:
        return {"edges": []}

@health_router.get("/{repo_name}/health/dead-code")
def get_health_dead_code(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Heuristic: entities with no incoming relationships
    try:
        query_layer = get_or_build_model(repo_name, db, current_user)
        from backend.intelligence.rim.enums import EntityType
        referenced_ids = {r.target_id for r in query_layer.model.relationships.values()}
        dead = [
            {"id": e.id, "name": e.name, "type": e.type.value, "file": e.location.repository_path}
            for e in query_layer.model.entities.values()
            if e.type in (EntityType.FUNCTION, EntityType.METHOD)
            and e.id not in referenced_ids
        ]
        return {"findings": dead[:50]}
    except HTTPException:
        return {"findings": []}

@health_router.get("/{repo_name}/health/smells")
def get_health_smells(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Derive smells from findings artifact (stored during analysis) and model patterns
    try:
        repo, analysis = get_latest_analysis(repo_name, db, current_user)
    except HTTPException:
        return {"smells": []}

    findings_art = db.query(AnalysisArtifact).filter(
        AnalysisArtifact.analysis_id == analysis.id,
        AnalysisArtifact.type == "findings"
    ).first()
    findings = findings_art.data if findings_art else []

    smells = []
    for f in findings:
        severity = f.get("severity", "").upper() if isinstance(f, dict) else ""
        if severity in ("ERROR", "CRITICAL", "WARNING"):
            smells.append({
                "type": f.get("type", "Finding") if isinstance(f, dict) else "Finding",
                "severity": severity,
                "description": f.get("description", "") if isinstance(f, dict) else str(f),
                "file_path": f.get("file_path", "") if isinstance(f, dict) else ""
            })
    return {"smells": smells}

@health_router.get("/{repo_name}/health/indexing")
def get_indexing_health_status(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get indexing health status for retrieval indexes (BM25, Chroma, exact search)."""
    repo, analysis = get_latest_analysis(repo_name, db, current_user)

    health = get_indexing_health(db, analysis.id)
    if not health:
        return {
            "analysis_id": analysis.id,
            "analysis_status": analysis.status,
            "indexing_status": analysis.indexing_status,
            "indexed_at": analysis.indexed_at.isoformat() if analysis.indexed_at else None,
            "indexes": {
                "exact": {"status": "UNKNOWN", "document_count": None},
                "bm25": {"status": "UNKNOWN", "document_count": None},
                "semantic": {"status": "UNKNOWN", "document_count": None},
            }
        }

    return {
        "analysis_id": analysis.id,
        "analysis_status": analysis.status,
        "indexing_status": health.overall_status.value,
        "indexed_at": analysis.indexed_at.isoformat() if analysis.indexed_at else None,
        "indexes": {
            "exact": {
                "status": health.exact.status.value,
                "document_count": health.exact.document_count,
                "error": health.exact.error_code.value if health.exact.error_code else None,
            },
            "bm25": {
                "status": health.bm25.status.value,
                "document_count": health.bm25.document_count,
                "error": health.bm25.error_code.value if health.bm25.error_code else None,
            },
            "semantic": {
                "status": health.semantic.status.value,
                "document_count": health.semantic.document_count,
                "error": health.semantic.error_code.value if health.semantic.error_code else None,
            },
        }
    }
