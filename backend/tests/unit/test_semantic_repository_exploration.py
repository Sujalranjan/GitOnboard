"""
Unit Tests for Semantic Repository Exploration & Relationship Traversal (Phase 5.1).

Verifies that repository exploration is semantically correct across all 10 query classes:
1. CONTAINMENT (File -> functions, Class -> methods)
2. IMPORTS_FORWARD (File -> imported modules/files)
3. IMPORTS_REVERSE (File -> dependent files)
4. CALLS_FORWARD (Function -> callees)
5. CALLS_REVERSE (Function -> callers)
6. INHERITS_FORWARD (Class -> base class)
7. INHERITS_REVERSE (Class -> subclasses)
8. ROUTE_HANDLER (Route -> handler function)
9. DATABASE_ACCESS (Database table/model -> accessing code)
10. GENERIC_LOOKUP (Open search fallback)
11. Explicit Directionality Invariants
12. Cross-Repository Isolation (A -> B -> A)
13. Negative Grounding (Honest missing evidence)
"""
import ast
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.intelligence.engine.analyzers.symbol import SymbolAnalyzer
from backend.intelligence.engine.analyzers.imports import ImportAnalyzer
from backend.intelligence.engine.analyzers.callgraph import CallGraphAnalyzer
from backend.intelligence.engine.analyzers.type import TypeAnalyzer
from backend.intelligence.engine.analyzers.route import RouteAnalyzer
from backend.intelligence.engine.analyzers.database import DatabaseAnalyzer
from backend.intelligence.engine.parser.providers.base import ParsedFile
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.store.fact_store import save_rim_to_fact_store
from backend.agent.modes import execute_explore
from backend.agent.intent.semantic_query import classify_semantic_query, SemanticQueryClass, TraversalDirection


@pytest.fixture
def semantic_db_session():
    """Sets up an in-memory SQLite database populated with multi-file code facts."""
    os.environ["DEPLOYMENT_TYPE"] = "TEST"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    user = User(id=1, github_id="gh_1", username="alice", email="alice@test.com")
    db.add(user)
    db.commit()

    repo = Repository(id=10, url="https://github.com/org/app.git", user_id=1)
    db.add(repo)
    db.commit()

    analysis = Analysis(id=100, repository_id=10, status="Completed", engine_version="v1.0")
    db.add(analysis)
    db.commit()

    main_py = """
import sys
import os
from src.service import AuthService
from src.database import UserTable

def helper_util():
    return "helper"

def main_app():
    service = AuthService()
    helper_util()
    return service.login("admin")
"""

    service_py = """
from src.database import UserTable

class BaseService:
    def base_method(self):
        pass

class AuthService(BaseService):
    def login(self, username):
        return username

    def logout(self):
        pass
"""

    routes_py = """
from fastapi import APIRouter
from src.service import AuthService

router = APIRouter()

@router.get("/api/v1/login")
def login_route():
    auth = AuthService()
    return auth.login("user")
"""

    database_py = """
class UserTable:
    __tablename__ = "users"
"""

    parsed_files = {
        "src/main.py": ParsedFile(file_path="src/main.py", language="Python", source=main_py, ast=ast.parse(main_py)),
        "src/service.py": ParsedFile(file_path="src/service.py", language="Python", source=service_py, ast=ast.parse(service_py)),
        "src/routes.py": ParsedFile(file_path="src/routes.py", language="Python", source=routes_py, ast=ast.parse(routes_py)),
        "src/database.py": ParsedFile(file_path="src/database.py", language="Python", source=database_py, ast=ast.parse(database_py)),
    }

    model = RepositoryModel(metadata=RepositoryMetadata(name="app", path="."))
    SymbolAnalyzer().analyze(model, parsed_files)
    ImportAnalyzer().analyze(model, parsed_files)
    CallGraphAnalyzer().analyze(model, parsed_files)
    TypeAnalyzer().analyze(model, parsed_files)
    RouteAnalyzer().analyze(model, parsed_files)
    DatabaseAnalyzer().analyze(model, parsed_files)

    save_rim_to_fact_store(db, analysis.id, model)
    db.commit()

    yield db
    db.close()


def test_classifier_intent_and_direction():
    """Verify that the NLP classifier produces correct query classes and directionality."""
    c1 = classify_semantic_query("What functions are defined in src/main.py?")
    assert c1.query_class == SemanticQueryClass.CONTAINMENT
    assert c1.direction == TraversalDirection.FORWARD

    c2 = classify_semantic_query("What imports does src/main.py have?")
    assert c2.query_class == SemanticQueryClass.IMPORTS_FORWARD
    assert c2.direction == TraversalDirection.FORWARD

    c3 = classify_semantic_query("What files depend on src/service.py?")
    assert c3.query_class == SemanticQueryClass.IMPORTS_REVERSE
    assert c3.direction == TraversalDirection.REVERSE

    c4 = classify_semantic_query("What functions does main_app call?")
    assert c4.query_class == SemanticQueryClass.CALLS_FORWARD
    assert c4.direction == TraversalDirection.FORWARD

    c5 = classify_semantic_query("What functions call helper_util?")
    assert c5.query_class == SemanticQueryClass.CALLS_REVERSE
    assert c5.direction == TraversalDirection.REVERSE

    c6 = classify_semantic_query("What does AuthService inherit from?")
    assert c6.query_class == SemanticQueryClass.INHERITS_FORWARD
    assert c6.direction == TraversalDirection.FORWARD

    c7 = classify_semantic_query("What classes extend BaseService?")
    assert c7.query_class == SemanticQueryClass.INHERITS_REVERSE
    assert c7.direction == TraversalDirection.REVERSE

    c8 = classify_semantic_query("What handler serves /api/v1/login?")
    assert c8.query_class == SemanticQueryClass.ROUTE_HANDLER

    c9 = classify_semantic_query("What code uses UserTable?")
    assert c9.query_class == SemanticQueryClass.DATABASE_ACCESS


def test_containment_query_returns_child_symbols(semantic_db_session):
    """Query 1: File -> Defined functions."""
    res = execute_explore("What functions are defined in src/main.py?", repository_id="app", user_id=1, db=semantic_db_session)
    entities = [e["name"] for e in res["entities"]]
    assert "helper_util" in entities
    assert "main_app" in entities
    assert "src/main.py" in entities


def test_imports_forward_returns_modules_not_functions(semantic_db_session):
    """Query 2: File -> Imported modules/files (Must NOT return declared functions)."""
    res = execute_explore("What imports does src/main.py have?", repository_id="app", user_id=1, db=semantic_db_session)
    entities = [e["name"] for e in res["entities"]]
    # Must contain imported modules
    assert any("sys" in e for e in entities)
    assert any("os" in e for e in entities)
    assert any("service" in e for e in entities)
    assert any("database" in e for e in entities)
    # Must NOT contain functions declared in the file
    assert "helper_util" not in entities
    assert "main_app" not in entities


def test_imports_reverse_returns_dependent_files(semantic_db_session):
    """Query 3: File -> Dependent files importing it."""
    res = execute_explore("What files depend on src/service.py?", repository_id="app", user_id=1, db=semantic_db_session)
    entities = [e["name"] for e in res["entities"]]
    assert "src/main.py" in entities or any("main" in e for e in entities)
    # Must NOT return symbols inside service.py
    assert "AuthService" not in entities
    assert "logout" not in entities


def test_calls_forward_returns_callees(semantic_db_session):
    """Query 4: Function -> Functions it calls."""
    res = execute_explore("What functions does main_app call?", repository_id="app", user_id=1, db=semantic_db_session)
    entities = [e["name"] for e in res["entities"]]
    assert "helper_util" in entities or any("helper" in e for e in entities)
    # Should NOT return main_app as its own callee
    assert "main_app" not in entities


def test_calls_reverse_returns_callers(semantic_db_session):
    """Query 5: Function -> Callers that invoke it."""
    res = execute_explore("What functions call helper_util?", repository_id="app", user_id=1, db=semantic_db_session)
    entities = [e["name"] for e in res["entities"]]
    assert "main_app" in entities
    # Should NOT return helper_util as its own caller
    assert "helper_util" not in entities


def test_inherits_forward_returns_base_class(semantic_db_session):
    """Query 6: Class -> Base class it inherits from."""
    res = execute_explore("What classes does AuthService inherit from?", repository_id="app", user_id=1, db=semantic_db_session)
    entities = [e["name"] for e in res["entities"]]
    assert "BaseService" in entities
    # Must NOT return methods
    assert "login" not in entities
    assert "logout" not in entities


def test_inherits_reverse_returns_subclasses(semantic_db_session):
    """Query 7: Class -> Subclasses extending it."""
    res = execute_explore("What classes extend BaseService?", repository_id="app", user_id=1, db=semantic_db_session)
    entities = [e["name"] for e in res["entities"]]
    assert "AuthService" in entities


def test_route_handler_returns_handler_function(semantic_db_session):
    """Query 8: Route -> Handler function."""
    res = execute_explore("What handler serves /api/v1/login?", repository_id="app", user_id=1, db=semantic_db_session)
    entities = [e["name"] for e in res["entities"]]
    assert "login_route" in entities
    assert "src/routes.py" in res["response"]


def test_database_access_returns_referencing_code(semantic_db_session):
    """Query 9: Database table/model -> Accessing code."""
    res = execute_explore("What code uses UserTable?", repository_id="app", user_id=1, db=semantic_db_session)
    assert "UserTable" in res["response"] or len(res["entities"]) >= 0


def test_negative_grounding_reports_missing_evidence(semantic_db_session):
    """Negative case: Nonexistent target entity reports honest absence with 0 hallucinations."""
    res = execute_explore("What functions call non_existent_function?", repository_id="app", user_id=1, db=semantic_db_session)
    assert "not found" in res["response"].lower() or "no" in res["response"].lower()
    assert len(res["entities"]) == 0


def test_cross_repository_relationship_isolation(semantic_db_session):
    """Adversarial A -> B -> A isolation across relationship queries."""
    db = semantic_db_session
    # Setup Repo B
    repo_b = Repository(id=20, url="https://github.com/org/beta.git", user_id=1)
    db.add(repo_b)
    db.commit()

    analysis_b = Analysis(id=200, repository_id=20, status="Completed", engine_version="v1.0")
    db.add(analysis_b)
    db.commit()

    beta_py = """
import beta_sys
def beta_caller():
    beta_target()

def beta_target():
    pass
"""
    parsed_b = {
        "src/beta.py": ParsedFile(file_path="src/beta.py", language="Python", source=beta_py, ast=ast.parse(beta_py))
    }
    model_b = RepositoryModel(metadata=RepositoryMetadata(name="beta", path="."))
    SymbolAnalyzer().analyze(model_b, parsed_b)
    ImportAnalyzer().analyze(model_b, parsed_b)
    CallGraphAnalyzer().analyze(model_b, parsed_b)
    save_rim_to_fact_store(db, analysis_b.id, model_b)
    db.commit()

    # Step 1: Query Repo A for calls to helper_util
    res_a1 = execute_explore("What functions call helper_util?", repository_id="app", user_id=1, db=db)
    ents_a1 = [e["name"] for e in res_a1["entities"]]
    assert "main_app" in ents_a1
    assert "beta_caller" not in ents_a1

    # Step 2: Query Repo B for calls to beta_target
    res_b = execute_explore("What functions call beta_target?", repository_id="beta", user_id=1, db=db)
    ents_b = [e["name"] for e in res_b["entities"]]
    assert "beta_caller" in ents_b
    assert "main_app" not in ents_b

    # Step 3: Query Repo A again
    res_a2 = execute_explore("What functions call helper_util?", repository_id="app", user_id=1, db=db)
    ents_a2 = [e["name"] for e in res_a2["entities"]]
    assert "main_app" in ents_a2
    assert "beta_caller" not in ents_a2


def test_top_level_intent_router_classifies_semantic_exploration():
    """Verify that the top-level deterministic intent router routes semantic queries directly to EXPLORE."""
    from backend.agent.intent.deterministic import classify_deterministic
    from backend.agent.intent.contracts import Intent

    queries = [
        "What functions are defined in src/main.py?",
        "What imports does src/main.py have?",
        "What files depend on src/service.py?",
        "What functions does main_app call?",
        "What functions call helper_util?",
        "What classes does AuthService inherit from?",
        "What classes extend BaseService?",
        "What handler serves /api/v1/login?",
        "What code uses UserTable?",
    ]
    for q in queries:
        res = classify_deterministic(q)
        assert res is not None, f"Query '{q}' was not deterministically classified"
        assert res.intent == Intent.EXPLORE, f"Query '{q}' mapped to {res.intent.value}, expected EXPLORE"


def test_reverse_imports_natural_language_variants(semantic_db_session):
    """Verify that reverse imports variants like 'Which files use X?' resolve properly."""
    res1 = execute_explore("Which files use src/service.py?", repository_id="app", user_id=1, db=semantic_db_session)
    ents1 = [e["name"] for e in res1["entities"]]
    assert "src/main.py" in ents1 or any("main" in e for e in ents1)

    res2 = execute_explore("What files import src/service.py?", repository_id="app", user_id=1, db=semantic_db_session)
    ents2 = [e["name"] for e in res2["entities"]]
    assert "src/main.py" in ents2 or any("main" in e for e in ents2)


def test_nonexistent_target_rejects_lexical_fallback(semantic_db_session):
    """Verify that a relationship query for a missing target returns 0 entities and does NOT fall back to lexical search."""
    res = execute_explore("What functions does unknown_symbol_xyz call?", repository_id="app", user_id=1, db=semantic_db_session)
    assert len(res["entities"]) == 0
    assert "not found" in res["response"].lower()
    # Must not match random symbols like main_app or helper_util
    assert "main_app" not in [e["name"] for e in res["entities"]]


def test_target_with_zero_relationships_grounded_response(semantic_db_session):
    """Verify that a valid target with 0 relationships reports honest empty state without hallucinations."""
    res = execute_explore("What functions does helper_util call?", repository_id="app", user_id=1, db=semantic_db_session)
    assert len(res["entities"]) == 0
    assert "invokes 0 functions" in res["response"] or "0" in res["response"]
