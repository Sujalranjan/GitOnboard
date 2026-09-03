#!/usr/bin/env python3
"""
Integration test: RIM Pipeline with realistic test data.

Creates a complete repository analysis with:
- Multiple symbols (functions, classes)
- Real relationships (CALLS, IMPORTS, CONTAINS)
- Routes and capabilities
- Tests the complete RIM pipeline

This verifies all fixes work end-to-end.
"""

import sys
import logging
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models.fact_store import (
    FactSymbol, FactFile, FactRoute, FactRelationship,
    FactCapability, FactCapabilityMember
)
from backend.models.repository import Repository, Analysis
from backend.models.user import User
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.services.rim_metadata import _build_rim_metadata_block_impl

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Create in-memory test database
test_db_url = "sqlite:///:memory:"
engine = create_engine(test_db_url)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def setup_test_data():
    """Create a realistic test repository with authentication flow."""
    session = Session()

    try:
        # Create user
        user = User(
            id=999,
            github_id="test-user",
            email="test@test.com",
            username="testuser"
        )
        session.add(user)
        session.flush()

        # Create repository
        repo = Repository(id=999, url="https://github.com/test/test-backend", user_id=user.id)
        session.add(repo)
        session.flush()

        # Create analysis
        analysis = Analysis(id=1, repository_id=repo.id, status="Completed")
        session.add(analysis)
        session.flush()

        # Create files
        auth_file = FactFile(
            id="test:file:auth",
            analysis_id=analysis.id,
            path="middleware/auth.js",
            language="javascript"
        )
        user_file = FactFile(
            id="test:file:user",
            analysis_id=analysis.id,
            path="routes/users.js",
            language="javascript"
        )
        controller_file = FactFile(
            id="test:file:controller",
            analysis_id=analysis.id,
            path="controllers/authController.js",
            language="javascript"
        )
        session.add_all([auth_file, user_file, controller_file])
        session.flush()

        # Create symbols (authentication flow)
        auth_middleware = FactSymbol(
            id="test:sym:authMiddleware",
            analysis_id=analysis.id,
            file_id="test:file:auth",
            name="authMiddleware",
            symbol_type="function",
            line_start=5,
            line_end=25
        )
        authenticate_token = FactSymbol(
            id="test:sym:authenticateToken",
            analysis_id=analysis.id,
            file_id="test:file:controller",
            name="authenticateToken",
            symbol_type="function",
            line_start=35,
            line_end=55
        )
        hash_token = FactSymbol(
            id="test:sym:hashToken",
            analysis_id=analysis.id,
            file_id="test:file:controller",
            name="hashToken",
            symbol_type="function",
            line_start=60,
            line_end=75
        )
        create_session = FactSymbol(
            id="test:sym:createSession",
            analysis_id=analysis.id,
            file_id="test:file:controller",
            name="createSession",
            symbol_type="function",
            line_start=80,
            line_end=100
        )
        verify_identity = FactSymbol(
            id="test:sym:verifyIdentity",
            analysis_id=analysis.id,
            file_id="test:file:controller",
            name="verifyIdentity",
            symbol_type="function",
            line_start=105,
            line_end=125
        )
        session.add_all([auth_middleware, authenticate_token, hash_token, create_session, verify_identity])
        session.flush()

        # Create relationships (authentication flow)
        # authMiddleware CALLS authenticateToken
        rel1 = FactRelationship(
            id="test:rel:1",
            analysis_id=analysis.id,
            from_symbol_id="test:sym:authMiddleware",
            to_symbol_id="test:sym:authenticateToken",
            rel_type="CALLS"
        )
        # authenticateToken CALLS hashToken
        rel2 = FactRelationship(
            id="test:rel:2",
            analysis_id=analysis.id,
            from_symbol_id="test:sym:authenticateToken",
            to_symbol_id="test:sym:hashToken",
            rel_type="CALLS"
        )
        # authenticateToken CALLS createSession
        rel3 = FactRelationship(
            id="test:rel:3",
            analysis_id=analysis.id,
            from_symbol_id="test:sym:authenticateToken",
            to_symbol_id="test:sym:createSession",
            rel_type="CALLS"
        )
        # createSession CALLS verifyIdentity
        rel4 = FactRelationship(
            id="test:rel:4",
            analysis_id=analysis.id,
            from_symbol_id="test:sym:createSession",
            to_symbol_id="test:sym:verifyIdentity",
            rel_type="CALLS"
        )
        session.add_all([rel1, rel2, rel3, rel4])
        session.flush()

        # Create routes
        login_route = FactRoute(
            id="test:route:login",
            analysis_id=analysis.id,
            method="POST",
            path="/api/auth/login",
            handler_symbol_id="test:sym:authenticateToken"
        )
        session.add(login_route)
        session.flush()

        # Create capability
        auth_capability = FactCapability(
            id="test:cap:auth",
            analysis_id=analysis.id,
            name="Authentication",
            capability_type="SECURITY"
        )
        session.add(auth_capability)
        session.flush()

        # Add members to capability
        member1 = FactCapabilityMember(
            id="test:capmem:1",
            capability_id="test:cap:auth",
            symbol_id="test:sym:authMiddleware",
            role="entry_point"
        )
        member2 = FactCapabilityMember(
            id="test:capmem:2",
            capability_id="test:cap:auth",
            symbol_id="test:sym:authenticateToken",
            role="service"
        )
        member3 = FactCapabilityMember(
            id="test:capmem:3",
            capability_id="test:cap:auth",
            symbol_id="test:sym:createSession",
            role="service"
        )
        session.add_all([member1, member2, member3])
        session.flush()

        session.commit()
        logger.info("Test data created successfully")
        logger.info(f"  Symbols: 5")
        logger.info(f"  Relationships: 4")
        logger.info(f"  Routes: 1")
        logger.info(f"  Capabilities: 1")

        return analysis.id

    except Exception as e:
        logger.error(f"Failed to setup test data: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()

def test_rim_pipeline(analysis_id):
    """Test the RIM pipeline with real data."""
    session = Session()

    try:
        question = "How does login feature work?"
        logger.info(f"\n{'='*80}")
        logger.info(f"Testing RIM Pipeline")
        logger.info(f"Question: {question}")
        logger.info(f"Analysis ID: {analysis_id}")
        logger.info(f"{'='*80}\n")

        # Initialize retriever
        retriever = HybridRetriever(session, analysis_id)

        # Build RIM metadata
        metadata_block = _build_rim_metadata_block_impl(
            session,
            analysis_id,
            question,
            retriever,
            max_seed_entities=5,
            max_related_per_seed=10,
            max_block_chars=4000,
        )

        # Report results
        logger.info(f"\nRIM METADATA RESULTS:")
        logger.info(f"  Content length: {len(metadata_block.text)}")
        logger.info(f"  Relationship types found: {metadata_block.relationship_types_used}")
        logger.info(f"  Seed entities: {len(metadata_block.seed_entities)}")
        logger.info(f"  Relationships: {len(metadata_block.relationships)}")
        logger.info(f"\n  Metadata content:")
        for line in metadata_block.text.split('\n'):
            logger.info(f"    {line}")

        # Verify results
        logger.info(f"\nVERIFICATION:")
        if len(metadata_block.text) > 100 and "No structural facts" not in metadata_block.text:
            logger.info("  ✅ Metadata generated")
        else:
            logger.warning("  ❌ Metadata not generated or empty")

        if len(metadata_block.relationship_types_used) > 0:
            logger.info(f"  ✅ Found relationships: {metadata_block.relationship_types_used}")
        else:
            logger.warning("  ❌ No relationships found")

        # Success criteria
        success = (
            len(metadata_block.text) > 100 and
            "No structural facts" not in metadata_block.text and
            len(metadata_block.relationship_types_used) > 0
        )

        if success:
            logger.info(f"\n🟢 RIM PIPELINE TEST: PASS")
        else:
            logger.warning(f"\n🔴 RIM PIPELINE TEST: FAIL")

        return success

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False
    finally:
        session.close()

if __name__ == "__main__":
    try:
        analysis_id = setup_test_data()
        success = test_rim_pipeline(analysis_id)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
