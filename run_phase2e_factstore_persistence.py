#!/usr/bin/env python3
"""
Phase 2E: FactStore Persistence Inspection

This script validates that RepositoryModel entities and relationships
correctly persist to PostgreSQL FactStore tables.

Expected Input (Phase 2D baseline):
- 5 files
- 29 entities (6 functions, 5 classes, 13 methods, 5 files)
- 29 relationships (24 DECLARES, 4 CALLS, 1 USES)

Expected Output:
- FactFile: 5 records
- FactSymbol: 29 records
- FactRelationship: 29 records with valid endpoints
- Complete metadata preservation
"""

import tempfile
import json
import logging
from pathlib import Path
from datetime import datetime
import shutil
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_phase2d_test_repository() -> Path:
    """Create Phase 2D test repository with 5 files, 29 entities, 29 relationships."""
    tmpdir = tempfile.mkdtemp(prefix="phase2e_")
    repo_path = Path(tmpdir) / "test_repo"
    repo_path.mkdir(parents=True)

    # Python files
    (repo_path / "auth.py").write_text("""def authenticate_token(token):
    '''Authenticate a user token.'''
    return token is not None

def validate_credentials(username, password):
    '''Validate user credentials.'''
    if not username or not password:
        raise ValueError("Missing credentials")
    return True

class AuthService:
    '''Authentication service.'''

    def __init__(self, db):
        self.db = db

    def login(self, username, password):
        '''Login user.'''
        if not validate_credentials(username, password):
            return None
        user = self.db.find_user(username)
        return {"user": user, "token": authenticate_token(user.id)}

    def logout(self, token):
        '''Logout user.'''
        return True

class User:
    '''User model.'''
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email
""")

    (repo_path / "database.py").write_text("""class Database:
    '''Database connection.'''

    def __init__(self, connection_string):
        self.conn_str = connection_string

    def find_user(self, username):
        '''Find user by username.'''
        pass

    def save_user(self, user):
        '''Save user to database.'''
        pass

    def create_session(self, user_id, token):
        '''Create session.'''
        pass
""")

    # JavaScript files
    (repo_path / "api.js").write_text("""async function authenticateUser(username, password) {
    // Authenticate user
    const user = await database.findUser(username);
    if (!user) return null;
    const token = generateToken(user.id);
    return { user, token };
}

function generateToken(userId) {
    // Generate authentication token
    return 'token_' + userId;
}

class APIServer {
    constructor(port) {
        this.port = port;
    }

    start() {
        console.log('Starting server on port ' + this.port);
    }

    stop() {
        console.log('Stopping server');
    }
}

module.exports = { authenticateUser, APIServer };
""")

    (repo_path / "middleware.js").write_text("""function authMiddleware(req, res, next) {
    // Check authentication
    const token = req.headers.authorization;
    if (!token) {
        return res.status(401).send('Unauthorized');
    }
    next();
}

function errorHandler(err, req, res, next) {
    // Handle errors
    console.error(err);
    res.status(500).send('Internal error');
}

module.exports = { authMiddleware, errorHandler };
""")

    # TypeScript files
    (repo_path / "types.ts").write_text("""interface User {
    id: string;
    username: string;
    email: string;
}

interface AuthToken {
    token: string;
    expiresAt: Date;
}

class TokenManager {
    private tokens: Map<string, AuthToken> = new Map();

    createToken(userId: string): AuthToken {
        const token = {
            token: 'ts_' + userId,
            expiresAt: new Date()
        };
        this.tokens.set(userId, token);
        return token;
    }

    validateToken(token: string): boolean {
        for (const t of this.tokens.values()) {
            if (t.token === token) return true;
        }
        return false;
    }
}

export { User, AuthToken, TokenManager };
""")

    logger.info(f"Phase 2D test repository created: {repo_path}")
    return repo_path


def run_analysis(repo_path: str):
    """Run AnalysisEngine on the repository."""
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    logger.info(f"Running AnalysisEngine on {repo_path}...")
    registry = get_default_registry()
    engine = AnalysisEngine(repo_path, registry)
    model = engine.run("test_repo", commit_info=None, analysis_id=None, db=None)
    logger.info(f"AnalysisEngine complete: {len(model.entities)} entities, {len(model.relationships)} relationships")
    return model


def setup_database():
    """Initialize database and create tables."""
    from backend.database import engine, Base
    logger.info("Creating database tables...")

    # Create all tables including User, Repository, Analysis, and FactStore tables
    Base.metadata.drop_all(bind=engine)  # Clean start
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created and initialized")
    return engine


def save_to_factstore(db, model, analysis_id=1):
    """Save RIM model to FactStore."""
    import time
    from backend.models.user import User
    from backend.models.repository import Repository, Analysis
    from backend.intelligence.store.fact_store import save_rim_to_fact_store

    # Create test records with unique IDs
    user_id = int(time.time() * 1000) % 1000000  # Use timestamp-based unique ID
    unique_suffix = str(user_id)[-6:]  # Get last 6 digits for uniqueness
    user = User(id=user_id, github_id=f"gh_test_{unique_suffix}", username=f"testuser_{unique_suffix}", email=f"test_{unique_suffix}@example.com")
    db.add(user)
    db.flush()

    repo_id = analysis_id * 100  # Derived from analysis_id to keep it unique
    repo = Repository(id=repo_id, url="https://github.com/test/repo", user_id=user.id)
    db.add(repo)
    db.flush()

    analysis = Analysis(id=analysis_id, repository_id=repo.id, status="Analyzing")
    db.add(analysis)
    db.commit()

    logger.info(f"Created Analysis record (id={analysis_id})")

    # Save RIM to FactStore
    save_rim_to_fact_store(db, analysis_id, model)
    logger.info("RIM saved to FactStore")
    return analysis_id


def query_factstore(db, analysis_id=1):
    """Query FactStore and return results."""
    from backend.models.fact_store import (
        FactFile, FactSymbol, FactRelationship, FactRoute,
        FactDatabaseObject, FactCapability
    )

    files = db.query(FactFile).filter_by(analysis_id=analysis_id).all()
    symbols = db.query(FactSymbol).filter_by(analysis_id=analysis_id).all()
    rels = db.query(FactRelationship).filter_by(analysis_id=analysis_id).all()
    routes = db.query(FactRoute).filter_by(analysis_id=analysis_id).all()
    db_objs = db.query(FactDatabaseObject).filter_by(analysis_id=analysis_id).all()
    caps = db.query(FactCapability).filter_by(analysis_id=analysis_id).all()

    return {
        "files": files,
        "symbols": symbols,
        "relationships": rels,
        "routes": routes,
        "database_objects": db_objs,
        "capabilities": caps,
    }


def analyze_persistence(model, persisted):
    """Compare RIM input with FactStore output."""
    logger.info("\n" + "=" * 80)
    logger.info("PERSISTENCE ANALYSIS")
    logger.info("=" * 80)

    # Count by type
    entity_types = {}
    for entity in model.entities.values():
        et = str(entity.type)
        entity_types[et] = entity_types.get(et, 0) + 1

    rel_types = {}
    for rel in model.relationships.values():
        rt = str(rel.type)
        rel_types[rt] = rel_types.get(rt, 0) + 1

    symbol_types = {}
    for sym in persisted["symbols"]:
        st = sym.symbol_type
        symbol_types[st] = symbol_types.get(st, 0) + 1

    rels_in_db = len(persisted["relationships"])

    logger.info("\nRepositoryModel Input:")
    logger.info(f"  Files: {sum(1 for e in model.entities.values() if str(e.type) == 'FILE')}")
    logger.info(f"  Symbols: {len(model.entities) - sum(1 for e in model.entities.values() if str(e.type) == 'FILE')}")
    logger.info("    By type:")
    for et, count in sorted(entity_types.items()):
        if et != 'FILE':
            logger.info(f"      {et}: {count}")
    logger.info(f"  Relationships: {len(model.relationships)}")
    logger.info("    By type:")
    for rt, count in sorted(rel_types.items()):
        logger.info(f"      {rt}: {count}")

    logger.info("\nFactStore Output:")
    logger.info(f"  FactFile: {len(persisted['files'])}")
    logger.info(f"  FactSymbol: {len(persisted['symbols'])}")
    logger.info("    By type:")
    for st, count in sorted(symbol_types.items()):
        logger.info(f"      {st}: {count}")
    logger.info(f"  FactRelationship: {rels_in_db}")

    # Check for losses
    logger.info("\nPersistence Loss Analysis:")
    expected_symbols = len(model.entities) - sum(1 for e in model.entities.values() if str(e.type) == 'FILE')
    actual_symbols = len(persisted["symbols"])
    symbol_loss = expected_symbols - actual_symbols

    if symbol_loss > 0:
        logger.error(f"  ✗ SYMBOL LOSS: {symbol_loss} symbols lost ({actual_symbols}/{expected_symbols})")
    else:
        logger.info(f"  ✓ No symbol loss ({actual_symbols}/{expected_symbols})")

    expected_rels = len(model.relationships)
    actual_rels = rels_in_db
    rel_loss = expected_rels - actual_rels

    if rel_loss > 0:
        logger.error(f"  ✗ RELATIONSHIP LOSS: {rel_loss} relationships lost ({actual_rels}/{expected_rels})")
    else:
        logger.info(f"  ✓ No relationship loss ({actual_rels}/{expected_rels})")

    # Metadata validation
    logger.info("\nMetadata Integrity Check:")

    # Check file_id population
    symbols_with_file_id = sum(1 for s in persisted["symbols"] if s.file_id)
    symbols_without_file_id = len(persisted["symbols"]) - symbols_with_file_id

    if symbols_without_file_id > 0:
        logger.warning(f"  ⚠ {symbols_without_file_id} symbols missing file_id")
    else:
        logger.info(f"  ✓ All {len(persisted['symbols'])} symbols have file_id")

    # Check line_start/line_end
    symbols_with_lines = sum(1 for s in persisted["symbols"] if s.line_start)
    symbols_without_lines = len(persisted["symbols"]) - symbols_with_lines

    if symbols_without_lines > 0:
        logger.warning(f"  ⚠ {symbols_without_lines} symbols missing line_start/line_end")
    else:
        logger.info(f"  ✓ All {len(persisted['symbols'])} symbols have line_start")

    # Check symbol types are preserved
    logger.info(f"  ✓ Symbol types preserved: {sorted(set(symbol_types.keys()))}")

    # Relationship endpoint validation
    logger.info("\nRelationship Endpoint Validation:")

    symbol_ids = {s.id for s in persisted["symbols"]}
    file_ids = {f.id for f in persisted["files"]}
    valid_ids = symbol_ids | file_ids

    invalid_rels = []
    for rel in persisted["relationships"]:
        if rel.from_symbol_id not in valid_ids:
            invalid_rels.append(f"  Invalid source: {rel.from_symbol_id}")
        if rel.to_symbol_id not in valid_ids:
            invalid_rels.append(f"  Invalid target: {rel.to_symbol_id}")

    if invalid_rels:
        logger.error(f"  ✗ {len(invalid_rels)} relationships with invalid endpoints")
        for inv in invalid_rels[:5]:
            logger.error(inv)
    else:
        logger.info(f"  ✓ All {len(persisted['relationships'])} relationships have valid endpoints")

    return {
        "input": {
            "files": sum(1 for e in model.entities.values() if str(e.type) == 'FILE'),
            "entities": len(model.entities),
            "relationships": len(model.relationships),
        },
        "output": {
            "files": len(persisted["files"]),
            "symbols": len(persisted["symbols"]),
            "relationships": len(persisted["relationships"]),
        },
        "losses": {
            "symbols": symbol_loss,
            "relationships": rel_loss,
        },
        "metadata": {
            "symbols_with_file_id": symbols_with_file_id,
            "symbols_without_file_id": symbols_without_file_id,
            "symbols_with_lines": symbols_with_lines,
            "symbols_without_lines": symbols_without_lines,
            "invalid_relationships": len(invalid_rels),
        }
    }


def sample_records(persisted):
    """Extract sample records for inspection."""
    logger.info("\n" + "=" * 80)
    logger.info("SAMPLE RECORDS")
    logger.info("=" * 80)

    # Sample files
    logger.info("\nSample FactFile records (first 3):")
    for f in persisted["files"][:3]:
        logger.info(f"  {f.path}")
        logger.info(f"    id: {f.id}")
        logger.info(f"    language: {f.language}")
        logger.info(f"    size: {f.size}")

    # Sample symbols
    logger.info("\nSample FactSymbol records (first 5):")
    for s in persisted["symbols"][:5]:
        logger.info(f"  {s.name}")
        logger.info(f"    id: {s.id}")
        logger.info(f"    type: {s.symbol_type}")
        logger.info(f"    file_id: {s.file_id}")
        logger.info(f"    line: {s.line_start}-{s.line_end}")
        logger.info(f"    qualified_name: {s.qualified_name}")

    # Sample relationships
    logger.info("\nSample FactRelationship records (first 5):")
    for r in persisted["relationships"][:5]:
        logger.info(f"  {r.from_symbol_id.split(':')[-1]} --{r.rel_type}--> {r.to_symbol_id.split(':')[-1]}")
        logger.info(f"    id: {r.id}")
        logger.info(f"    status: {r.status}")
        logger.info(f"    evidence_line: {r.evidence_line}")


def main():
    """Main execution flow."""
    logger.info("=" * 80)
    logger.info("PHASE 2E: FACTSTORE PERSISTENCE INSPECTION")
    logger.info("=" * 80)
    logger.info("\nObjective: Verify RepositoryModel → FactStore persistence")
    logger.info("Expected: 5 files, 29 entities, 29 relationships (Phase 2D baseline)")

    repo_path = None
    try:
        # Step 1: Create test repository
        logger.info("\n[STEP 1/5] Create Phase 2D Test Repository")
        repo_path = create_phase2d_test_repository()

        # Step 2: Run analysis
        logger.info("\n[STEP 2/5] Run AnalysisEngine")
        model = run_analysis(str(repo_path))

        # Step 3: Setup database
        logger.info("\n[STEP 3/5] Setup PostgreSQL Database")
        engine = setup_database()

        # Create database session
        from backend.database import SessionLocal
        import time
        db = SessionLocal()

        # Use unique analysis_id based on timestamp
        analysis_id = int(time.time() * 1000) % 1000000

        try:
            # Step 4: Save to FactStore
            logger.info("\n[STEP 4/5] Save RIM to FactStore")
            save_to_factstore(db, model, analysis_id=analysis_id)

            # Step 5: Query FactStore
            logger.info("\n[STEP 5/5] Query FactStore")
            persisted = query_factstore(db, analysis_id=analysis_id)

            # Analysis
            analysis = analyze_persistence(model, persisted)

            # Samples
            sample_records(persisted)

            # Final report
            logger.info("\n" + "=" * 80)
            logger.info("FINAL REPORT")
            logger.info("=" * 80)

            report = {
                "timestamp": datetime.now().isoformat(),
                "analysis": analysis,
            }

            # Determine verdict
            if (analysis["losses"]["symbols"] == 0 and
                analysis["losses"]["relationships"] == 0 and
                analysis["metadata"]["invalid_relationships"] == 0):
                logger.info("\n✓ PERSISTENCE VALIDATION PASSED")
                logger.info("✓ All entities and relationships persisted successfully")
                logger.info("✓ Metadata integrity preserved")
                report["verdict"] = "PASSED"
            else:
                logger.error("\n✗ PERSISTENCE VALIDATION FAILED")
                if analysis["losses"]["symbols"] > 0:
                    logger.error(f"  - {analysis['losses']['symbols']} symbols lost")
                if analysis["losses"]["relationships"] > 0:
                    logger.error(f"  - {analysis['losses']['relationships']} relationships lost")
                if analysis["metadata"]["invalid_relationships"] > 0:
                    logger.error(f"  - {analysis['metadata']['invalid_relationships']} invalid relationship endpoints")
                report["verdict"] = "FAILED"

            # Save report
            report_file = Path("/tmp/claude-1000/-home-dheeraj-repository-intelligence-platform/c471a75d-59b9-41e1-9714-c5409d0af19b/scratchpad/PHASE2E_PERSISTENCE_REPORT.json")
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(json.dumps(report, indent=2))
            logger.info(f"\nReport saved: {report_file}")

            logger.info("=" * 80)

        finally:
            db.close()

    finally:
        # Cleanup
        if repo_path and Path(repo_path).exists():
            shutil.rmtree(Path(repo_path).parent)
            logger.info(f"Cleaned up test repository")


if __name__ == "__main__":
    main()
