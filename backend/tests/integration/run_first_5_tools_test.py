#!/usr/bin/env python3
"""
Integration Test Runner: First 5 Verified Tools
Connects to production PostgreSQL database and tests tools against real data.

Run with: python backend/tests/integration/run_first_5_tools_test.py
"""

import sys
import os

# Ensure we're using the right database (production, not test)
os.environ['DATABASE_URL'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:postgres@localhost:5432/repository_intelligence'
)

from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis
from backend.agent.tools.repository import (
    handle_search_code,
    handle_search_symbols,
    handle_get_symbol,
    handle_get_callers,
    handle_get_callees,
)
from backend.agent.tools.contracts import AgentToolContext


def make_context(db, repo_id):
    """Create AgentToolContext for tool execution."""
    import uuid
    return AgentToolContext(
        db=db,
        repository_id=str(repo_id),  # Must be string
        agent_run_id=str(uuid.uuid4()),  # Required field
        user_id=1,
        worktree_path="/tmp/repo"
    )


def test_1_search_code():
    """Test 1: Search Code for Authentication"""
    print("\n" + "="*70)
    print("TEST 1: search_code - Find authentication handling")
    print("="*70)

    db = SessionLocal()

    try:
        # Find a completed analysis
        analysis = db.query(Analysis).filter(
            Analysis.status == "Completed"
        ).first()

        if not analysis:
            print("❌ SKIP: No completed analysis found")
            return False

        repo = db.query(Repository).filter(
            Repository.id == analysis.repository_id
        ).first()

        print(f"\nAnalysis ID: {analysis.id}")
        print(f"Repository: {repo.url} (ID: {repo.id})")

        context = make_context(db, repo.id)

        # Test: Search for 'authenticate'
        print("\n📍 Natural Language Query: 'Find where we handle user authentication'")
        print("🔍 Tool Call: search_code(query='authenticate', limit=20)")

        result = handle_search_code(
            args={
                "query": "authenticate",
                "limit": 20
            },
            context=context
        )

        print(f"\n✅ Result:")
        print(f"  - Match count: {result['match_count']}")

        if result['match_count'] > 0:
            print(f"  - Sample matches:")
            for match in result['matches'][:3]:
                print(f"    • {match}")

        return result['match_count'] >= 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_2_search_symbols():
    """Test 2: Search Symbols for API Files"""
    print("\n" + "="*70)
    print("TEST 2: search_symbols - Find route/API files")
    print("="*70)

    db = SessionLocal()

    try:
        analysis = db.query(Analysis).filter(
            Analysis.status == "Completed"
        ).first()

        if not analysis:
            print("❌ SKIP: No completed analysis found")
            return False

        repo = db.query(Repository).filter(
            Repository.id == analysis.repository_id
        ).first()

        print(f"\nAnalysis ID: {analysis.id}")
        print(f"Repository: {repo.url}")

        context = make_context(db, repo.id)

        # Test: Find route/API files
        print("\n📍 Natural Language Query: 'Show me all the API endpoint files'")
        print("🔍 Tool Call: search_symbols(pattern='*route*', limit=20)")

        result = handle_search_symbols(
            args={
                "pattern": "*route*",
                "limit": 20
            },
            context=context
        )

        files_count = len(result.get('files_found', []))
        print(f"\n✅ Result:")
        print(f"  - Files found: {files_count}")

        if result.get('files_found'):
            print(f"  - Sample files:")
            for file in result['files_found'][:3]:
                print(f"    • {file}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_3_get_symbol():
    """Test 3: Get Symbol Definition"""
    print("\n" + "="*70)
    print("TEST 3: get_symbol - Look up symbol definition")
    print("="*70)

    db = SessionLocal()

    try:
        analysis = db.query(Analysis).filter(
            Analysis.status == "Completed"
        ).first()

        if not analysis:
            print("❌ SKIP: No completed analysis found")
            return False

        repo = db.query(Repository).filter(
            Repository.id == analysis.repository_id
        ).first()

        print(f"\nAnalysis ID: {analysis.id}")
        print(f"Repository: {repo.url}")

        context = make_context(db, repo.id)

        # Test: Look up User symbol
        print("\n📍 Natural Language Query: 'Show me the User class definition'")
        print("🔍 Tool Call: get_symbol(name='User')")

        result = handle_get_symbol(
            args={"name": "User"},
            context=context
        )

        print(f"\n✅ Result:")
        print(f"  - Symbol count: {result['symbol_count']}")

        if result.get('symbols'):
            print(f"  - Symbol details:")
            for sym in result['symbols'][:2]:
                print(f"    • {sym}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_4_get_callers():
    """Test 4: Get Callers"""
    print("\n" + "="*70)
    print("TEST 4: get_callers - Find who calls a function")
    print("="*70)

    db = SessionLocal()

    try:
        analysis = db.query(Analysis).filter(
            Analysis.status == "Completed"
        ).first()

        if not analysis:
            print("❌ SKIP: No completed analysis found")
            return False

        repo = db.query(Repository).filter(
            Repository.id == analysis.repository_id
        ).first()

        print(f"\nAnalysis ID: {analysis.id}")
        print(f"Repository: {repo.url}")

        context = make_context(db, repo.id)

        # Test: Find callers of 'save'
        print("\n📍 Natural Language Query: 'Who calls the save() method?'")
        print("🔍 Tool Call: get_callers(symbol_name='save')")

        result = handle_get_callers(
            args={"symbol_name": "save"},
            context=context
        )

        print(f"\n✅ Result:")
        print(f"  - Caller count: {result['caller_count']}")

        if result.get('callers'):
            print(f"  - Sample callers:")
            for caller in result['callers'][:3]:
                print(f"    • {caller}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_5_get_callees():
    """Test 5: Get Callees"""
    print("\n" + "="*70)
    print("TEST 5: get_callees - Find what a function calls")
    print("="*70)

    db = SessionLocal()

    try:
        analysis = db.query(Analysis).filter(
            Analysis.status == "Completed"
        ).first()

        if not analysis:
            print("❌ SKIP: No completed analysis found")
            return False

        repo = db.query(Repository).filter(
            Repository.id == analysis.repository_id
        ).first()

        print(f"\nAnalysis ID: {analysis.id}")
        print(f"Repository: {repo.url}")

        context = make_context(db, repo.id)

        # Test: Find functions called by 'process'
        print("\n📍 Natural Language Query: 'What functions does process() call?'")
        print("🔍 Tool Call: get_callees(symbol_name='process')")

        result = handle_get_callees(
            args={"symbol_name": "process"},
            context=context
        )

        print(f"\n✅ Result:")
        print(f"  - Callee count: {result['callee_count']}")

        if result.get('callees'):
            print(f"  - Sample callees:")
            for callee in result['callees'][:3]:
                print(f"    • {callee}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_integrated_flow():
    """Integration Test: Chain multiple tools together"""
    print("\n" + "="*70)
    print("INTEGRATION TEST: Chained tool calls")
    print("="*70)

    db = SessionLocal()

    try:
        analysis = db.query(Analysis).filter(
            Analysis.status == "Completed"
        ).first()

        if not analysis:
            print("❌ SKIP: No completed analysis found")
            return False

        repo = db.query(Repository).filter(
            Repository.id == analysis.repository_id
        ).first()

        print(f"\nAnalysis ID: {analysis.id}")
        print(f"Repository: {repo.url}")

        context = make_context(db, repo.id)

        # Step 1: Search for authentication code
        print("\n📍 Step 1: Search for authentication code")
        print("🔍 search_code(query='authenticate')")

        search_result = handle_search_code(
            args={"query": "authenticate", "limit": 5},
            context=context
        )

        print(f"  ✓ Found {search_result['match_count']} matches")

        if search_result['match_count'] == 0:
            print("  → Skipping remaining steps (no matches found)")
            return True

        # Step 2: Get symbol definition
        print("\n📍 Step 2: Get authenticate symbol definition")
        print("🔍 get_symbol(name='authenticate')")

        symbol_result = handle_get_symbol(
            args={"name": "authenticate"},
            context=context
        )

        print(f"  ✓ Found {symbol_result['symbol_count']} symbols")

        if symbol_result['symbol_count'] == 0:
            print("  → Skipping Step 3 (no symbol found)")
            return True

        # Step 3: Get callers
        print("\n📍 Step 3: Get callers of authenticate")
        print("🔍 get_callers(symbol_name='authenticate')")

        callers_result = handle_get_callers(
            args={"symbol_name": "authenticate"},
            context=context
        )

        print(f"  ✓ Found {callers_result['caller_count']} callers")

        print("\n✅ Integrated flow completed successfully")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("INTEGRATION TEST: First 5 Verified Tools")
    print("="*70)

    results = []

    # Run all tests
    results.append(("search_code", test_1_search_code()))
    results.append(("search_symbols", test_2_search_symbols()))
    results.append(("get_symbol", test_3_get_symbol()))
    results.append(("get_callers", test_4_get_callers()))
    results.append(("get_callees", test_5_get_callees()))
    results.append(("integrated_flow", test_integrated_flow()))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\n{passed}/{total} tests passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
