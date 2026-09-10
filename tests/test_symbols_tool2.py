#!/usr/bin/env python3
"""
Test Tool #2 (File Retrieval) - Read file content from Azure Blob Storage.
"""

import sys
import os
os.environ["DATABASE_HOST"] = "repository_intelligence_platform-postgres-1"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+psycopg://myuser:mypassword@repository_intelligence_platform-postgres-1:5432/repository_intelligence"

def test_file_retrieval():
    """Test Tool #2 File Retrieval - Read from Azure Blob Storage."""

    print("=" * 90)
    print("FILE RETRIEVAL TEST: Read from Azure Blob Storage")
    print("=" * 90)

    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        db = Session()

        from backend.models.repository import Repository, Analysis
        from backend.models.fact_store import FactFile
        from backend.storage import get_storage

        # Get GitOnboard repo
        repo = db.query(Repository).filter(
            Repository.url.like("%GitOnboard%")
        ).first()

        repo_hash = repo.repository_hash

        # Get latest analysis
        analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()

        print(f"\n📦 Repository: GitOnboard")
        print(f"🔑 UUID Hash: {repo_hash}")
        print(f"📊 Analysis ID: {analysis.id}")

        # Test: Read agent.py file
        print(f"\n{'='*90}")
        print("TEST: Reading backend/routers/agent.py from Azure Blob Storage")
        print(f"{'='*90}")

        fact_file = db.query(FactFile).filter(
            FactFile.analysis_id == analysis.id,
            FactFile.path == "backend/routers/agent.py"
        ).first()

        if not fact_file:
            print(f"❌ File not found in analysis")
            return False

        print(f"\n✅ File metadata from database:")
        print(f"   ├─ Path: {fact_file.path}")
        print(f"   ├─ Size: {fact_file.size:,} bytes")
        print(f"   ├─ Language: {fact_file.language}")
        print(f"   └─ Blob Name (UUID key): {fact_file.blob_name}")

        # Verify blob key uses UUID
        if repo_hash not in fact_file.blob_name:
            print(f"\n❌ ERROR: Blob key does not contain repository UUID!")
            print(f"   Expected: {repo_hash}")
            print(f"   Got: {fact_file.blob_name}")
            return False

        print(f"\n✅ Blob key uses repository_hash UUID:")
        print(f"   Format: repositories/{{UUID}}/snapshots/{{snapshot}}/{{path}}")
        print(f"   Actual: {fact_file.blob_name}")

        # Read from blob storage
        print(f"\n   Reading from Azure Blob Storage...")
        storage = get_storage()

        try:
            content = storage.get_object_text(fact_file.blob_name)

            if not content:
                print(f"❌ Blob returned empty content")
                return False

            print(f"✅ Successfully read {len(content):,} bytes from blob storage")

            # Verify content
            lines = content.split('\n')
            print(f"\n   📄 File Content:")
            print(f"      ├─ Total lines: {len(lines)}")
            print(f"      ├─ First line: {lines[0][:50]}...")

            # Find our test functions
            get_run_changes_line = None
            agent_response_line = None

            for i, line in enumerate(lines, 1):
                if 'def get_run_changes' in line:
                    get_run_changes_line = i
                if 'class AgentRunDetailResponse' in line:
                    agent_response_line = i

            print(f"      ├─ Line with 'get_run_changes': {get_run_changes_line}")
            print(f"      ├─ Line with 'AgentRunDetailResponse': {agent_response_line}")

            # Show snippets
            if agent_response_line:
                start = max(0, agent_response_line - 2)
                end = min(len(lines), agent_response_line + 3)
                print(f"\n   📋 AgentRunDetailResponse snippet:")
                for i in range(start, end):
                    print(f"      {i+1:4d}: {lines[i]}")

            if get_run_changes_line:
                start = max(0, get_run_changes_line - 1)
                end = min(len(lines), get_run_changes_line + 4)
                print(f"\n   📋 get_run_changes snippet:")
                for i in range(start, end):
                    print(f"      {i+1:4d}: {lines[i]}")

        except Exception as e:
            print(f"❌ Failed to read blob: {e}")
            return False

        # Summary
        print(f"\n{'='*90}")
        print("VERIFICATION")
        print(f"{'='*90}")

        print(f"\n✅ Tool #2 (File Retrieval) works perfectly:")
        print(f"   ├─ Repository identified by UUID: {repo_hash}")
        print(f"   ├─ File metadata retrieved from database")
        print(f"   ├─ Blob stored with UUID-based key")
        print(f"   └─ File content successfully read from Azure Blob Storage")

        print(f"\n🎯 Complete file retrieval pipeline using repository_hash UUID")

        db.close()
        return True

    except Exception as e:
        import traceback
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_file_retrieval()
    sys.exit(0 if success else 1)
