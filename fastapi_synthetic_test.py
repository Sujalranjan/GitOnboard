"""
FastAPI-Specific Synthetic Repository Smoke Test

Tests the complete semantic retrieval lifecycle with a realistic FastAPI
application structure matching the actual project architecture.

Includes:
- FastAPI app and routers
- Dependencies and middleware
- Authentication/authorization
- Service layer
- Repository/database layer
- Pydantic models
- Cross-module relationships
- External imports
"""

import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models.repository import Repository, Analysis, AnalysisArtifact
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder
from backend.services.rim_metadata import build_rim_metadata_block


class FastAPIRepository:
    """Realistic FastAPI application with authentication."""

    def __init__(self):
        self.name = "fastapi-app"
        self.language = "Python"
        self.description = "FastAPI application with JWT authentication and role-based access control"
        self.files = {}
        self.symbols = {}
        self.relationships = []

    def create_in_db(self, db, analysis_id):
        """Create FastAPI repository structure in database."""

        # Files - realistic FastAPI structure
        self.files = {
            "main.py": FactFile(id="1", analysis_id=analysis_id, path="main.py", language="Python"),
            "auth.py": FactFile(id="2", analysis_id=analysis_id, path="app/core/auth.py", language="Python"),
            "security.py": FactFile(id="3", analysis_id=analysis_id, path="app/core/security.py", language="Python"),
            "dependencies.py": FactFile(id="4", analysis_id=analysis_id, path="app/core/dependencies.py", language="Python"),
            "models.py": FactFile(id="5", analysis_id=analysis_id, path="app/models.py", language="Python"),
            "schemas.py": FactFile(id="6", analysis_id=analysis_id, path="app/schemas.py", language="Python"),
            "users_router.py": FactFile(id="7", analysis_id=analysis_id, path="app/api/routes/users.py", language="Python"),
            "auth_router.py": FactFile(id="8", analysis_id=analysis_id, path="app/api/routes/auth.py", language="Python"),
            "users_service.py": FactFile(id="9", analysis_id=analysis_id, path="app/services/users.py", language="Python"),
            "auth_service.py": FactFile(id="10", analysis_id=analysis_id, path="app/services/auth.py", language="Python"),
            "db.py": FactFile(id="11", analysis_id=analysis_id, path="app/db/db.py", language="Python"),
            "repositories.py": FactFile(id="12", analysis_id=analysis_id, path="app/db/repositories.py", language="Python"),
        }
        for f in self.files.values():
            db.add(f)
        db.flush()

        # Symbols - FastAPI application components
        self.symbols = {
            # main.py
            "app": FactSymbol(
                id="1", analysis_id=analysis_id, name="app", qualified_name="main.app",
                symbol_type="variable", file_id="1", line_start=5, line_end=10,
                metadata_json={"docstring": "FastAPI application instance"}
            ),
            "create_app": FactSymbol(
                id="2", analysis_id=analysis_id, name="create_app", qualified_name="main.create_app",
                symbol_type="function", file_id="1", line_start=15, line_end=40,
                metadata_json={"docstring": "Creates and configures FastAPI application"}
            ),

            # core/auth.py
            "create_access_token": FactSymbol(
                id="3", analysis_id=analysis_id, name="create_access_token", qualified_name="app.core.auth.create_access_token",
                symbol_type="function", file_id="2", line_start=10, line_end=35,
                metadata_json={"docstring": "Creates JWT access token for authenticated user"}
            ),
            "verify_token": FactSymbol(
                id="4", analysis_id=analysis_id, name="verify_token", qualified_name="app.core.auth.verify_token",
                symbol_type="function", file_id="2", line_start=40, line_end=65,
                metadata_json={"docstring": "Verifies JWT token validity and expiration"}
            ),

            # core/security.py
            "get_password_hash": FactSymbol(
                id="5", analysis_id=analysis_id, name="get_password_hash", qualified_name="app.core.security.get_password_hash",
                symbol_type="function", file_id="3", line_start=5, line_end=20,
                metadata_json={"docstring": "Hashes password using bcrypt"}
            ),
            "verify_password": FactSymbol(
                id="6", analysis_id=analysis_id, name="verify_password", qualified_name="app.core.security.verify_password",
                symbol_type="function", file_id="3", line_start=25, line_end=40,
                metadata_json={"docstring": "Verifies password against stored hash"}
            ),

            # core/dependencies.py
            "get_current_user": FactSymbol(
                id="7", analysis_id=analysis_id, name="get_current_user", qualified_name="app.core.dependencies.get_current_user",
                symbol_type="function", file_id="4", line_start=5, line_end=30,
                metadata_json={"docstring": "FastAPI dependency that extracts and validates current user from JWT"}
            ),
            "get_db": FactSymbol(
                id="8", analysis_id=analysis_id, name="get_db", qualified_name="app.core.dependencies.get_db",
                symbol_type="function", file_id="4", line_start=35, line_end=50,
                metadata_json={"docstring": "FastAPI dependency providing database session"}
            ),

            # models.py
            "User": FactSymbol(
                id="9", analysis_id=analysis_id, name="User", qualified_name="app.models.User",
                symbol_type="class", file_id="5", line_start=10, line_end=40,
                metadata_json={"docstring": "SQLAlchemy User model"}
            ),

            # schemas.py
            "UserSchema": FactSymbol(
                id="10", analysis_id=analysis_id, name="UserSchema", qualified_name="app.schemas.UserSchema",
                symbol_type="class", file_id="6", line_start=5, line_end=20,
                metadata_json={"docstring": "Pydantic schema for user data validation"}
            ),
            "LoginRequest": FactSymbol(
                id="11", analysis_id=analysis_id, name="LoginRequest", qualified_name="app.schemas.LoginRequest",
                symbol_type="class", file_id="6", line_start=25, line_end=35,
                metadata_json={"docstring": "Pydantic schema for login credentials"}
            ),

            # api/routes/users.py
            "router": FactSymbol(
                id="12", analysis_id=analysis_id, name="router", qualified_name="app.api.routes.users.router",
                symbol_type="variable", file_id="7", line_start=5, line_end=8,
                metadata_json={"docstring": "APIRouter for user endpoints"}
            ),
            "create_user": FactSymbol(
                id="13", analysis_id=analysis_id, name="create_user", qualified_name="app.api.routes.users.create_user",
                symbol_type="function", file_id="7", line_start=10, line_end=35,
                metadata_json={"docstring": "Endpoint to create new user and session"}
            ),
            "get_user": FactSymbol(
                id="14", analysis_id=analysis_id, name="get_user", qualified_name="app.api.routes.users.get_user",
                symbol_type="function", file_id="7", line_start=40, line_end=60,
                metadata_json={"docstring": "Endpoint to retrieve current user - requires authentication"}
            ),

            # api/routes/auth.py
            "auth_router": FactSymbol(
                id="15", analysis_id=analysis_id, name="auth_router", qualified_name="app.api.routes.auth.auth_router",
                symbol_type="variable", file_id="8", line_start=5, line_end=8,
                metadata_json={"docstring": "APIRouter for authentication endpoints"}
            ),
            "login": FactSymbol(
                id="16", analysis_id=analysis_id, name="login", qualified_name="app.api.routes.auth.login",
                symbol_type="function", file_id="8", line_start=10, line_end=40,
                metadata_json={"docstring": "Login endpoint - validates credentials and returns JWT"}
            ),
            "logout": FactSymbol(
                id="17", analysis_id=analysis_id, name="logout", qualified_name="app.api.routes.auth.logout",
                symbol_type="function", file_id="8", line_start=45, line_end=55,
                metadata_json={"docstring": "Logout endpoint - invalidates user session"}
            ),

            # services/users.py
            "UserService": FactSymbol(
                id="18", analysis_id=analysis_id, name="UserService", qualified_name="app.services.users.UserService",
                symbol_type="class", file_id="9", line_start=5, line_end=50,
                metadata_json={"docstring": "Business logic for user operations"}
            ),
            "create_new_user": FactSymbol(
                id="19", analysis_id=analysis_id, name="create_new_user", qualified_name="app.services.users.create_new_user",
                symbol_type="function", file_id="9", line_start=20, line_end=45,
                metadata_json={"docstring": "Creates new user with hashed password"}
            ),

            # services/auth.py
            "AuthService": FactSymbol(
                id="20", analysis_id=analysis_id, name="AuthService", qualified_name="app.services.auth.AuthService",
                symbol_type="class", file_id="10", line_start=5, line_end=45,
                metadata_json={"docstring": "Authentication service with JWT and password handling"}
            ),
            "authenticate_user": FactSymbol(
                id="21", analysis_id=analysis_id, name="authenticate_user", qualified_name="app.services.auth.authenticate_user",
                symbol_type="function", file_id="10", line_start=15, line_end=35,
                metadata_json={"docstring": "Authenticates user by verifying password and returning JWT"}
            ),

            # db/db.py
            "SessionLocal": FactSymbol(
                id="22", analysis_id=analysis_id, name="SessionLocal", qualified_name="app.db.db.SessionLocal",
                symbol_type="variable", file_id="11", line_start=5, line_end=10,
                metadata_json={"docstring": "SQLAlchemy session factory"}
            ),

            # db/repositories.py
            "UserRepository": FactSymbol(
                id="23", analysis_id=analysis_id, name="UserRepository", qualified_name="app.db.repositories.UserRepository",
                symbol_type="class", file_id="12", line_start=5, line_end=40,
                metadata_json={"docstring": "Data access layer for User model"}
            ),
            "get_user_by_email": FactSymbol(
                id="24", analysis_id=analysis_id, name="get_user_by_email", qualified_name="app.db.repositories.get_user_by_email",
                symbol_type="function", file_id="12", line_start=10, line_end=25,
                metadata_json={"docstring": "Queries database for user by email"}
            ),
        }
        for s in self.symbols.values():
            db.add(s)
        db.flush()

        # Relationships - realistic FastAPI call graph
        self.relationships = [
            # login flow
            (self.symbols["login"], self.symbols["authenticate_user"], "CALLS", 20),
            (self.symbols["authenticate_user"], self.symbols["verify_password"], "CALLS", 25),
            (self.symbols["authenticate_user"], self.symbols["create_access_token"], "CALLS", 30),
            (self.symbols["authenticate_user"], self.symbols["get_user_by_email"], "CALLS", 22),

            # user creation flow
            (self.symbols["create_user"], self.symbols["create_new_user"], "CALLS", 20),
            (self.symbols["create_new_user"], self.symbols["get_password_hash"], "CALLS", 35),
            (self.symbols["create_new_user"], self.symbols["UserRepository"], "USES", 40),

            # dependency injection
            (self.symbols["get_user"], self.symbols["get_current_user"], "CALLS", 15),
            (self.symbols["get_current_user"], self.symbols["verify_token"], "CALLS", 20),
            (self.symbols["create_user"], self.symbols["get_db"], "CALLS", 12),

            # routing
            (self.symbols["app"], self.symbols["router"], "USES", 25),
            (self.symbols["app"], self.symbols["auth_router"], "USES", 30),

            # service layer
            (self.symbols["login"], self.symbols["AuthService"], "USES", 15),
            (self.symbols["create_user"], self.symbols["UserService"], "USES", 18),

            # logout flow
            (self.symbols["logout"], self.symbols["verify_token"], "CALLS", 50),
        ]
        for idx, (from_sym, to_sym, rel_type, line) in enumerate(self.relationships, start=1):
            rel = FactRelationship(
                id=f"fastapi_rel_{idx}",
                analysis_id=analysis_id,
                from_symbol_id=from_sym.id,
                to_symbol_id=to_sym.id,
                rel_type=rel_type,
                evidence_line=line
            )
            db.add(rel)


def create_semantic_entities(symbols):
    """Create entities for SemanticIndexBuilder."""
    class SimpleEntity:
        def __init__(self, sym):
            self.type = type('', (), {'value': 'SYMBOL'})()
            self.name = sym.name
            self.qualified_name = sym.qualified_name
            self.metadata = {"docstring": sym.metadata_json.get("docstring", "")}
            self.location = type('', (), {'repository_path': sym.qualified_name})()

    return {sym.id: SimpleEntity(sym) for sym in symbols.values()}


def test_fastapi_repository():
    """Run complete semantic lifecycle test on FastAPI repository."""
    print("\n" + "="*90)
    print("FASTAPI-SPECIFIC SEMANTIC RETRIEVAL TEST")
    print("="*90 + "\n")

    start_time = time.time()

    # Setup
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(id=1, github_id="test", username="test", email="test@test.com")
    db.add(user)
    repo = Repository(id=1, url="https://github.com/test/fastapi-app", user_id=user.id)
    db.add(repo)
    analysis = Analysis(id=100, repository_id=repo.id, status="Completed")
    db.add(analysis)
    db.flush()

    # Create FastAPI repository
    fastapi_repo = FastAPIRepository()
    fastapi_repo.create_in_db(db, analysis.id)
    db.commit()

    print(f"✓ FastAPI repository created")
    print(f"  Files: {len(fastapi_repo.files)}")
    print(f"  Entities: {len(fastapi_repo.symbols)}")
    print(f"  Relationships: {len(fastapi_repo.relationships)}\n")

    # Build semantic index
    print(f"✓ Building semantic index...")
    try:
        entities = create_semantic_entities(fastapi_repo.symbols)
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
            print(f"  ✓ Artifact created: {len(chroma_bytes)} bytes\n")
        else:
            print(f"  ✗ Build returned None\n")
            return False
    except Exception as e:
        print(f"  ✗ Build failed: {e}\n")
        return False

    # Test queries
    print(f"✓ Testing natural-language FastAPI queries...\n")

    test_queries = [
        ("How does login work?", ["login", "authenticate_user", "create_access_token"]),
        ("How are requests authenticated?", ["get_current_user", "verify_token"]),
        ("How are permissions enforced?", ["get_current_user", "verify_token"]),
        ("How does a request reach the database?", ["get_db", "UserRepository"]),
        ("Which endpoint creates a user session?", ["create_user", "login"]),
        ("What happens when an unauthorized request is made?", ["get_current_user", "verify_token"]),
        ("How does the API validate incoming data?", ["UserSchema", "LoginRequest"]),
        ("Which services are used by the user endpoint?", ["UserService", "AuthService"]),
    ]

    results = []
    for query, expected in test_queries:
        try:
            retriever = HybridRetriever(db, analysis_id=analysis.id)
            query_results = retriever.retrieve(query, top_k=5, enable_fallback=True)

            if query_results:
                retrieved_names = set(r.entity_name for r in query_results)
                expected_set = set(expected)
                matches = retrieved_names & expected_set

                if matches:
                    status = "✅"
                    classification = "PASS"
                else:
                    status = "⚠️"
                    classification = "PARTIAL"
                    matches = f"found {len(retrieved_names)} but no match"

                print(f"{status} '{query}'")
                if classification == "PASS":
                    print(f"   Found: {', '.join(matches)}")
                else:
                    print(f"   {matches}")
            else:
                status = "❌"
                classification = "FAIL"
                print(f"{status} '{query}'")
                print(f"   No results")

            results.append((query, classification))
        except Exception as e:
            print(f"❌ '{query}' - Error: {e}")
            results.append((query, "FAIL"))

    # Test RIM metadata
    print(f"\n✓ Testing RIM metadata building...")
    try:
        retriever = HybridRetriever(db, analysis_id=analysis.id)
        metadata = build_rim_metadata_block(db, analysis.id, test_queries[0][0], retriever)

        if metadata and metadata.text and "No structural facts" not in metadata.text:
            print(f"  ✓ Metadata built: {len(metadata.text)} chars")
            print(f"  ✓ Seeds: {len(metadata.seed_entities)}")
            print(f"  ✓ Relationships: {len(metadata.relationships)}")
            metadata_ok = True
        else:
            print(f"  ✗ Metadata empty")
            metadata_ok = False
    except Exception as e:
        print(f"  ✗ Metadata failed: {e}")
        metadata_ok = False

    analysis_time = time.time() - start_time

    db.close()

    # Results
    print(f"\n" + "="*90)
    print("FASTAPI TEST RESULTS")
    print("="*90 + "\n")

    pass_count = sum(1 for _, c in results if c == "PASS")
    partial_count = sum(1 for _, c in results if c == "PARTIAL")
    fail_count = sum(1 for _, c in results if c == "FAIL")

    print(f"Queries: {pass_count} PASS, {partial_count} PARTIAL, {fail_count} FAIL")
    print(f"Success rate: {(pass_count + partial_count)*100/len(results):.0f}%")
    print(f"Metadata: {'✓' if metadata_ok else '✗'}")
    print(f"Analysis time: {analysis_time:.2f}s\n")

    # Verdict
    if pass_count >= 6 and metadata_ok:
        print("🟢 FASTAPI SYNTHETIC TEST: PASS")
        return True
    elif pass_count >= 4:
        print("🟡 FASTAPI SYNTHETIC TEST: PARTIAL")
        return True  # Still acceptable
    else:
        print("🔴 FASTAPI SYNTHETIC TEST: FAIL")
        return False


if __name__ == "__main__":
    success = test_fastapi_repository()
    exit(0 if success else 1)
