"""
Detailed trace of graph expansion to validate forward/reverse traversal and multi-hop behavior.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.database import Base
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship
from backend.intelligence.retrieval.bounded_graph_expander import BoundedGraphExpander

def setup_test_repo():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Create user and repo
    user = User(id=1, github_id="test", username="test", email="test@test.com")
    session.add(user)
    session.flush()

    repo = Repository(id=1, url="https://github.com/test/repo", user_id=user.id)
    session.add(repo)
    session.flush()

    # Create analysis
    analysis = Analysis(id=100, repository_id=repo.id, status="Completed")
    session.add(analysis)
    session.commit()

    return session, analysis.id


def setup_test_facts(session, analysis_id):
    """Create test fact store with realistic relationships."""
    # Create files
    file1 = FactFile(id="f1", analysis_id=analysis_id, path="auth.py", language="Python")
    file2 = FactFile(id="f2", analysis_id=analysis_id, path="handlers.py", language="Python")
    file3 = FactFile(id="f3", analysis_id=analysis_id, path="utils.py", language="Python")
    session.add_all([file1, file2, file3])
    session.flush()

    # Create symbols (functions)
    authenticate = FactSymbol(
        id="sym:urn:python:auth.py#authenticate",
        analysis_id=analysis_id, file_id="f1", name="authenticate",
        qualified_name="auth.authenticate", symbol_type="function",
        line_start=10, line_end=30
    )

    login = FactSymbol(
        id="sym:urn:python:handlers.py#login_handler",
        analysis_id=analysis_id, file_id="f2", name="login_handler",
        qualified_name="handlers.login_handler", symbol_type="function",
        line_start=15, line_end=45
    )

    hash_pw = FactSymbol(
        id="sym:urn:python:utils.py#hash_password",
        analysis_id=analysis_id, file_id="f3", name="hash_password",
        qualified_name="utils.hash_password", symbol_type="function",
        line_start=5, line_end=20
    )

    verify_pw = FactSymbol(
        id="sym:urn:python:utils.py#verify_password",
        analysis_id=analysis_id, file_id="f3", name="verify_password",
        qualified_name="utils.verify_password", symbol_type="function",
        line_start=25, line_end=40
    )

    session.add_all([authenticate, login, hash_pw, verify_pw])
    session.flush()

    # Create relationships (directed edges)
    # login_handler CALLS authenticate (depth 1 forward)
    r1 = FactRelationship(
        id="r1", analysis_id=analysis_id,
        from_symbol_id=login.id, to_symbol_id=authenticate.id,
        rel_type="CALLS", evidence_line=20
    )

    # authenticate CALLS hash_password (depth 2 forward)
    r2 = FactRelationship(
        id="r2", analysis_id=analysis_id,
        from_symbol_id=authenticate.id, to_symbol_id=hash_pw.id,
        rel_type="CALLS", evidence_line=15
    )

    # authenticate CALLS verify_password (depth 2 forward)
    r3 = FactRelationship(
        id="r3", analysis_id=analysis_id,
        from_symbol_id=authenticate.id, to_symbol_id=verify_pw.id,
        rel_type="CALLS", evidence_line=18
    )

    session.add_all([r1, r2, r3])
    session.commit()

    return {
        "files": {"f1": file1, "f2": file2, "f3": file3},
        "symbols": {
            "authenticate": authenticate,
            "login": login,
            "hash_pw": hash_pw,
            "verify_pw": verify_pw,
        },
        "relationships": [r1, r2, r3],
    }


def trace_forward_expansion():
    """Test 1: Forward expansion from authenticate function."""
    print("\n" + "="*80)
    print("TEST 1: FORWARD EXPANSION from authenticate")
    print("="*80)

    session, analysis_id = setup_test_repo()
    facts = setup_test_facts(session, analysis_id)

    expander = BoundedGraphExpander(
        session, analysis_id, max_depth=2, max_nodes_per_hop=3, max_total_nodes=30
    )

    # Start from authenticate
    candidates = [{
        "id": "authenticate_1",
        "name": "authenticate",
        "file_path": "auth.py",
        "symbol_id": facts["symbols"]["authenticate"].id,
        "type": "function",
    }]

    result = expander.expand_candidates(candidates)

    print(f"\nAnchor: {candidates[0]['name']}")
    print(f"Total results: {len(result)}")
    print("\nResults by type:")
    for r in result:
        is_anchor = r.get("is_anchor", False)
        src = r.get("expansion_source", "unknown")
        role = r.get("relationship_role", "")
        rel_type = r.get("rel_type", "")
        dist = r.get("distance_from_anchor", -1)
        print(f"  {'[ANCHOR]' if is_anchor else '        '} {r['name']:20} | type={r['type']:10} | "
              f"role={role:15} | rel={rel_type:10} | distance={dist} | source={src}")

    # Validate expectations
    expanded = [r for r in result if r.get("expansion_source", "").startswith("expanded_from")]
    callees = [n for n in expanded if n.get("relationship_role") == "callee"]
    callee_names = [n.get("name") for n in callees]

    print(f"\nCallees found: {callee_names}")
    print(f"Expected: ['hash_password', 'verify_password'] (or subset)")
    assert "hash_password" in callee_names, "hash_password not found as callee!"
    assert "verify_password" in callee_names, "verify_password not found as callee!"
    print("✓ FORWARD EXPANSION WORKS")


def trace_reverse_expansion():
    """Test 2: Reverse expansion (who calls hash_password)."""
    print("\n" + "="*80)
    print("TEST 2: REVERSE EXPANSION - who calls hash_password")
    print("="*80)

    session, analysis_id = setup_test_repo()
    facts = setup_test_facts(session, analysis_id)

    expander = BoundedGraphExpander(
        session, analysis_id, max_depth=2, max_nodes_per_hop=3, max_total_nodes=30
    )

    # Start from hash_password
    candidates = [{
        "id": "hash_pw_1",
        "name": "hash_password",
        "file_path": "utils.py",
        "symbol_id": facts["symbols"]["hash_pw"].id,
        "type": "function",
    }]

    result = expander.expand_candidates(candidates)

    print(f"\nAnchor: {candidates[0]['name']}")
    print(f"Total results: {len(result)}")
    print("\nResults by type:")
    for r in result:
        is_anchor = r.get("is_anchor", False)
        src = r.get("expansion_source", "unknown")
        role = r.get("relationship_role", "")
        rel_type = r.get("rel_type", "")
        dist = r.get("distance_from_anchor", -1)
        print(f"  {'[ANCHOR]' if is_anchor else '        '} {r['name']:20} | type={r['type']:10} | "
              f"role={role:15} | rel={rel_type:10} | distance={dist} | source={src}")

    # Validate expectations
    expanded = [r for r in result if r.get("expansion_source", "").startswith("expanded_from")]
    callers = [n for n in expanded if n.get("relationship_role") == "caller"]
    caller_names = [n.get("name") for n in callers]

    print(f"\nCallers found: {caller_names}")
    print(f"Expected: ['authenticate'] (depth 1) or ['authenticate', 'login_handler'] (depth 2)")
    assert len(callers) > 0, f"No callers found! Expanded nodes: {[(n.get('name'), n.get('relationship_role')) for n in expanded]}"
    print("✓ REVERSE EXPANSION WORKS")


def trace_multihop_expansion():
    """Test 3: Multi-hop expansion from login_handler."""
    print("\n" + "="*80)
    print("TEST 3: MULTI-HOP EXPANSION from login_handler")
    print("="*80)

    session, analysis_id = setup_test_repo()
    facts = setup_test_facts(session, analysis_id)

    expander = BoundedGraphExpander(
        session, analysis_id, max_depth=2, max_nodes_per_hop=3, max_total_nodes=30
    )

    # Start from login_handler
    candidates = [{
        "id": "login_1",
        "name": "login_handler",
        "file_path": "handlers.py",
        "symbol_id": facts["symbols"]["login"].id,
        "type": "function",
    }]

    result = expander.expand_candidates(candidates)

    print(f"\nAnchor: {candidates[0]['name']}")
    print(f"Total results: {len(result)}")
    print("\nExpansion tree:")

    # Group by distance
    by_distance = {}
    for r in result:
        dist = r.get("distance_from_anchor", -1)
        if dist not in by_distance:
            by_distance[dist] = []
        by_distance[dist].append(r)

    for dist in sorted(by_distance.keys()):
        if dist == 0:
            print(f"\nDepth {dist} (Anchor):")
        else:
            print(f"\nDepth {dist}:")
        for r in by_distance[dist]:
            role = r.get("relationship_role", "")
            rel_type = r.get("rel_type", "")
            print(f"  - {r['name']:20} | role={role:15} | rel={rel_type:10}")

    # Validate multi-hop: should reach hash_password at depth 2
    depth_2_nodes = by_distance.get(2, [])
    depth_2_names = [n.get("name") for n in depth_2_nodes]

    print(f"\nDepth 2 nodes found: {depth_2_names}")
    print(f"Expected: ['hash_password', 'verify_password'] via authenticate")
    if "hash_password" in depth_2_names or "verify_password" in depth_2_names:
        print("✓ MULTI-HOP EXPANSION WORKS")
    else:
        print("! Multi-hop may be limited - check depth limit and max_nodes")


def trace_deduplication():
    """Test 4: Deduplication when node is reachable via multiple paths."""
    print("\n" + "="*80)
    print("TEST 4: DEDUPLICATION")
    print("="*80)

    session, analysis_id = setup_test_repo()
    facts = setup_test_facts(session, analysis_id)

    expander = BoundedGraphExpander(
        session, analysis_id, max_depth=2, max_nodes_per_hop=3, max_total_nodes=30
    )

    # hash_password can be reached via authenticate (and potentially others)
    candidates = [{
        "id": "hash_pw_1",
        "name": "hash_password",
        "file_path": "utils.py",
        "symbol_id": facts["symbols"]["hash_pw"].id,
        "type": "function",
    }]

    result = expander.expand_candidates(candidates)

    # Check for duplicates
    symbol_ids = [r.get("symbol_id") for r in result]
    unique_ids = set(symbol_ids)

    print(f"\nTotal results: {len(result)}")
    print(f"Unique symbol_ids: {len(unique_ids)}")
    print(f"Results:")
    for r in result:
        print(f"  - {r['name']:20} | id={r['symbol_id']}")

    if len(symbol_ids) == len(unique_ids):
        print("\n✓ NO DUPLICATES - Deduplication works correctly")
    else:
        duplicates = [(s, symbol_ids.count(s)) for s in unique_ids if symbol_ids.count(s) > 1]
        print(f"\n✗ DUPLICATES FOUND: {duplicates}")


def trace_both_directions():
    """Test 5: Both forward and reverse in same query."""
    print("\n" + "="*80)
    print("TEST 5: BOTH DIRECTIONS in same query from authenticate")
    print("="*80)

    session, analysis_id = setup_test_repo()
    facts = setup_test_facts(session, analysis_id)

    expander = BoundedGraphExpander(
        session, analysis_id, max_depth=1, max_nodes_per_hop=3, max_total_nodes=30
    )

    # Start from authenticate (has both incoming and outgoing edges)
    candidates = [{
        "id": "auth_1",
        "name": "authenticate",
        "file_path": "auth.py",
        "symbol_id": facts["symbols"]["authenticate"].id,
        "type": "function",
    }]

    result = expander.expand_candidates(candidates)

    print(f"\nAnchor: {candidates[0]['name']}")
    print(f"Total results: {len(result)}")
    print("\nResults:")
    for r in result:
        is_anchor = r.get("is_anchor", False)
        role = r.get("relationship_role", "")
        rel_type = r.get("rel_type", "")
        print(f"  {'[ANCHOR]' if is_anchor else '        '} {r['name']:20} | role={role:15} | rel={rel_type:10}")

    # Check for both directions
    expanded = [r for r in result if r.get("expansion_source", "").startswith("expanded_from")]
    callees = [n for n in expanded if n.get("relationship_role") == "callee"]
    callers = [n for n in expanded if n.get("relationship_role") == "caller"]

    print(f"\nCallees (outgoing): {[n.get('name') for n in callees]}")
    print(f"Callers (incoming): {[n.get('name') for n in callers]}")

    if len(callees) > 0 and len(callers) > 0:
        print("\n✓ BOTH DIRECTIONS PRESERVED")
    elif len(callees) > 0:
        print("\n! Only forward direction found (no reverse)")
    elif len(callers) > 0:
        print("\n! Only reverse direction found (no forward)")
    else:
        print("\n✗ Neither direction found!")


if __name__ == "__main__":
    trace_forward_expansion()
    trace_reverse_expansion()
    trace_multihop_expansion()
    trace_deduplication()
    trace_both_directions()

    print("\n" + "="*80)
    print("ALL VALIDATION TESTS COMPLETED")
    print("="*80)
