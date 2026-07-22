import logging
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.user import User
from backend.models.repository import AnalysisArtifact
from backend.routers.repo.services.analysis import get_latest_analysis

logger = logging.getLogger(__name__)

def get_or_build_model(repo_name: str, db: Session, current_user: User):
    repo, analysis = get_latest_analysis(repo_name, db, current_user)
    art = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == analysis.id, AnalysisArtifact.type == "core_model").first()
    if not art or not art.blob_data:
        raise HTTPException(status_code=404, detail="Model artifact not found")
    try:
        from backend.intelligence.rim.serialization import deserialize_rim
        model = deserialize_rim(art.blob_data.decode("utf-8"))
        from backend.intelligence import QueryLayer
        return QueryLayer(model)
    except Exception as e:
        logger.error(f"Failed to load model from json: {e}")
        raise HTTPException(status_code=500, detail="Failed to parse model")
