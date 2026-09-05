#!/usr/bin/env python3
"""
Import local GitOnboard repository through normal application flow.
"""
import time
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis, AnalysisJob
from backend.models.user import User
from backend.routers.repo.services.analysis import get_latest_analysis
from backend.dependencies.auth import get_or_create_local_dev_user

db = SessionLocal()

try:
    # Step 1: Get or create local dev user
    print("Step 1: Getting local development user...")
    user = get_or_create_local_dev_user(db)
    print(f"  User ID: {user.id}, Username: {user.username}")

    # Step 2: Check if GitOnboard already exists
    print("\nStep 2: Checking for existing GitOnboard repository...")
    existing_repos = db.query(Repository).filter(
        Repository.user_id == user.id,
        Repository.url.ilike('%salianDheeraj/GitOnboard%')
    ).all()

    if existing_repos:
        print(f"  Found {len(existing_repos)} existing GitOnboard repository(ies)")
        repo = existing_repos[0]
        print(f"  Using existing repository ID: {repo.id}")
    else:
        print("  No existing GitOnboard repository found")
        print("  Creating new repository record...")

        # Step 3: Create repository record
        repo = Repository(
            url="https://github.com/salianDheeraj/GitOnboard",
            default_branch="main",
            user_id=user.id
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        print(f"  Created repository ID: {repo.id}")

    # Step 4: Check for existing analyses
    print("\nStep 3: Checking for existing analyses...")
    existing_analyses = db.query(Analysis).filter(
        Analysis.repository_id == repo.id
    ).order_by(Analysis.created_at.desc()).all()

    if existing_analyses:
        print(f"  Found {len(existing_analyses)} existing analysis(es)")
        latest = existing_analyses[0]
        print(f"  Latest analysis ID: {latest.id}, Status: {latest.status}")

        # Check if latest is completed
        if latest.status == "Completed":
            print("  Latest analysis is completed. Ready for Phase 2F validation.")
            analysis = latest
        else:
            print(f"  Latest analysis status: {latest.status}")
            print("  Creating new analysis for fresh Phase 2F run...")
            analysis = Analysis(repository_id=repo.id)
            db.add(analysis)
            db.commit()
            db.refresh(analysis)
            print(f"  Created analysis ID: {analysis.id}")
    else:
        print("  No existing analyses found")
        print("  Creating new analysis...")
        analysis = Analysis(repository_id=repo.id)
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        print(f"  Created analysis ID: {analysis.id}")

    # Step 5: Summary
    print("\n" + "="*60)
    print("IMPORT SUMMARY")
    print("="*60)
    print(f"Repository ID: {repo.id}")
    print(f"Repository URL: {repo.url}")
    print(f"Repository User ID: {repo.user_id}")
    print(f"Analysis ID: {analysis.id}")
    print(f"Analysis Status: {analysis.status}")
    print(f"Analysis Created: {analysis.created_at}")
    print("="*60)

    # Step 6: Verify in database
    print("\nStep 4: Verifying repository in database...")
    verify_repo = db.query(Repository).filter(Repository.id == repo.id).first()
    verify_analyses = db.query(Analysis).filter(Analysis.repository_id == repo.id).all()

    print(f"  Repository verified: {verify_repo is not None}")
    print(f"  Analyses count: {len(verify_analyses)}")

    print("\n✓ GitOnboard repository imported successfully")
    print(f"\nRepository ID: {repo.id}")
    print(f"Analysis ID: {analysis.id}")
    print("\nReady for Phase 2F validation.")

finally:
    db.close()
