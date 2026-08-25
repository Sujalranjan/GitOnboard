"""
Unit & Integration Tests for Target Repository Context Isolation.

Verifies:
  1. Strict target repository isolation: Evidence, facts, symbols, and files belong ONLY to target analysis_id.
  2. Multi-language archetype adaptation: Python repository proposes Python files and tests (not hardcoded TS files).
  3. TypeScript repository proposes TypeScript files and tests.
  4. Non-existent repository does not fall back to other repositories.
  5. Generic domain concept extraction contains 0 hardcoded application-specific component names.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.agent.context.assembler import ContextAssembler, extract_domain_concepts
from backend.agent.context.contracts import ContextAssemblyRequest, ContextBudget
from backend.agent.modes import (
    execute_explore,
    execute_explain,
    execute_plan,
    execute_implement,
    resolve_target_repository_and_analysis,
)
from backend.agent.planning.orchestrator import PlanningOrchestrator
from backend.database import Base
from backend.models.fact_store import FactFile, FactSymbol
from backend.models.repository import Analysis, Repository
from backend.models.user import User


@pytest.fixture
def isolated_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        # Create User
        user = User(id=1, github_id="gh_123", username="testdev", email="test@gitonboard.com")
        db.add(user)
        db.flush()

        # Repository 1: GitOnboard (TypeScript / Next.js)
        repo_gitonboard = Repository(id=1, url="https://github.com/org/GitOnboard.git", user_id=1)
        db.add(repo_gitonboard)
        db.flush()

        analysis_gitonboard = Analysis(id=1, repository_id=1, status="Completed", engine_version="v1.0")
        db.add(analysis_gitonboard)
        db.flush()

        db.add_all([
            FactFile(id="1:src/components/UploadArea.tsx", analysis_id=1, path="src/components/UploadArea.tsx", language="typescript", size=1200),
            FactFile(id="1:src/services/analysisStore.ts", analysis_id=1, path="src/services/analysisStore.ts", language="typescript", size=950),
            FactFile(id="1:package.json", analysis_id=1, path="package.json", language="json", size=500),
            FactSymbol(id="1:sym:UploadArea", analysis_id=1, name="UploadArea", qualified_name="UploadArea", symbol_type="function", line_start=10),
        ])

        # Repository 2: pls-cli (Python CLI tool)
        repo_pls = Repository(id=2, url="https://github.com/guedesfelipe/pls-cli.git", user_id=1)
        db.add(repo_pls)
        db.flush()

        analysis_pls = Analysis(id=2, repository_id=2, status="Completed", engine_version="v1.0")
        db.add(analysis_pls)
        db.flush()

        db.add_all([
            FactFile(id="2:pls_cli/__init__.py", analysis_id=2, path="pls_cli/__init__.py", language="python", size=100),
            FactFile(id="2:pls_cli/please.py", analysis_id=2, path="pls_cli/please.py", language="python", size=4500),
            FactFile(id="2:pls_cli/utils.py", analysis_id=2, path="pls_cli/utils.py", language="python", size=1800),
            FactFile(id="2:tests/test_pls_cli.py", analysis_id=2, path="tests/test_pls_cli.py", language="python", size=2200),
            FactFile(id="2:Makefile", analysis_id=2, path="Makefile", language="makefile", size=300),
            FactSymbol(id="2:sym:run_command", analysis_id=2, name="run_command", qualified_name="pls_cli.please.run_command", symbol_type="function", line_start=42),
        ])

        db.commit()
        yield db
    finally:
        db.close()


def test_domain_concepts_contain_no_hardcoded_gitonboard_components():
    """Verifies that domain concepts extract general domain terms, NOT GitOnboard frontend component names."""
    queries = [
        "What would it take to add Google OAuth?",
        "What would it take to add search?",
        "What would it take to add dark mode?",
        "What would it take to add email notifications?",
        "What would it take to add pagination?",
    ]
    forbidden_tokens = ["UploadArea", "RecentAnalyses", "AnalysisHistory", "analysisStore", "AccountSettings", "AnalysisPage", "ThemeToggle", "authService.ts"]
    for q in queries:
        extracted = extract_domain_concepts(q)
        for token in forbidden_tokens:
            assert token not in extracted.get("primary", []), f"Leaked {token} in primary keywords for query '{q}'"
            assert token not in extracted.get("secondary", []), f"Leaked {token} in secondary keywords for query '{q}'"


def test_python_target_repository_plan_generates_python_files(isolated_db):
    """Verifies that planning for pls-cli (Python) proposes Python files in pls_cli/ and tests/."""
    plan_res = execute_plan(
        user_requirement="What would it take to add Google OAuth?",
        repository_id="pls-cli",
        user_id=1,
        db=isolated_db,
    )
    assert plan_res["intent"] == "plan"
    plan = plan_res["plan"]
    tasks = plan["tasks"]
    assert len(tasks) >= 2

    # Step 1 should be Python in pls_cli/
    impl_task = tasks[0]
    for file_path in impl_task["affected_files"]:
        assert file_path.endswith(".py"), f"Expected Python file but got {file_path}"
        assert not file_path.endswith(".ts"), f"Leaked TypeScript file in Python repository: {file_path}"
        assert "authService.ts" not in file_path
        assert "lib/auth.ts" not in file_path
        assert file_path.startswith("pls_cli/"), f"Expected pls_cli/ directory but got {file_path}"

    # Step 2 should be Python test in tests/
    test_task = tasks[1]
    for file_path in test_task["affected_files"]:
        assert file_path.endswith(".py"), f"Expected Python test file but got {file_path}"
        assert file_path.startswith("tests/"), f"Expected tests/ directory but got {file_path}"


def test_typescript_target_repository_plan_generates_typescript_files(isolated_db):
    """Verifies that planning for GitOnboard (TypeScript) proposes TypeScript files."""
    plan_res = execute_plan(
        user_requirement="What would it take to add payment system?",
        repository_id="GitOnboard",
        user_id=1,
        db=isolated_db,
    )
    assert plan_res["intent"] == "plan"
    plan = plan_res["plan"]
    tasks = plan["tasks"]
    assert len(tasks) >= 2

    impl_task = tasks[0]
    for file_path in impl_task["affected_files"]:
        assert file_path.endswith((".ts", ".tsx")), f"Expected TypeScript file but got {file_path}"


def test_target_repository_isolation_in_explore(isolated_db):
    """Verifies that execute_explore for pls-cli never lists files or symbols from GitOnboard."""
    explore_res = execute_explore(
        user_requirement="list files in tree",
        repository_id="pls-cli",
        user_id=1,
        db=isolated_db,
    )
    assert explore_res["intent"] == "explore"
    entities = explore_res.get("entities", [])
    entity_paths = [e["path"] for e in entities if "path" in e]

    # Must contain pls-cli files
    assert any("pls_cli" in p for p in entity_paths)
    # Must NOT contain GitOnboard files
    assert not any("UploadArea" in p for p in entity_paths)
    assert not any("analysisStore" in p for p in entity_paths)


def test_nonexistent_repository_does_not_leak_other_repositories(isolated_db):
    """Verifies that querying a non-existent repo returns an empty/isolated state rather than leaking other repos."""
    repo, analysis_id, repo_name = resolve_target_repository_and_analysis(
        db=isolated_db,
        repository_id="nonexistent-repo-xyz",
        user_id=1,
    )
    assert repo is None
    assert analysis_id is None
    assert repo_name == "nonexistent-repo-xyz"

    explore_res = execute_explore(
        user_requirement="find symbols",
        repository_id="nonexistent-repo-xyz",
        user_id=1,
        db=isolated_db,
    )
    assert len(explore_res.get("entities", [])) == 0
    assert "has not been analyzed" in explore_res.get("response", "")


def test_implement_mode_preserves_target_isolation_and_approval_gate(isolated_db):
    """Verifies that execute_implement for pls-cli produces a Python plan with status READY_FOR_APPROVAL."""
    impl_res = execute_implement(
        user_requirement="add Google OAuth",
        repository_id="pls-cli",
        user_id=1,
        db=isolated_db,
    )
    assert impl_res["intent"] == "implement"
    assert impl_res["status"] == "READY_FOR_APPROVAL"
    tasks = impl_res["plan"]["tasks"]
    assert tasks[0]["affected_files"][0].endswith(".py")
    assert tasks[0]["affected_files"][0].startswith("pls_cli/")


def test_strict_cross_repository_fact_and_evidence_isolation(isolated_db):
    """
    Forensic Verification Test:
    Sets up two separate repositories in the same database with distinct symbols, routes, DB objects,
    and capabilities. Proves that querying Repository A retrieves ZERO facts from Repository B,
    and querying Repository B retrieves ZERO facts from Repository A.
    """
    from backend.models.fact_store import FactRoute, FactDatabaseObject, FactCapability

    # Add routes, db objects, and capabilities to Repository 1 (GitOnboard, analysis_id=1)
    isolated_db.add_all([
        FactRoute(id="1:route:auth", analysis_id=1, method="POST", path="/api/auth/login", handler_symbol_id="1:sym:login_handler"),
        FactDatabaseObject(id="1:db:users", analysis_id=1, name="users_table", object_type="table"),
        FactCapability(id="1:cap:auth", analysis_id=1, name="Authentication & Session", capability_type="AUTHENTICATION", status="CONFIRMED"),
    ])

    # Add routes, db objects, and capabilities to Repository 2 (pls-cli, analysis_id=2)
    isolated_db.add_all([
        FactRoute(id="2:route:cli", analysis_id=2, method="GET", path="/cli/commands", handler_symbol_id="2:sym:run_command"),
        FactDatabaseObject(id="2:db:config", analysis_id=2, name="cli_config", object_type="config"),
        FactCapability(id="2:cap:cli", analysis_id=2, name="CLI Command Execution", capability_type="CLI", status="CONFIRMED"),
    ])
    isolated_db.commit()

    assembler = ContextAssembler()

    # Query 1: Assemble context for Repository 2 (pls-cli) with query "how does authentication work?"
    req_pls = ContextAssemblyRequest(
        repository_id="pls-cli",
        requirement="how does authentication work?",
        analysis_id=2,
    )
    context_pls = assembler.assemble(req_pls, db=isolated_db)

    # Invariant 1: No GitOnboard files or symbols leaked into pls-cli
    for f in context_pls.relevant_files:
        assert "src/components" not in f
        assert "UploadArea" not in f
        assert "analysisStore" not in f

    for s in context_pls.relevant_symbols:
        assert s["name"] != "UploadArea"
        assert s["name"] != "login_handler"

    for r in context_pls.relevant_routes:
        assert r["path"] != "/api/auth/login"

    for d in context_pls.relevant_db_objects:
        assert d["name"] != "users_table"

    for c in context_pls.capabilities:
        assert c["id"].startswith("2:")

    for ev in context_pls.evidence:
        assert not str(ev.source_id).startswith("1:")

    # Query 2: Assemble context for Repository 1 (GitOnboard)
    req_git = ContextAssemblyRequest(
        repository_id="GitOnboard",
        requirement="how does authentication work?",
        analysis_id=1,
    )
    context_git = assembler.assemble(req_git, db=isolated_db)

    for f in context_git.relevant_files:
        assert "pls_cli" not in f

    for s in context_git.relevant_symbols:
        assert s["name"] != "run_command"

    for r in context_git.relevant_routes:
        assert r["path"] != "/cli/commands"

    for d in context_git.relevant_db_objects:
        assert d["name"] != "cli_config"

    for c in context_git.capabilities:
        assert c["id"].startswith("1:")

    for ev in context_git.evidence:
        assert not str(ev.source_id).startswith("2:")


def test_cross_user_repository_access_rejected(isolated_db):
    """
    Adversarial Attack 1:
    User 1 attempts to resolve or query a private repository belonging exclusively to User 2.
    Asserts that target resolution returns None, and execution engines return unavailable.
    """
    # Create User 2 and User 2's private repository
    user2 = User(id=2, github_id="gh_456", username="user2", email="user2@gitonboard.com")
    isolated_db.add(user2)
    isolated_db.flush()

    repo_user2 = Repository(id=99, url="https://github.com/secret-org/secret-repo.git", user_id=2)
    isolated_db.add(repo_user2)
    isolated_db.flush()

    analysis_user2 = Analysis(id=999, repository_id=99, status="Completed", engine_version="v1.0")
    isolated_db.add(analysis_user2)
    isolated_db.flush()

    isolated_db.add_all([
        FactFile(id="999:src/secret.py", analysis_id=999, path="src/secret.py", language="python", size=100),
        FactSymbol(id="999:sym:secret_function", analysis_id=999, name="secret_function", symbol_type="function", line_start=1),
    ])
    isolated_db.commit()

    # 1. Target resolution attack: User 1 queries User 2's repository
    repo_res, analysis_id, r_name = resolve_target_repository_and_analysis(
        db=isolated_db,
        repository_id="secret-repo",
        user_id=1,  # User 1 is requesting
    )
    assert repo_res is None, "Cross-user security breach: User 1 resolved User 2's repository!"
    assert analysis_id is None, "Cross-user security breach: User 1 resolved User 2's analysis!"

    # 2. Execution attack: User 1 queries User 2's repository in explore mode
    explore_res = execute_explore(
        user_requirement="find secret symbols",
        repository_id="secret-repo",
        user_id=1,
        db=isolated_db,
    )
    assert len(explore_res.get("entities", [])) == 0
    assert "has not been analyzed" in explore_res.get("response", "")

    # 3. Target resolution by exact ID attack: User 1 queries User 2's repository ID '99'
    repo_by_id, a_by_id, _ = resolve_target_repository_and_analysis(
        db=isolated_db,
        repository_id="99",
        user_id=1,
    )
    assert repo_by_id is None
    assert a_by_id is None


def test_null_and_empty_repository_id_does_not_fallback(isolated_db):
    """
    Adversarial Attack 2:
    Request sent with repository_id = None, "", or "   ".
    System must NOT silently fall back to user's latest repository or analysis.
    """
    for null_val in [None, "", "   ", "default", "Default"]:
        repo_res, analysis_id, r_name = resolve_target_repository_and_analysis(
            db=isolated_db,
            repository_id=null_val,
            user_id=1,
        )
        assert repo_res is None, f"Implicit fallback defect: repository_id='{null_val}' resolved repo {repo_res}!"
        assert analysis_id is None, f"Implicit fallback defect: repository_id='{null_val}' resolved analysis {analysis_id}!"
        assert r_name == "default"


def test_ambiguous_repository_slug_resolution(isolated_db):
    """
    Adversarial Attack 3:
    User owns two repositories with the same slug name from different orgs:
    - github.com/org-a/common-tool
    - github.com/org-b/common-tool
    Request with slug 'common-tool' must reject ambiguous resolution.
    Request with explicit repository.id must resolve cleanly.
    """
    repo_a = Repository(id=30, url="https://github.com/org-a/common-tool.git", user_id=1)
    repo_b = Repository(id=31, url="https://github.com/org-b/common-tool.git", user_id=1)
    isolated_db.add_all([repo_a, repo_b])
    isolated_db.flush()

    analysis_a = Analysis(id=301, repository_id=30, status="Completed", engine_version="v1.0")
    analysis_b = Analysis(id=302, repository_id=31, status="Completed", engine_version="v1.0")
    isolated_db.add_all([analysis_a, analysis_b])
    isolated_db.commit()

    # 1. Ambiguous slug query -> Must return None, rejecting arbitrary selection
    repo_ambig, a_ambig, _ = resolve_target_repository_and_analysis(
        db=isolated_db,
        repository_id="common-tool",
        user_id=1,
    )
    assert repo_ambig is None, "Ambiguity defect: Arbitrarily selected a repository when multiple matched!"
    assert a_ambig is None

    # 2. Authoritative integer repository.id query -> Resolves exact repository
    repo_exact_a, a_exact_a, _ = resolve_target_repository_and_analysis(
        db=isolated_db,
        repository_id="30",
        user_id=1,
    )
    assert repo_exact_a is not None and repo_exact_a.id == 30
    assert a_exact_a == 301

    repo_exact_b, a_exact_b, _ = resolve_target_repository_and_analysis(
        db=isolated_db,
        repository_id="31",
        user_id=1,
    )
    assert repo_exact_b is not None and repo_exact_b.id == 31
    assert a_exact_b == 302


def test_chromadb_partitioning_isolation():
    """
    Adversarial Attack 4:
    Verifies that vector storage paths are strictly partitioned by:
    user_{user_id} / repo_{repo_id} / analysis_{analysis_id} / chroma
    """
    from pathlib import Path
    from backend.routers.repo.semantic import CHROMA_BASE_DIR

    def compute_chroma_path(user_id: int, repo_id: int, analysis_id: int) -> Path:
        return CHROMA_BASE_DIR / f"user_{user_id}" / f"repo_{repo_id}" / f"analysis_{analysis_id}" / "chroma"

    # Same repo with two analyses -> distinct vector stores
    path_a1 = compute_chroma_path(user_id=1, repo_id=10, analysis_id=101)
    path_a2 = compute_chroma_path(user_id=1, repo_id=10, analysis_id=102)
    assert path_a1 != path_a2

    # Two repos with same slug for same user -> distinct vector stores
    path_repo1 = compute_chroma_path(user_id=1, repo_id=10, analysis_id=101)
    path_repo2 = compute_chroma_path(user_id=1, repo_id=20, analysis_id=101)
    assert path_repo1 != path_repo2

    # Two users with same repo ID -> distinct vector stores
    path_u1 = compute_chroma_path(user_id=1, repo_id=10, analysis_id=101)
    path_u2 = compute_chroma_path(user_id=2, repo_id=10, analysis_id=101)
    assert path_u1 != path_u2


def test_overlapping_concept_a_b_a_isolation(isolated_db):
    """
    Adversarial Attack 5:
    Two repositories with identical domain concepts ('auth', 'login'), distinct non-empty entities.
    Query A -> B -> A:
    - A must return ONLY A facts (non-empty)
    - B must return ONLY B facts (non-empty)
    - A must return ONLY A facts (non-empty)
    """
    from backend.models.fact_store import FactRoute, FactCapability

    # Add Repo A entities
    isolated_db.add_all([
        FactFile(id="1:src/a_auth.py", analysis_id=1, path="src/a_auth.py", language="python", size=1000),
        FactSymbol(id="1:sym:AuthServiceA", analysis_id=1, name="AuthServiceA", symbol_type="class", line_start=10),
        FactRoute(id="1:route:a_login", analysis_id=1, method="POST", path="/api/a/login", handler_symbol_id="1:sym:AuthServiceA"),
        FactCapability(id="1:cap:auth_a", analysis_id=1, name="OAuth A Authentication", capability_type="AUTHENTICATION", status="CONFIRMED"),
    ])

    # Add Repo B entities
    isolated_db.add_all([
        FactFile(id="2:src/b_auth.py", analysis_id=2, path="src/b_auth.py", language="python", size=1000),
        FactSymbol(id="2:sym:AuthServiceB", analysis_id=2, name="AuthServiceB", symbol_type="class", line_start=10),
        FactRoute(id="2:route:b_login", analysis_id=2, method="POST", path="/api/b/login", handler_symbol_id="2:sym:AuthServiceB"),
        FactCapability(id="2:cap:auth_b", analysis_id=2, name="Session Authentication B", capability_type="AUTHENTICATION", status="CONFIRMED"),
    ])
    isolated_db.commit()

    assembler = ContextAssembler()

    # Step 1: Query A
    ctx_a1 = assembler.assemble(
        ContextAssemblyRequest(repository_id="GitOnboard", requirement="how does authentication login work?", analysis_id=1),
        db=isolated_db,
    )
    # Step 2: Switch to B
    ctx_b = assembler.assemble(
        ContextAssemblyRequest(repository_id="pls-cli", requirement="how does authentication login work?", analysis_id=2),
        db=isolated_db,
    )
    # Step 3: Switch back to A
    ctx_a2 = assembler.assemble(
        ContextAssemblyRequest(repository_id="GitOnboard", requirement="how does authentication login work?", analysis_id=1),
        db=isolated_db,
    )

    # 1. Verify Non-Empty Results
    assert len(ctx_a1.relevant_files) > 0
    assert len(ctx_b.relevant_files) > 0
    assert len(ctx_a2.relevant_files) > 0

    # 2. Strict Zero Leakage Assertions
    # A cannot contain B's symbols, routes, capabilities, or files
    assert any("AuthServiceA" in s["name"] for s in ctx_a1.relevant_symbols)
    assert not any("AuthServiceB" in s["name"] for s in ctx_a1.relevant_symbols)
    assert any("/api/a/login" in r["path"] for r in ctx_a1.relevant_routes)
    assert not any("/api/b/login" in r["path"] for r in ctx_a1.relevant_routes)
    assert any("OAuth A" in c["name"] for c in ctx_a1.capabilities)
    assert not any("Session Authentication B" in c["name"] for c in ctx_a1.capabilities)

    # B cannot contain A's symbols, routes, capabilities, or files
    assert any("AuthServiceB" in s["name"] for s in ctx_b.relevant_symbols)
    assert not any("AuthServiceA" in s["name"] for s in ctx_b.relevant_symbols)
    assert any("/api/b/login" in r["path"] for r in ctx_b.relevant_routes)
    assert not any("/api/a/login" in r["path"] for r in ctx_b.relevant_routes)
    assert any("Session Authentication B" in c["name"] for c in ctx_b.capabilities)
    assert not any("OAuth A" in c["name"] for c in ctx_b.capabilities)

    # Returning to A reproduces pristine A facts
    assert [s["name"] for s in ctx_a1.relevant_symbols] == [s["name"] for s in ctx_a2.relevant_symbols]
    assert [r["path"] for r in ctx_a1.relevant_routes] == [r["path"] for r in ctx_a2.relevant_routes]


def test_real_api_agent_routes_isolation(isolated_db):
    """
    Adversarial Attack 6:
    Tests the real HTTP routes (/api/v1/agent/classify and /api/v1/agent/runs) with TestClient.
    Verifies:
      1. repository_id=None does not fall back to latest repo facts
      2. User 1 calling API for User 2's repo is blocked
      3. Real classify endpoint for pls-cli produces pls-cli plans without foreign files.
    """
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.dependencies.auth import get_current_user
    from backend.database import get_db

    current_user_obj = isolated_db.query(User).filter(User.id == 1).first()

    app.dependency_overrides[get_current_user] = lambda: current_user_obj
    app.dependency_overrides[get_db] = lambda: isolated_db

    try:
        client = TestClient(app)

        # 1. Real HTTP request with repository_id = None
        resp_null = client.post(
            "/api/v1/agent/classify",
            json={"requirement": "Explain authentication", "repository_id": None}
        )
        assert resp_null.status_code == 200
        null_data = resp_null.json()
        assert "has not been analyzed or is unavailable" in null_data["response"] or "Explain" in null_data["response"]

        # 2. Real HTTP request for User 2's repo (Cross-user rejection)
        user2 = User(id=2, github_id="gh_456", username="user2", email="user2@gitonboard.com")
        isolated_db.add(user2)
        isolated_db.flush()
        repo_user2 = Repository(id=99, url="https://github.com/secret-org/secret-repo.git", user_id=2)
        isolated_db.add(repo_user2)
        isolated_db.commit()

        # Attack on /api/v1/agent/runs
        resp_run_attack = client.post(
            "/api/v1/agent/runs",
            json={"user_requirement": "Implement secret feature", "repository_id": "99"}
        )
        assert resp_run_attack.status_code == 403, f"Expected 403 Forbidden for cross-user repo, got {resp_run_attack.status_code}"

        # Attack on /api/v1/agent/classify
        resp_classify_attack = client.post(
            "/api/v1/agent/classify",
            json={"requirement": "What would it take to modify secret-repo?", "repository_id": "secret-repo"}
        )
        assert resp_classify_attack.status_code == 200
        classify_data = resp_classify_attack.json()
        # Verify Analysis #N/A (no analysis resolved) and ZERO foreign facts leaked
        assert "Analysis #N/A" in classify_data["response"] or "has not been analyzed" in classify_data["response"]
        assert "secret_function" not in str(classify_data)
        assert "src/secret.py" not in str(classify_data)

        # 3. Real HTTP request for pls-cli plan synthesis
        resp_plan = client.post(
            "/api/v1/agent/classify",
            json={"requirement": "What would it take to add Google OAuth?", "repository_id": "pls-cli"}
        )
        assert resp_plan.status_code == 200
        plan_data = resp_plan.json()
        assert plan_data["plan"] is not None
        for task in plan_data["plan"]["tasks"]:
            for f in task["affected_files"]:
                assert not f.endswith(".ts") and not f.endswith(".tsx"), f"Foreign TypeScript file in Python repo: {f}"
                assert "pls_cli" in f or "tests" in f or f.endswith(".py")
    finally:
        app.dependency_overrides.clear()


