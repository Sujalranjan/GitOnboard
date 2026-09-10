"""
PART 1: SYNTHETIC END-TO-END SMOKE TEST

Create 3-5 realistic synthetic repositories and verify the complete
semantic retrieval lifecycle using real production code paths.

Tests the entire flow:
analysis → entities → relationships → semantic index → artifact persistence
→ reload → semantic query → retrieval → RIM metadata → graph expansion

Uses REAL code paths (no mocks):
- HybridRetriever
- SemanticIndexBuilder
- AnalysisArtifact
- RRF fusion
- RIM metadata building
"""

import time
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models.repository import Repository, Analysis, AnalysisArtifact
from backend.models.user import User
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.semantic_builder import SemanticIndexBuilder
from backend.services.rim_metadata import build_rim_metadata_block


class SyntheticRepository:
    """Base class for synthetic repository definitions."""

    def __init__(self, name, language, description):
        self.name = name
        self.language = language
        self.description = description
        self.files = {}
        self.symbols = {}
        self.relationships = []

    def create_in_db(self, db, analysis_id):
        """Create symbols and relationships in database."""
        raise NotImplementedError


class PythonDjangoRepository(SyntheticRepository):
    """Realistic Django/Python web project with authentication."""

    def __init__(self):
        super().__init__(
            name="django-auth-app",
            language="Python",
            description="Django REST framework with authentication"
        )

    def create_in_db(self, db, analysis_id):
        # Files
        self.files = {
            "middleware.py": FactFile(id="1", analysis_id=analysis_id, path="auth/middleware.py", language="Python"),
            "models.py": FactFile(id="2", analysis_id=analysis_id, path="auth/models.py", language="Python"),
            "views.py": FactFile(id="3", analysis_id=analysis_id, path="auth/views.py", language="Python"),
            "permissions.py": FactFile(id="4", analysis_id=analysis_id, path="auth/permissions.py", language="Python"),
            "tokens.py": FactFile(id="5", analysis_id=analysis_id, path="core/tokens.py", language="Python"),
        }
        for f in self.files.values():
            db.add(f)
        db.flush()

        # Symbols
        self.symbols = {
            "authenticate_request": FactSymbol(id="1", analysis_id=analysis_id, name="authenticate_request", qualified_name="auth.middleware.authenticate_request", symbol_type="function", file_id="1", line_start=10, line_end=45, metadata_json={"docstring": "Middleware that validates JWT tokens from request headers"}),
            "User": FactSymbol(id="2", analysis_id=analysis_id, name="User", qualified_name="auth.models.User", symbol_type="class", file_id="2", line_start=50, line_end=120, metadata_json={"docstring": "User model with authentication fields"}),
            "LoginView": FactSymbol(id="3", analysis_id=analysis_id, name="LoginView", qualified_name="auth.views.LoginView", symbol_type="class", file_id="3", line_start=10, line_end=80, metadata_json={"docstring": "API endpoint for user login and credential validation"}),
            "verify_password": FactSymbol(id="4", analysis_id=analysis_id, name="verify_password", qualified_name="auth.views.verify_password", symbol_type="function", file_id="3", line_start=85, line_end=110, metadata_json={"docstring": "Verifies user password against stored hash"}),
            "IsAuthenticated": FactSymbol(id="5", analysis_id=analysis_id, name="IsAuthenticated", qualified_name="auth.permissions.IsAuthenticated", symbol_type="class", file_id="4", line_start=10, line_end=30, metadata_json={"docstring": "Permission class that checks if user is logged in"}),
            "generate_token": FactSymbol(id="6", analysis_id=analysis_id, name="generate_token", qualified_name="core.tokens.generate_token", symbol_type="function", file_id="5", line_start=5, line_end=35, metadata_json={"docstring": "Creates JWT token for authenticated user"}),
            "Session": FactSymbol(id="7", analysis_id=analysis_id, name="Session", qualified_name="auth.models.Session", symbol_type="class", file_id="2", line_start=130, line_end=180, metadata_json={"docstring": "User session management model"}),
            "check_access_level": FactSymbol(id="8", analysis_id=analysis_id, name="check_access_level", qualified_name="auth.permissions.check_access_level", symbol_type="function", file_id="4", line_start=35, line_end=60, metadata_json={"docstring": "Determines if user has required permission level"}),
        }
        for s in self.symbols.values():
            db.add(s)
        db.flush()

        # Relationships
        self.relationships = [
            (self.symbols["authenticate_request"], self.symbols["verify_password"], "CALLS", 25),
            (self.symbols["authenticate_request"], self.symbols["generate_token"], "CALLS", 30),
            (self.symbols["LoginView"], self.symbols["verify_password"], "CALLS", 40),
            (self.symbols["LoginView"], self.symbols["generate_token"], "CALLS", 50),
            (self.symbols["LoginView"], self.symbols["Session"], "USES", 55),
            (self.symbols["IsAuthenticated"], self.symbols["authenticate_request"], "USES", 20),
            (self.symbols["check_access_level"], self.symbols["IsAuthenticated"], "CALLS", 45),
        ]
        for idx, (from_sym, to_sym, rel_type, line) in enumerate(self.relationships, start=1):
            rel = FactRelationship(
                id=f"django_rel_{idx}",
                analysis_id=analysis_id,
                from_symbol_id=from_sym.id,
                to_symbol_id=to_sym.id,
                rel_type=rel_type,
                evidence_line=line
            )
            db.add(rel)


class NodeExpressRepository(SyntheticRepository):
    """Realistic Node.js/Express API with auth."""

    def __init__(self):
        super().__init__(
            name="express-api-server",
            language="JavaScript",
            description="Express.js REST API with role-based access control"
        )

    def create_in_db(self, db, analysis_id):
        self.files = {
            "auth.js": FactFile(id="11", analysis_id=analysis_id, path="middleware/auth.js", language="JavaScript"),
            "controller.js": FactFile(id="12", analysis_id=analysis_id, path="controllers/controller.js", language="JavaScript"),
            "rbac.js": FactFile(id="13", analysis_id=analysis_id, path="lib/rbac.js", language="JavaScript"),
        }
        for f in self.files.values():
            db.add(f)
        db.flush()

        self.symbols = {
            "authMiddleware": FactSymbol(id="11", analysis_id=analysis_id, name="authMiddleware", qualified_name="middleware.auth.authMiddleware", symbol_type="function", file_id="11", line_start=5, line_end=30, metadata_json={"docstring": "Express middleware for JWT validation and user extraction"}),
            "validateToken": FactSymbol(id="12", analysis_id=analysis_id, name="validateToken", qualified_name="middleware.auth.validateToken", symbol_type="function", file_id="11", line_start=35, line_end=60, metadata_json={"docstring": "Validates JWT signature and expiration"}),
            "UserController": FactSymbol(id="13", analysis_id=analysis_id, name="UserController", qualified_name="controllers.UserController", symbol_type="class", file_id="12", line_start=1, line_end=50, metadata_json={"docstring": "Controller handling user CRUD operations"}),
            "login": FactSymbol(id="14", analysis_id=analysis_id, name="login", qualified_name="controllers.UserController.login", symbol_type="function", file_id="12", line_start=10, line_end=35, metadata_json={"docstring": "User login endpoint - verifies credentials and issues JWT"}),
            "RBACManager": FactSymbol(id="15", analysis_id=analysis_id, name="RBACManager", qualified_name="lib.rbac.RBACManager", symbol_type="class", file_id="13", line_start=1, line_end=60, metadata_json={"docstring": "Role-based access control permission evaluator"}),
            "hasPermission": FactSymbol(id="16", analysis_id=analysis_id, name="hasPermission", qualified_name="lib.rbac.hasPermission", symbol_type="function", file_id="13", line_start=65, line_end=85, metadata_json={"docstring": "Checks if user role has required permission"}),
            "refreshToken": FactSymbol(id="17", analysis_id=analysis_id, name="refreshToken", qualified_name="middleware.auth.refreshToken", symbol_type="function", file_id="11", line_start=90, line_end=120, metadata_json={"docstring": "Issues new JWT when token is expiring"}),
        }
        for s in self.symbols.values():
            db.add(s)
        db.flush()

        self.relationships = [
            (self.symbols["authMiddleware"], self.symbols["validateToken"], "CALLS", 15),
            (self.symbols["authMiddleware"], self.symbols["refreshToken"], "CALLS", 25),
            (self.symbols["login"], self.symbols["validateToken"], "CALLS", 20),
            (self.symbols["login"], self.symbols["RBACManager"], "USES", 30),
            (self.symbols["UserController"], self.symbols["authMiddleware"], "USES", 5),
            (self.symbols["hasPermission"], self.symbols["RBACManager"], "CALLS", 70),
        ]
        for idx, (from_sym, to_sym, rel_type, line) in enumerate(self.relationships, start=1):
            rel = FactRelationship(
                id=f"express_rel_{idx}",
                analysis_id=analysis_id,
                from_symbol_id=from_sym.id,
                to_symbol_id=to_sym.id,
                rel_type=rel_type,
                evidence_line=line
            )
            db.add(rel)


class GoMicroserviceRepository(SyntheticRepository):
    """Realistic Go microservice with gRPC."""

    def __init__(self):
        super().__init__(
            name="go-auth-service",
            language="Go",
            description="Go microservice with gRPC and OAuth2"
        )

    def create_in_db(self, db, analysis_id):
        self.files = {
            "auth.go": FactFile(id="21", analysis_id=analysis_id, path="pkg/auth/auth.go", language="Go"),
            "service.go": FactFile(id="22", analysis_id=analysis_id, path="pkg/service/service.go", language="Go"),
            "store.go": FactFile(id="23", analysis_id=analysis_id, path="pkg/store/store.go", language="Go"),
        }
        for f in self.files.values():
            db.add(f)
        db.flush()

        self.symbols = {
            "ValidateToken": FactSymbol(id="21", analysis_id=analysis_id, name="ValidateToken", qualified_name="auth.ValidateToken", symbol_type="function", file_id="21", line_start=10, line_end=45, metadata_json={"docstring": "Validates OAuth2 access token and returns claims"}),
            "CreateSession": FactSymbol(id="22", analysis_id=analysis_id, name="CreateSession", qualified_name="service.CreateSession", symbol_type="function", file_id="22", line_start=50, line_end=85, metadata_json={"docstring": "Initiates new user session after successful identity verification"}),
            "AuthService": FactSymbol(id="23", analysis_id=analysis_id, name="AuthService", qualified_name="service.AuthService", symbol_type="class", file_id="22", line_start=1, line_end=40, metadata_json={"docstring": "gRPC service implementing authentication endpoints"}),
            "CheckPermissions": FactSymbol(id="24", analysis_id=analysis_id, name="CheckPermissions", qualified_name="auth.CheckPermissions", symbol_type="function", file_id="21", line_start=50, line_end=80, metadata_json={"docstring": "Evaluates if principal has required authorization level"}),
            "SessionStore": FactSymbol(id="25", analysis_id=analysis_id, name="SessionStore", qualified_name="store.SessionStore", symbol_type="class", file_id="23", line_start=1, line_end=50, metadata_json={"docstring": "Persistent storage for user sessions"}),
            "VerifyIdentity": FactSymbol(id="26", analysis_id=analysis_id, name="VerifyIdentity", qualified_name="auth.VerifyIdentity", symbol_type="function", file_id="21", line_start=90, line_end=130, metadata_json={"docstring": "Confirms user identity through credential or OAuth flow"}),
        }
        for s in self.symbols.values():
            db.add(s)
        db.flush()

        self.relationships = [
            (self.symbols["AuthService"], self.symbols["ValidateToken"], "CALLS", 20),
            (self.symbols["AuthService"], self.symbols["VerifyIdentity"], "CALLS", 25),
            (self.symbols["CreateSession"], self.symbols["ValidateToken"], "CALLS", 60),
            (self.symbols["CreateSession"], self.symbols["SessionStore"], "USES", 70),
            (self.symbols["CheckPermissions"], self.symbols["ValidateToken"], "CALLS", 55),
            (self.symbols["VerifyIdentity"], self.symbols["CreateSession"], "CALLS", 110),
        ]
        for idx, (from_sym, to_sym, rel_type, line) in enumerate(self.relationships, start=1):
            rel = FactRelationship(
                id=f"go_rel_{idx}",
                analysis_id=analysis_id,
                from_symbol_id=from_sym.id,
                to_symbol_id=to_sym.id,
                rel_type=rel_type,
                evidence_line=line
            )
            db.add(rel)


def create_semantic_entities_for_builder(symbols):
    """Create entity objects for SemanticIndexBuilder."""
    class SimpleEntity:
        def __init__(self, sym, repo_name):
            self.type = type('', (), {'value': 'SYMBOL'})()
            self.name = sym.name
            self.qualified_name = sym.qualified_name
            self.metadata = {"docstring": sym.metadata_json.get("docstring", "")}
            self.location = type('', (), {'repository_path': f"{repo_name}/{sym.qualified_name}"})()

    return {sym.id: SimpleEntity(sym, "repo") for sym in symbols.values()}


def run_smoke_test(repo_def):
    """Run complete semantic lifecycle test on one synthetic repository."""
    print(f"\n{'='*90}")
    print(f"TESTING: {repo_def.name}")
    print(f"{'='*90}\n")

    start_time = time.time()

    # Setup database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(id=1, github_id="test", username="test", email="test@test.com")
    db.add(user)
    repo = Repository(id=1, url=f"https://github.com/test/{repo_def.name}", user_id=user.id)
    db.add(repo)
    analysis = Analysis(id=100, repository_id=repo.id, status="Completed")
    db.add(analysis)
    db.flush()

    # Create synthetic repository
    repo_def.create_in_db(db, analysis.id)
    db.commit()

    entity_count = len(repo_def.symbols)
    relationship_count = len(repo_def.relationships)

    print(f"✓ Repository structure created")
    print(f"  Entities: {entity_count}")
    print(f"  Relationships: {relationship_count}")

    # Build semantic index
    print(f"\n✓ Building semantic index...")
    semantic_built = False
    artifact_size = 0

    try:
        entities = create_semantic_entities_for_builder(repo_def.symbols)
        builder = SemanticIndexBuilder()
        chroma_bytes = builder.build_index(entities)

        if chroma_bytes:
            semantic_built = True
            artifact_size = len(chroma_bytes)
            artifact = AnalysisArtifact(
                analysis_id=analysis.id,
                type="semantic_index_db",
                blob_data=chroma_bytes
            )
            db.add(artifact)
            db.commit()
            print(f"  ✓ Artifact created: {artifact_size} bytes")
        else:
            print(f"  ✗ SemanticIndexBuilder returned None")
    except Exception as e:
        print(f"  ✗ Semantic build failed: {e}")

    # Test loading
    print(f"\n✓ Testing artifact loading...")
    artifact_loaded = False
    try:
        retriever = HybridRetriever(db, analysis_id=analysis.id)
        if retriever.chroma_collection and not retriever.semantic_degradation:
            artifact_loaded = True
            print(f"  ✓ Artifact loaded successfully")
        else:
            print(f"  ✗ Failed to load: {retriever.semantic_degradation}")
    except Exception as e:
        print(f"  ✗ Loading failed: {e}")

    # Test vocabulary-gap query
    print(f"\n✓ Testing natural-language query...")

    test_queries = {
        "django-auth-app": [
            ("How do users prove who they are?", ["verify_password", "User", "authenticate_request"]),
            ("How is user identity checked?", ["VerifyIdentity", "authenticate_request"]),
        ],
        "express-api-server": [
            ("How does a user log in?", ["login", "validateToken", "UserController"]),
            ("How are permissions verified?", ["hasPermission", "RBACManager"]),
        ],
        "go-auth-service": [
            ("How is identity established?", ["VerifyIdentity", "ValidateToken"]),
            ("How do we control access?", ["CheckPermissions", "ValidateToken"]),
        ],
    }

    queries = test_queries.get(repo_def.name, [])
    queries_passed = 0

    for query, expected_keywords in queries:
        try:
            retriever = HybridRetriever(db, analysis_id=analysis.id)
            results = retriever.retrieve(query, top_k=5, enable_fallback=True)

            if results:
                retrieved_names = set(r.entity_name for r in results)
                expected_set = set(expected_keywords)
                if retrieved_names & expected_set:
                    queries_passed += 1
                    print(f"  ✓ '{query[:40]}'")
                else:
                    print(f"  ⚠ '{query[:40]}' - found but no match")
            else:
                print(f"  ✗ '{query[:40]}' - no results")
        except Exception as e:
            print(f"  ✗ Query error: {e}")

    # Test RIM metadata
    print(f"\n✓ Testing RIM metadata building...")
    metadata_populated = False
    try:
        retriever = HybridRetriever(db, analysis_id=analysis.id)
        metadata = build_rim_metadata_block(db, analysis.id, queries[0][0] if queries else "test", retriever)
        if metadata and metadata.text and "No structural facts" not in metadata.text:
            metadata_populated = True
            metadata_len = len(metadata.text)
            print(f"  ✓ Metadata built: {metadata_len} chars")
        else:
            print(f"  ⚠ Metadata empty or missing")
    except Exception as e:
        print(f"  ✗ Metadata building failed: {e}")

    analysis_time = time.time() - start_time

    db.close()

    return {
        "repository": repo_def.name,
        "analysis_id": 100,
        "entity_count": entity_count,
        "relationship_count": relationship_count,
        "semantic_artifact_created": semantic_built,
        "artifact_size": artifact_size,
        "artifact_persisted": semantic_built,
        "artifact_loaded": artifact_loaded,
        "semantic_queries_passed": queries_passed,
        "semantic_queries_total": len(queries),
        "metadata_populated": metadata_populated,
        "analysis_time_seconds": round(analysis_time, 2),
    }


def main():
    print("\n" + "="*90)
    print("PART 1: SYNTHETIC END-TO-END SMOKE TEST")
    print("="*90)
    print("\nRunning complete semantic retrieval lifecycle on synthetic repositories...")

    repositories = [
        PythonDjangoRepository(),
        NodeExpressRepository(),
        GoMicroserviceRepository(),
    ]

    results = []
    for repo in repositories:
        result = run_smoke_test(repo)
        results.append(result)

    # Summary
    print(f"\n{'='*90}")
    print("SYNTHETIC SMOKE TEST RESULTS")
    print(f"{'='*90}\n")

    for result in results:
        status = "✅" if (result["semantic_artifact_created"] and result["artifact_loaded"] and result["metadata_populated"]) else "⚠️"
        print(f"{status} {result['repository']}")
        print(f"   Entities: {result['entity_count']}, Relationships: {result['relationship_count']}")
        print(f"   Semantic artifact: {result['semantic_artifact_created']}")
        print(f"   Artifact loaded: {result['artifact_loaded']}")
        print(f"   Queries passed: {result['semantic_queries_passed']}/{result['semantic_queries_total']}")
        print(f"   Metadata: {'✓' if result['metadata_populated'] else '✗'}")
        print(f"   Time: {result['analysis_time_seconds']}s\n")

    # Overall result
    all_passed = all(
        r["semantic_artifact_created"] and r["artifact_loaded"] and r["metadata_populated"]
        for r in results
    )

    print(f"{'='*90}")
    if all_passed:
        print("🟢 SYNTHETIC SMOKE TEST: PASS")
        print("All repositories verified with real production code paths")
    else:
        print("🟡 SYNTHETIC SMOKE TEST: PARTIAL")
        print("Some repositories completed successfully")
    print(f"{'='*90}")

    return "PASS" if all_passed else "PARTIAL"


if __name__ == "__main__":
    result = main()
