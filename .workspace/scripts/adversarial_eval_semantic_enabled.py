"""
Adversarial evaluation with semantic enabled.

Builds semantic index (like analyzer does) and tests all 24 queries.
Compares BEFORE/AFTER to measure improvement.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models.repository import Repository, Analysis, AnalysisArtifact
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder
from backend.services.rim_metadata import build_rim_metadata_block

QUERIES = [
    ("How does login work?", ["authMiddleware", "authenticateToken", "createSession"], "login vs auth"),
    ("How do users sign in?", ["verifyIdentity", "authenticateToken"], "sign-in vs authenticate"),
    ("What's the flow for user login?", ["authMiddleware"], "flow + login vocabulary gap"),
    ("How is user identity verified?", ["verifyIdentity", "authenticateToken"], "verified vs authenticate"),
    ("How are user credentials checked?", ["verifyIdentity", "authenticateToken"], "credentials vs token"),
    ("What's the overall authentication architecture?", ["authMiddleware", "createSession", "setAuthCookies"], "architecture overview"),
    ("How are security tokens handled?", ["hashToken", "authenticateToken"], "security tokens vs hash"),
    ("What's the middleware stack?", ["authMiddleware"], "middleware as term"),
    ("How does authorization work?", ["checkPermissions"], "authorization vs permissions"),
    ("What happens when a user logs in?", ["createSession", "authenticateToken"], "multi-step process"),
    ("How does the system secure session data?", ["setAuthCookies", "createSession"], "secure data + sessions"),
    ("Where are credentials stored?", ["createSession", "setAuthCookies"], "credentials location"),
    ("Which functions are called during authentication?", ["authMiddleware", "authenticateToken"], "dependency/call chain"),
    ("What functions depend on authentication?", ["checkPermissions"], "dependent functions"),
    ("How do session creation and token handling interact?", ["createSession", "hashToken"], "interaction between"),
    ("How does the system authenticate users?", ["authenticateToken"], "authenticate as direct synonym"),
    ("How is access controlled?", ["checkPermissions"], "access controlled = permissions check"),
    ("How are HTTP requests authenticated?", ["authMiddleware"], "HTTP context"),
    ("What's the mechanism for user validation?", ["verifyIdentity"], "validation vs verification"),
    ("How does session management work?", ["createSession", "clearAuthCookies"], "session management"),
    ("How do users prove who they are?", ["verifyIdentity", "authenticateToken"], "prove identity = verify"),
    ("What prevents unauthorized access?", ["checkPermissions"], "prevent unauthorized = permissions"),
    ("How does the database schema work?", [], "completely unrelated"),
    ("What's the fastest algorithm for sorting?", [], "unrelated computer science"),
]

def create_test_db_with_semantic():
    """Create DB and build semantic index."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(id=1, github_id="test", username="test", email="test@test.com")
    db.add(user)
    repo = Repository(id=1, url="https://github.com/test/deep-guard", user_id=user.id)
    db.add(repo)
    analysis = Analysis(id=100, repository_id=repo.id, status="Completed")
    db.add(analysis)
    db.flush()

    files = {
        "auth.js": FactFile(id=1, analysis_id=analysis.id, path="middleware/auth.js", language="JavaScript"),
        "authcontroller.js": FactFile(id=2, analysis_id=analysis.id, path="controllers/authcontroller.js", language="JavaScript"),
    }
    for f in files.values():
        db.add(f)
    db.flush()

    symbols = {}
    symbols_data = {
        "authMiddleware": ("middleware/auth.js", "Middleware for JWT authentication"),
        "authenticateToken": ("middleware/auth.js", "Validates JWT tokens"),
        "hashToken": ("middleware/auth.js", "Generates secure tokens"),
        "createSession": ("controllers/authcontroller.js", "Creates user session"),
        "verifyIdentity": ("controllers/authcontroller.js", "Verifies user identity"),
        "checkPermissions": ("controllers/authcontroller.js", "Checks user permissions"),
        "setAuthCookies": ("controllers/authcontroller.js", "Sets auth cookies"),
        "clearAuthCookies": ("controllers/authcontroller.js", "Clears auth cookies"),
    }

    for idx, (name, (file_path, doc)) in enumerate(symbols_data.items(), start=1):
        file_id = 1 if "middleware" in file_path else 2
        sym = FactSymbol(
            id=str(idx),
            analysis_id=analysis.id,
            name=name,
            qualified_name=f"auth.{name}",
            symbol_type="function",
            file_id=file_id,
            line_start=10 + (idx * 20),
            line_end=30 + (idx * 20),
            metadata_json={"docstring": doc}
        )
        db.add(sym)
        symbols[name] = sym

    db.flush()

    relationships = [
        (symbols["authMiddleware"], symbols["authenticateToken"], "CALLS", 15),
        (symbols["authMiddleware"], symbols["hashToken"], "CALLS", 18),
        (symbols["createSession"], symbols["hashToken"], "CALLS", 77),
        (symbols["verifyIdentity"], symbols["authenticateToken"], "CALLS", 45),
        (symbols["createSession"], symbols["setAuthCookies"], "CALLS", 80),
    ]

    for idx, (from_sym, to_sym, rel_type, line) in enumerate(relationships, start=1):
        rel = FactRelationship(
            id=f"rel{idx}",
            analysis_id=analysis.id,
            from_symbol_id=from_sym.id,
            to_symbol_id=to_sym.id,
            rel_type=rel_type,
            evidence_line=line
        )
        db.add(rel)

    db.commit()

    # Build semantic index
    class SimpleEntity:
        def __init__(self, sym):
            self.type = type('', (), {'value': 'SYMBOL'})()
            self.name = sym.name
            self.qualified_name = sym.qualified_name
            self.metadata = {"docstring": sym.metadata_json.get("docstring", "")}
            self.location = type('', (), {'repository_path': f"auth.{sym.name}"})()

    entities = {sym.id: SimpleEntity(sym) for sym in symbols.values()}

    try:
        builder = SemanticIndexBuilder()
        chroma_bytes = builder.build_index(entities)
        if chroma_bytes:
            artifact = AnalysisArtifact(
                analysis_id=analysis.id,
                type="semantic_index_db",
                blob_data=chroma_bytes
            )
            db.add(artifact)
            db.commit()
            return db, analysis, True
    except Exception as e:
        pass

    return db, analysis, False

def evaluate_query(db, analysis, query, expected_symbols):
    """Test query and return classification."""
    retriever = HybridRetriever(db, analysis_id=analysis.id)
    results = retriever.retrieve(query, top_k=5, enable_fallback=True)
    metadata = build_rim_metadata_block(db, analysis.id, query, retriever, max_seed_entities=3)

    has_metadata = "No structural facts" not in metadata.text
    relevant = len(results) > 0 and (len(expected_symbols) == 0 or any(r.entity_name in expected_symbols for r in results))

    if relevant and has_metadata:
        return "PASS"
    elif relevant and not expected_symbols:
        return "PASS"
    elif relevant:
        return "PARTIAL"
    else:
        return "FAIL"

def main():
    print("🧪 ADVERSARIAL EVALUATION WITH SEMANTIC ENABLED\n")

    db, analysis, semantic_built = create_test_db_with_semantic()

    if not semantic_built:
        print("❌ Could not build semantic index (chromadb issue)")
        db.close()
        return

    print(f"✅ Semantic index built and loaded\n")

    # Test all 24 queries
    results = []
    for query, expected, reason in QUERIES:
        classification = evaluate_query(db, analysis, query, expected)
        results.append((query, expected, classification, reason))

    db.close()

    # Analyze results
    pass_count = sum(1 for _, _, c, _ in results if c == "PASS")
    partial_count = sum(1 for _, _, c, _ in results if c == "PARTIAL")
    fail_count = sum(1 for _, _, c, _ in results if c == "FAIL")

    print("="*100)
    print("RESULTS: SEMANTIC ENABLED")
    print("="*100)

    for query, expected, classification, reason in results:
        status = "✅" if classification == "PASS" else "⚠️" if classification == "PARTIAL" else "❌"
        print(f"{status} {classification:<8} | {query[:55]:<55} | {reason}")

    print("\n" + "="*100)
    print("SUMMARY")
    print("="*100)

    print(f"\nPASS:    {pass_count:2d}/24 ({pass_count*100/24:.0f}%)")
    print(f"PARTIAL: {partial_count:2d}/24 ({partial_count*100/24:.0f}%)")
    print(f"FAIL:    {fail_count:2d}/24 ({fail_count*100/24:.0f}%)")
    print(f"\nTrue success (PASS only): {pass_count}/24 ({pass_count*100/24:.0f}%)")
    print(f"Overall success (PASS + PARTIAL): {(pass_count+partial_count)}/24 ({(pass_count+partial_count)*100/24:.0f}%)")

    # Compare with expected semantic improvements
    print("\n" + "="*100)
    print("COMPARISON WITH PREVIOUS RESULTS (No Semantic)")
    print("="*100)

    print(f"\nWithout semantic: PASS=17, PARTIAL=3, FAIL=4 (71% true success)")
    print(f"With semantic:    PASS={pass_count}, PARTIAL={partial_count}, FAIL={fail_count} ({pass_count*100/24:.0f}% true success)")
    print(f"Improvement:      +{pass_count-17} PASS queries ({(pass_count-17)*100/24:+.0f}%)")

    # Check specific vocabulary-gap queries
    print("\n" + "="*100)
    print("VOCABULARY-GAP QUERIES (Expected to improve with semantic)")
    print("="*100)

    vocab_gap_queries = [
        "How does login work?",
        "Where are credentials stored?",
        "What prevents unauthorized access?",
    ]

    for query in vocab_gap_queries:
        for q, exp, classification, reason in results:
            if q == query:
                status = "✅" if classification == "PASS" else "⚠️" if classification == "PARTIAL" else "❌"
                print(f"\n{status} {query}")
                print(f"   Result: {classification}")
                print(f"   Reason: {reason}")

    # Final verdict
    print("\n" + "="*100)
    print("PRODUCTION READINESS VERDICT")
    print("="*100)

    if pass_count >= 20:
        print(f"\n🟢 GO - {pass_count}/24 PASS ({pass_count*100/24:.0f}% success)")
        print(f"   Semantic retrieval significantly improves results")
    elif pass_count >= 17:
        print(f"\n🟡 CONDITIONAL GO - {pass_count}/24 PASS ({pass_count*100/24:.0f}% success)")
        print(f"   Semantic provides modest improvement but still has gaps")
    else:
        print(f"\n🔴 NO-GO - {pass_count}/24 PASS ({pass_count*100/24:.0f}% success)")

if __name__ == "__main__":
    main()
