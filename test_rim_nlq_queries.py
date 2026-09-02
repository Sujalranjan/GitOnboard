"""
Natural-Language Query Testing for RIM Implementation
Tests whether RIM can handle queries with different vocabulary than code.

NO CODE CHANGES - pure evaluation of existing implementation.
"""

import json
import time
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.services.rim_metadata import build_rim_metadata_block

# Test queries with different vocabulary than code
QUERIES = [
    "How does login work?",
    "How does user sign-in work?",
    "How are users authenticated?",
    "How are permissions checked?",
    "How does the application verify a user's identity?",
    "How does a user session get created?",
    "How are access tokens handled?",
    "How does request authorization work?",
]

def setup_test_db():
    """Create in-memory test database with realistic auth-related entities."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Create test user and repo
    user = User(id=1, github_id="test", username="test", email="test@test.com")
    db.add(user)
    db.flush()

    repo = Repository(id=1, url="https://github.com/test/deep-guard", user_id=user.id)
    db.add(repo)
    db.flush()

    analysis = Analysis(id=100, repository_id=repo.id, status="Completed")
    db.add(analysis)
    db.flush()

    # Create files
    files = {
        "auth.js": FactFile(id=1, analysis_id=analysis.id, path="middleware/auth.js", language="JavaScript"),
        "authcontroller.js": FactFile(id=2, analysis_id=analysis.id, path="controllers/authcontroller.js", language="JavaScript"),
    }
    for f in files.values():
        db.add(f)
    db.flush()

    # Create symbols matching Deep-Guard-Backend repo structure
    symbols_data = {
        "authMiddleware": ("middleware/auth.js", "function", "Middleware that validates JWT tokens and verifies user session"),
        "authenticateToken": ("middleware/auth.js", "function", "Validates JWT token expiration and signature"),
        "hashToken": ("middleware/auth.js", "function", "Generates or processes a secure token"),
        "createSession": ("controllers/authcontroller.js", "function", "Creates a new user session after authentication"),
        "verifyIdentity": ("controllers/authcontroller.js", "function", "Verifies user identity and credentials"),
        "checkPermissions": ("controllers/authcontroller.js", "function", "Checks if user has required permissions"),
        "setAuthCookies": ("controllers/authcontroller.js", "function", "Sets authentication cookies for the session"),
        "clearAuthCookies": ("controllers/authcontroller.js", "function", "Clears authentication cookies on logout"),
    }

    for idx, (name, (file_path, sym_type, doc)) in enumerate(symbols_data.items(), start=1):
        file_id = 1 if "middleware" in file_path else 2
        sym = FactSymbol(
            id=str(idx),
            analysis_id=analysis.id,
            name=name,
            qualified_name=f"auth.{name}",
            symbol_type=sym_type,
            file_id=file_id,
            line_start=10 + (idx * 20),
            line_end=30 + (idx * 20),
            metadata_json={"docstring": doc}
        )
        db.add(sym)

    db.commit()
    return db, analysis

def test_query(db, analysis, query):
    """Test a single query and collect detailed metrics."""
    print(f"\n{'='*80}")
    print(f"QUERY: {query}")
    print(f"{'='*80}")

    retriever = HybridRetriever(db, analysis_id=analysis.id)

    # Test retrieval
    start = time.time()
    results = retriever.retrieve(query, top_k=5, enable_fallback=True)
    retrieval_time = time.time() - start

    print(f"\n📊 RETRIEVAL")
    print(f"  Results Found: {len(results)}")
    print(f"  Latency: {retrieval_time*1000:.1f}ms")
    print(f"  Semantic Status: {retriever.semantic_degradation or 'Available'}")

    if results:
        print(f"\n  Retrieved Entities:")
        for i, r in enumerate(results[:5], 1):
            print(f"    {i}. {r.entity_name} ({r.entity_type}) - {r.score_type} score")

    # Test RIM metadata building
    print(f"\n🔗 RIM METADATA")
    start = time.time()
    metadata = build_rim_metadata_block(db, analysis.id, query, retriever, max_seed_entities=3)
    metadata_time = time.time() - start

    print(f"  Build Time: {metadata_time*1000:.1f}ms")
    print(f"  Seeds Found: {len(metadata.seed_entities)}")
    print(f"  Relationships: {len(metadata.relationships)}")

    if metadata.text and "No structural facts" not in metadata.text:
        print(f"  Metadata Quality: ✅ NON-EMPTY")
        print(f"  Metadata Preview:")
        for line in metadata.text.split("\n")[:5]:
            print(f"    {line}")
    else:
        print(f"  Metadata Quality: ❌ EMPTY")

    # Classify result
    if len(results) > 0 and "No structural facts" not in metadata.text:
        classification = "PASS"
    elif len(results) > 0:
        classification = "PARTIAL"
    else:
        classification = "FAIL"

    print(f"\n✓ Classification: {classification}")

    return {
        "query": query,
        "retrieved_count": len(results),
        "retrieved_entities": [r.entity_name for r in results[:5]],
        "retrieval_time_ms": retrieval_time * 1000,
        "metadata_quality": "non-empty" if ("No structural facts" not in metadata.text) else "empty",
        "seeds_found": len(metadata.seed_entities),
        "relationships_found": len(metadata.relationships),
        "classification": classification,
        "semantic_status": retriever.semantic_degradation or "available"
    }

def main():
    """Run all queries and generate report."""
    print("🧪 NATURAL-LANGUAGE QUERY TESTING (NO CODE CHANGES)")
    print("Testing whether RIM can handle vocabulary mismatches\n")

    db, analysis = setup_test_db()
    results = []

    for query in QUERIES:
        result = test_query(db, analysis, query)
        results.append(result)

    # Summary report
    print(f"\n{'='*80}")
    print("📈 SUMMARY REPORT")
    print(f"{'='*80}\n")

    pass_count = sum(1 for r in results if r["classification"] == "PASS")
    partial_count = sum(1 for r in results if r["classification"] == "PARTIAL")
    fail_count = sum(1 for r in results if r["classification"] == "FAIL")

    print(f"Results: {pass_count} PASS, {partial_count} PARTIAL, {fail_count} FAIL")
    print(f"Success Rate: {(pass_count + partial_count) / len(results) * 100:.0f}%\n")

    print("Detailed Results:")
    print("-" * 80)
    for r in results:
        status = "✅" if r["classification"] == "PASS" else "⚠️" if r["classification"] == "PARTIAL" else "❌"
        print(f"{status} {r['query'][:50]:<50} | {r['classification']:<7} | {r['retrieved_count']} entities")

    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)

    # Analyze failures
    failures = [r for r in results if r["classification"] == "FAIL"]
    if failures:
        print(f"\n❌ Failed Queries ({len(failures)}):")
        for r in failures:
            print(f"  - {r['query']}")
            print(f"    Issue: Retrieved {r['retrieved_count']} entities but no metadata built")

    # Semantic status
    semantic_issues = [r for r in results if "artifact_not_found" in r["semantic_status"]]
    if semantic_issues:
        print(f"\n⚠️  Semantic Retrieval: UNAVAILABLE (artifact_not_found)")
        print(f"   Affected: {len(semantic_issues)}/8 queries")
    else:
        print(f"\n✅ Semantic Retrieval: AVAILABLE")

    # Verdict
    print("\n" + "="*80)
    print("PRODUCTION READINESS ASSESSMENT")
    print("="*80)

    print(f"""
1. Is RIM general-purpose for natural-language?
   {('YES - works across vocabulary mismatches' if pass_count >= 6 else 'NO - limited by vocabulary overlap')}

2. Success rate: {(pass_count + partial_count) / len(results) * 100:.0f}%

3. Primary failure mode:
   {'Vocabulary mismatch (lexical BM25 gap)' if fail_count > 0 else 'N/A - all queries work'}

4. Semantic retrieval necessary?
   {'YES - fallback alone insufficient' if fail_count > 2 else 'NO - fallback handles most cases'}

5. Production-ready verdict:
   {'CONDITIONAL - works for code-vocabulary queries only' if fail_count > 2 else 'YES - handles most natural language'}
""")

    db.close()

if __name__ == "__main__":
    main()
