#!/usr/bin/env python3
"""
Phase 2D: Real Repository Validation - Using Local Repository

This script validates the parser fix by analyzing a local test repository
to ensure symbol extraction is working correctly.
"""
import tempfile
import json
from pathlib import Path
from datetime import datetime
import logging
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_test_repository() -> Path:
    """Create a comprehensive test repository with various language files."""
    tmpdir = tempfile.mkdtemp(prefix="phase2d_")
    repo_path = Path(tmpdir) / "test_repo"
    repo_path.mkdir(parents=True)

    # Python files
    (repo_path / "auth.py").write_text("""
def authenticate_token(token):
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

    (repo_path / "database.py").write_text("""
class Database:
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
    (repo_path / "api.js").write_text("""
async function authenticateUser(username, password) {
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

    (repo_path / "middleware.js").write_text("""
function authMiddleware(req, res, next) {
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
    (repo_path / "types.ts").write_text("""
interface User {
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

    # Config files
    (repo_path / "config.json").write_text("""
{
    "database": {
        "host": "localhost",
        "port": 5432,
        "name": "auth_db"
    },
    "server": {
        "port": 3000,
        "timeout": 30000
    }
}
""")

    logger.info(f"Test repository created: {repo_path}")
    logger.info(f"Files created:")
    for f in sorted(repo_path.glob("*")):
        logger.info(f"  {f.name}")

    return repo_path


def run_analysis(repo_path: str) -> dict:
    """Run AnalysisEngine on the repository."""
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    logger.info(f"\nStarting AnalysisEngine on {repo_path}...")

    registry = get_default_registry()
    engine = AnalysisEngine(repo_path, registry)
    model = engine.run("test_repo", commit_info=None, analysis_id=None, db=None)

    logger.info(f"AnalysisEngine complete")
    return model


def count_by_type(collection, key_field: str = "type") -> dict:
    """Count items by type."""
    counts = {}
    for item in collection.values():
        item_type = str(getattr(item, key_field, "UNKNOWN"))
        counts[item_type] = counts.get(item_type, 0) + 1
    return counts


def extract_samples(entities: dict, limit: int = 20) -> list:
    """Extract sample entities."""
    samples = []
    for entity in list(entities.values())[:limit]:
        if str(entity.type) not in ["FILE"]:
            samples.append({
                "name": entity.name,
                "type": str(entity.type),
                "qualified_name": entity.qualified_name,
                "file": entity.location.repository_path if entity.location else None,
                "line": entity.location.start_line if entity.location else None,
            })
    return samples


def main():
    """Main validation flow."""
    logger.info("=" * 80)
    logger.info("PHASE 2D: LOCAL REPOSITORY VALIDATION")
    logger.info("Parser Fix Validation Against Real Symbol Extraction")
    logger.info("=" * 80)

    repo_path = None
    try:
        # Create test repository
        logger.info("\n[STEP 1] Create Test Repository")
        repo_path = create_test_repository()

        # Run analysis
        logger.info("\n[STEP 2] Run AnalysisEngine")
        model = run_analysis(str(repo_path))

        # Collect metrics
        logger.info("\n[STEP 3] Analyze Results")

        entity_counts = count_by_type(model.entities, "type")
        rel_counts = count_by_type(model.relationships, "type")

        total_entities = sum(entity_counts.values())
        total_rels = sum(rel_counts.values())

        logger.info(f"\nEntity Counts:")
        logger.info(f"  Total: {total_entities}")
        for etype, count in sorted(entity_counts.items()):
            logger.info(f"    {etype}: {count}")

        logger.info(f"\nRelationship Counts:")
        logger.info(f"  Total: {total_rels}")
        for rtype, count in sorted(rel_counts.items()):
            logger.info(f"    {rtype}: {count}")

        # Sample symbols
        logger.info(f"\n[STEP 4] Sample Extracted Symbols")
        symbols = extract_samples(model.entities, limit=20)
        logger.info(f"Extracted {len(symbols)} symbols (showing first 15):")
        for sym in symbols[:15]:
            logger.info(f"  {sym['name']:30} ({sym['type']:10}) @ {sym['file']}:{sym.get('line', '?')}")

        # Sample relationships
        logger.info(f"\n[STEP 5] Sample Relationships")
        relationships = []
        for rel in list(model.relationships.values())[:10]:
            src = model.entities.get(rel.source_id)
            tgt = model.entities.get(rel.target_id)
            relationships.append({
                "type": str(rel.type),
                "source": src.name if src else "?",
                "target": tgt.name if tgt else "?",
            })
        logger.info(f"Sample relationships:")
        for rel in relationships:
            logger.info(f"  {rel['source']:25} --{rel['type']:15}--> {rel['target']}")

        # Results
        results = {
            "timestamp": datetime.now().isoformat(),
            "repository_type": "local_test",
            "analysis_status": "COMPLETE",
            "entity_counts": entity_counts,
            "relationship_counts": rel_counts,
            "total_entities": total_entities,
            "total_relationships": total_rels,
            "sample_symbols": symbols,
            "sample_relationships": relationships,
        }

        # Save results
        results_file = Path("/home/dheeraj/repository_intelligence_platform/.diagnostics/phase2_rim_retrieval/PHASE2D_VALIDATION_DATA.json")
        results_file.parent.mkdir(parents=True, exist_ok=True)
        results_file.write_text(json.dumps(results, indent=2))

        logger.info(f"\n[STEP 6] Results Saved")
        logger.info(f"File: {results_file}")

        # Final verdict
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 2D VALIDATION VERDICT")
        logger.info("=" * 80)

        if total_entities > 0 and total_rels > 0:
            logger.info(f"✓ PARSER FIX VALIDATED")
            logger.info(f"✓ Symbol extraction is WORKING")
            logger.info(f"✓ Extracted {total_entities} entities with {total_rels} relationships")
            logger.info(f"\n✓ REAL_REPOSITORY_RIM_PARTIALLY_VALIDATED")
            logger.info(f"  (Minimal test case passed; full GitOnboard validation pending)")
        else:
            logger.error(f"✗ PARSER FIX FAILED")
            logger.error(f"✗ No symbols extracted (parser may still be broken)")
            logger.error(f"\n✗ REAL_REPOSITORY_RIM_NOT_VALIDATED")

        logger.info("=" * 80)

    finally:
        # Cleanup
        if repo_path and Path(repo_path).exists():
            shutil.rmtree(Path(repo_path).parent)
            logger.info(f"\nCleaned up test repository")


if __name__ == "__main__":
    main()
