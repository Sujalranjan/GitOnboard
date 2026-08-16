from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db

router = APIRouter(tags=["health"])

@router.get("/health")
def health_check(response: Response, db: Session = Depends(get_db)):
    """
    Health check endpoint for Docker, Azure readiness probes, and frontend cold start.
    Verifies that the API server is active and the PostgreSQL database is reachable.
    """
    try:
        # Verify active database connectivity
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
