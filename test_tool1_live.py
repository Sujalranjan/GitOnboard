#!/usr/bin/env python3
"""
Test Tool #1 (Symbol Inspection) with real GitOnboard repository data.

This test uses the actual imported repository from Docker database.
"""

import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Database connection using Docker credentials (using psycopg3)
# Use 'postgres' hostname for Docker network (works when run inside container)
import os
docker_db_host = os.getenv("DATABASE_HOST", "repository_intelligence_platform-postgres-1")
DATABASE_URL = f"postgresql+psycopg://myuser:mypassword@{docker_db_host}:5432/repository_intelligence"

def test_tool1_live():
    """Test Tool #1 with live GitOnboard data."""

    print("=" * 80)
    print("LIVE TEST: Tool #1 (Symbol Inspection) with GitOnboard Repository")
    print("=" * 80)

    try:
        # Connect to database
        print("\n[1] Connecting to database...")
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        db = Session()
        print("✅ Connected to PostgreSQL database")

        # Import models and tool
        print("\n[2] Importing models and Symbol Inspection tool...")
        from backend.models.repository import Repository, Analysis
        from backend.models.fact_store import FactFile, FactSymbol
        from backend.intelligence.inspection.symbol_inspector import inspect_symbol
        print("✅ Models and tool imported")

        # Query the imported GitOnboard repository
        print("\n[3] Finding GitOnboard repository...")
        repo = db.query(Repository).filter(
            Repository.url.like("%GitOnboard%")
        ).first()

        if not repo:
            print("❌ GitOnboard repository not found")
            print("   Available repositories:")
            repos = db.query(Repository).all()
            for r in repos:
                print(f"   - {r.url}")
            db.close()
            return False

        print(f"✅ Found: {repo.url}")
        print(f"   Repository Hash (UUID): {repo.repository_hash}")

        # Get latest completed analysis
        print("\n[4] Finding completed analysis...")
        analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()

        if not analysis:
            print("❌ No completed analysis found")
            db.close()
            return False

        print(f"✅ Analysis ID: {analysis.id}")
        print(f"   Status: {analysis.status}")
        print(f"   Created: {analysis.created_at}")

        # Find a symbol to test
        print("\n[5] Finding a symbol to inspect...")
        symbol = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis.id,
            FactSymbol.symbol_type == "FUNCTION"
        ).first()

        if not symbol:
            print("❌ No symbols found")
            db.close()
            return False

        file = db.query(FactFile).filter(FactFile.id == symbol.file_id).first()
        file_path = file.path if file else "unknown"

        print(f"✅ Found symbol: {symbol.name}")
        print(f"   File: {file_path}")
        print(f"   Type: {symbol.symbol_type}")
        print(f"   Lines: {symbol.line_start}-{symbol.line_end}")

        # TEST: Call inspect_symbol with repo_hash
        print(f"\n[6] TESTING inspect_symbol() with repo_hash...")
        print(f"   Parameters:")
        print(f"   - file_path: {file_path}")
        print(f"   - symbol_name: {symbol.name}")
        print(f"   - repo_hash: {repo.repository_hash}")
        print(f"   - db: Session")

        result = inspect_symbol(
            file_path=file_path,
            symbol_name=symbol.name,
            repo_hash=repo.repository_hash,
            db=db
        )

        # Validate result
        print(f"\n[7] Validating result...")

        if not result.success:
            print(f"❌ Tool returned error: {result.error}")
            if result.candidates:
                print(f"   Candidates: {result.candidates}")
            db.close()
            return False

        print(f"✅ Tool executed successfully!")
        print(f"\n   Result Details:")
        print(f"   ├─ name: {result.name}")
        print(f"   ├─ symbol_id: {result.symbol_id}")
        print(f"   ├─ qualified_name: {result.qualified_name}")
        print(f"   ├─ symbol_type: {result.symbol_type}")
        print(f"   ├─ file_path: {result.file_path}")
        print(f"   ├─ lines: {result.line_start}-{result.line_end}")
        print(f"   ├─ language: {result.language}")
        print(f"   ├─ signature: {result.signature[:80] if result.signature else 'None'}{'...' if result.signature and len(result.signature) > 80 else ''}")
        print(f"   └─ relationships:")
        if result.relationships:
            if result.relationships.calls:
                print(f"      ├─ calls: {len(result.relationships.calls)} items")
            if result.relationships.called_by:
                print(f"      ├─ called_by: {len(result.relationships.called_by)} items")
            if result.relationships.imports:
                print(f"      ├─ imports: {len(result.relationships.imports)} items")
            if result.relationships.imported_by:
                print(f"      ├─ imported_by: {len(result.relationships.imported_by)} items")
            if result.relationships.uses:
                print(f"      ├─ uses: {len(result.relationships.uses)} items")
            if result.relationships.used_by:
                print(f"      └─ used_by: {len(result.relationships.used_by)} items")
        else:
            print(f"      └─ (none)")

        # Verify key fields match
        print(f"\n[8] Verifying data integrity...")
        checks = [
            ("Name matches", result.name == symbol.name),
            ("File path matches", result.file_path == file_path),
            ("Symbol type matches", result.symbol_type == symbol.symbol_type),
            ("Line start matches", result.line_start == symbol.line_start),
            ("Line end matches", result.line_end == symbol.line_end),
        ]

        all_passed = True
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"   {status} {check_name}")
            if not passed:
                all_passed = False

        print("\n" + "=" * 80)
        if all_passed:
            print("✅ ALL CHECKS PASSED - Tool #1 works perfectly with GitOnboard!")
        else:
            print("⚠️  Some checks failed - see details above")
        print("=" * 80)

        db.close()
        return all_passed

    except Exception as e:
        import traceback
        print(f"\n❌ Test failed with error: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_tool1_live()
    sys.exit(0 if success else 1)
