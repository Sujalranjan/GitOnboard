import sys
import os
sys.path.append(os.getcwd())

from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisArtifact

db = SessionLocal()
repos = db.query(Repository).all()
for r in repos:
    print(f"Repo: {r.url}")
    latest = db.query(Analysis).filter(Analysis.repository_id == r.id).order_by(Analysis.created_at.desc()).first()
    if latest:
        print(f"  Latest Analysis ID: {latest.id}, Status: {latest.status}")
        em = db.query(AnalysisArtifact).filter(AnalysisArtifact.analysis_id == latest.id, AnalysisArtifact.type == "enriched_metadata").first()
        if em:
            print(f"  Has enriched_metadata: YES")
            print(f"  Primary language: {em.data.get('repository', {}).get('primary_language')}")
            print(f"  Languages: {em.data.get('repository', {}).get('languages')}")
        else:
            print(f"  Has enriched_metadata: NO")
    else:
        print(f"  No analysis found.")
