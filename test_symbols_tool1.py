#!/usr/bin/env python3
"""
Test Tool #1 (Symbol Inspection) with two specific symbols:
1. AgentRunDetailResponse (CLASS)
2. get_run_changes (FUNCTION)

Both from GitOnboard repository.
"""

import sys
import os
os.environ["DATABASE_HOST"] = "repository_intelligence_platform-postgres-1"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+psycopg://myuser:mypassword@repository_intelligence_platform-postgres-1:5432/repository_intelligence"

def test_symbols():
    """Test Tool #1 with both symbols."""

    print("=" * 90)
    print("SYMBOL INSPECTION TEST: get_run_changes & AgentRunDetailResponse")
    print("=" * 90)

    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        db = Session()

        from backend.models.repository import Repository
        from backend.intelligence.inspection.symbol_inspector import inspect_symbol

        # Get GitOnboard repo
        repo = db.query(Repository).filter(
            Repository.url.like("%GitOnboard%")
        ).first()

        if not repo:
            print("❌ GitOnboard repository not found")
            return False

        repo_hash = repo.repository_hash
        print(f"\n📦 Repository: GitOnboard")
        print(f"🔑 UUID Hash: {repo_hash}")

        # Test 1: AgentRunDetailResponse (CLASS)
        print(f"\n{'='*90}")
        print("TEST 1: AgentRunDetailResponse (CLASS)")
        print(f"{'='*90}")

        result1 = inspect_symbol(
            file_path="backend/routers/agent.py",
            symbol_name="AgentRunDetailResponse",
            repo_hash=repo_hash,
            db=db
        )

        print(f"✅ Symbol found: {result1.name}")
        print(f"  ├─ Type: {result1.symbol_type}")
        print(f"  ├─ File: {result1.file_path}")
        print(f"  ├─ Lines: {result1.line_start}-{result1.line_end}")
        print(f"  ├─ Qualified Name: {result1.qualified_name}")
        print(f"  ├─ Language: {result1.language}")
        print(f"  └─ Symbol ID: {result1.symbol_id}")

        if result1.relationships:
            print(f"\n  📊 Relationships:")
            if result1.relationships.calls:
                print(f"     ├─ Calls: {len(result1.relationships.calls)} items")
            if result1.relationships.called_by:
                print(f"     ├─ Called by: {len(result1.relationships.called_by)} items")
            if result1.relationships.uses:
                print(f"     ├─ Uses: {len(result1.relationships.uses)} items")
            if result1.relationships.used_by:
                print(f"     ├─ Used by: {len(result1.relationships.used_by)} items")
            if result1.relationships.imports:
                print(f"     └─ Imports: {len(result1.relationships.imports)} items")

        if not result1.success:
            print(f"❌ FAILED: {result1.error}")
            return False

        # Test 2: get_run_changes (FUNCTION)
        print(f"\n{'='*90}")
        print("TEST 2: get_run_changes (FUNCTION)")
        print(f"{'='*90}")

        result2 = inspect_symbol(
            file_path="backend/routers/agent.py",
            symbol_name="get_run_changes",
            repo_hash=repo_hash,
            db=db
        )

        print(f"✅ Symbol found: {result2.name}")
        print(f"  ├─ Type: {result2.symbol_type}")
        print(f"  ├─ File: {result2.file_path}")
        print(f"  ├─ Lines: {result2.line_start}-{result2.line_end}")
        print(f"  ├─ Qualified Name: {result2.qualified_name}")
        print(f"  ├─ Language: {result2.language}")
        print(f"  ├─ Signature: {result2.signature[:80] if result2.signature else 'None'}{'...' if result2.signature and len(result2.signature) > 80 else ''}")
        print(f"  └─ Symbol ID: {result2.symbol_id}")

        if result2.relationships:
            print(f"\n  📊 Relationships:")
            if result2.relationships.calls:
                print(f"     ├─ Calls: {len(result2.relationships.calls)} items")
                for call in result2.relationships.calls[:3]:
                    print(f"     │  ├─ → {call.name}")
                if len(result2.relationships.calls) > 3:
                    print(f"     │  └─ ... and {len(result2.relationships.calls) - 3} more")
            if result2.relationships.called_by:
                print(f"     ├─ Called by: {len(result2.relationships.called_by)} items")
                for caller in result2.relationships.called_by[:3]:
                    print(f"     │  ├─ ← {caller.name}")
                if len(result2.relationships.called_by) > 3:
                    print(f"     │  └─ ... and {len(result2.relationships.called_by) - 3} more")
            if result2.relationships.uses:
                print(f"     ├─ Uses: {len(result2.relationships.uses)} items")
            if result2.relationships.used_by:
                print(f"     ├─ Used by: {len(result2.relationships.used_by)} items")
            if result2.relationships.imports:
                print(f"     └─ Imports: {len(result2.relationships.imports)} items")

        if not result2.success:
            print(f"❌ FAILED: {result2.error}")
            return False

        # Summary
        print(f"\n{'='*90}")
        print("✅ ALL TESTS PASSED")
        print(f"{'='*90}")
        print(f"\n📋 Summary:")
        print(f"  Repository: GitOnboard (UUID: {repo_hash})")
        print(f"  File: backend/routers/agent.py")
        print(f"  Symbol 1: {result1.name} ({result1.symbol_type})")
        print(f"    ├─ Lines: {result1.line_start}-{result1.line_end}")
        print(f"    └─ Relationships: {len(result1.relationships.calls) if result1.relationships and result1.relationships.calls else 0} calls")
        print(f"  Symbol 2: {result2.name} ({result2.symbol_type})")
        print(f"    ├─ Lines: {result2.line_start}-{result2.line_end}")
        print(f"    └─ Relationships: {len(result2.relationships.calls) if result2.relationships and result2.relationships.calls else 0} calls, {len(result2.relationships.called_by) if result2.relationships and result2.relationships.called_by else 0} called by")
        print(f"\n🎯 Tool #1 (Symbol Inspection) works perfectly with both symbols!")

        db.close()
        return True

    except Exception as e:
        import traceback
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_symbols()
    sys.exit(0 if success else 1)
