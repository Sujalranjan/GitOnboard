#!/usr/bin/env python3
"""
Test Tool #1 (Symbol Inspection) with REAL repository data.

This test:
1. Connects to the database
2. Gets GitOnBoard repository (this project itself)
3. Verifies repository_hash exists
4. Tests inspect_symbol() with a real symbol from the repo
5. Validates the response against expected metadata
"""

import sys
import uuid
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime

def test_tool1_real_data():
    """Test Tool #1 with real repository and symbol data."""

    print("=" * 70)
    print("TEST: Tool #1 (Symbol Inspection) with Real Repository Data")
    print("=" * 70)

    # Step 1: Connect to database
    print("\n[1] Connecting to database...")
    try:
        engine = create_engine(
            'postgresql://postgres:postgres@localhost:5432/repository_intelligence',
            echo=False
        )
        Session = sessionmaker(bind=engine)
        db = Session()
        print("✅ Database connected")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

    try:
        # Step 2: Import models
        print("\n[2] Importing models...")
        from backend.models.repository import Repository, Analysis
        from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
        from backend.intelligence.inspection.symbol_inspector import inspect_symbol
        print("✅ Models imported")

        # Step 3: Find GitOnBoard repository
        print("\n[3] Finding GitOnBoard (current) repository...")
        repos = db.query(Repository).filter(
            Repository.name.ilike('%repository%') |
            Repository.name.ilike('%gitonboard%')
        ).limit(5).all()

        if not repos:
            print(f"❌ No repositories found. Available repos:")
            all_repos = db.query(Repository).limit(10).all()
            for repo in all_repos:
                print(f"   - {repo.name} (id={repo.id})")
            db.close()
            return False

        repo = repos[0]
        print(f"✅ Found repository: {repo.name}")

        # Step 4: Verify repository_hash exists
        print(f"\n[4] Checking repository_hash...")
        if not hasattr(repo, 'repository_hash') or not repo.repository_hash:
            print(f"❌ Repository has no repository_hash. Need to run migration first.")
            print(f"   Run: psql -U postgres repository_intelligence < backend/migrations/add_repository_hash.sql")
            db.close()
            return False

        repo_hash = repo.repository_hash
        print(f"✅ Repository hash (UUID): {repo_hash}")
        print(f"   Format: {type(repo_hash).__name__} (length: {len(str(repo_hash))})")

        # Validate UUID format
        try:
            uuid.UUID(str(repo_hash))
            print(f"✅ Valid UUID v4 format")
        except ValueError:
            print(f"❌ Invalid UUID format: {repo_hash}")
            db.close()
            return False

        # Step 5: Find completed analysis
        print(f"\n[5] Finding latest completed analysis...")
        analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()

        if not analysis:
            print(f"❌ No completed analysis found for repository")
            analyses = db.query(Analysis).filter(
                Analysis.repository_id == repo.id
            ).all()
            print(f"   Available analyses: {len(analyses)}")
            for a in analyses:
                print(f"   - {a.id} (status={a.status})")
            db.close()
            return False

        analysis_id = analysis.id
        print(f"✅ Found completed analysis: {analysis_id}")
        print(f"   Created: {analysis.created_at}")
        print(f"   Status: {analysis.status}")

        # Step 6: Find a FactFile in this repository
        print(f"\n[6] Finding a file in the repository...")
        fact_file = db.query(FactFile).filter(
            FactFile.analysis_id == analysis_id,
            FactFile.path.ilike('%.py')
        ).first()

        if not fact_file:
            print(f"❌ No Python files found in analysis")
            db.close()
            return False

        file_path = fact_file.path
        print(f"✅ Found file: {file_path}")

        # Step 7: Find a symbol in this file
        print(f"\n[7] Finding a symbol in {file_path}...")
        symbol = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.file_id == fact_file.id
        ).first()

        if not symbol:
            print(f"❌ No symbols found in file")
            db.close()
            return False

        symbol_name = symbol.name
        print(f"✅ Found symbol: {symbol_name}")
        print(f"   Type: {symbol.symbol_type}")
        print(f"   Qualified: {symbol.qualified_name}")
        print(f"   Lines: {symbol.line_start}-{symbol.line_end}")

        # Step 8: TEST inspect_symbol() with repo_hash
        print(f"\n[8] TESTING inspect_symbol() with repo_hash...")
        print(f"   Parameters:")
        print(f"   - file_path: {file_path}")
        print(f"   - symbol_name: {symbol_name}")
        print(f"   - repo_hash: {repo_hash}")
        print(f"   - db: Session")

        result = inspect_symbol(
            file_path=file_path,
            symbol_name=symbol_name,
            repo_hash=repo_hash,
            db=db
        )

        # Step 9: Validate result
        print(f"\n[9] Validating result...")

        # Check success flag
        if not result.success:
            print(f"❌ Tool returned error: {result.error}")
            if result.candidates:
                print(f"   Candidates: {result.candidates}")
            db.close()
            return False

        print(f"✅ Tool executed successfully")
        print(f"\n   Result Details:")
        print(f"   - success: {result.success}")
        print(f"   - name: {result.name}")
        print(f"   - symbol_id: {result.symbol_id}")
        print(f"   - qualified_name: {result.qualified_name}")
        print(f"   - symbol_type: {result.symbol_type}")
        print(f"   - file_path: {result.file_path}")
        print(f"   - lines: {result.line_start}-{result.line_end}")
        print(f"   - language: {result.language}")
        print(f"   - signature: {result.signature[:100] if result.signature else 'None'}...")
        print(f"   - docstring: {result.docstring[:100] if result.docstring else 'None'}...")

        # Validate key fields
        assert result.name == symbol_name, f"Name mismatch: {result.name} != {symbol_name}"
        assert result.file_path == file_path, f"File path mismatch: {result.file_path} != {file_path}"
        assert result.symbol_type == symbol.symbol_type, f"Type mismatch"
        assert result.line_start == symbol.line_start, f"Line start mismatch"
        assert result.line_end == symbol.line_end, f"Line end mismatch"

        print(f"\n✅ All assertions passed!")

        # Step 10: Test relationships
        print(f"\n[10] Checking relationships...")
        if result.relationships:
            print(f"✅ Relationships found:")
            if result.relationships.calls:
                print(f"   - Calls: {len(result.relationships.calls)} items")
            if result.relationships.called_by:
                print(f"   - Called by: {len(result.relationships.called_by)} items")
            if result.relationships.imports:
                print(f"   - Imports: {len(result.relationships.imports)} items")
            if result.relationships.imported_by:
                print(f"   - Imported by: {len(result.relationships.imported_by)} items")
            if result.relationships.uses:
                print(f"   - Uses: {len(result.relationships.uses)} items")
            if result.relationships.used_by:
                print(f"   - Used by: {len(result.relationships.used_by)} items")
        else:
            print(f"⚠️  No relationships found (may be empty)")

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED - Tool #1 works with real data!")
        print("=" * 70)

        db.close()
        return True

    except Exception as e:
        import traceback
        print(f"\n❌ Test failed with error: {e}")
        traceback.print_exc()
        db.close()
        return False

if __name__ == "__main__":
    success = test_tool1_real_data()
    sys.exit(0 if success else 1)
