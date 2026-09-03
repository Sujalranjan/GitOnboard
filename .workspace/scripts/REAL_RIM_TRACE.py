#!/usr/bin/env python3
"""
PHASE 1 DIAGNOSTIC: Trace real RIM execution on Deep-Guard-Backend.

This script will:
1. Load the analyzed Deep-Guard-Backend repository from the database
2. Run "How does login feature work?" query
3. Instrument every boundary in the RIM pipeline
4. Report where valid information is lost

IMPORTANT: This uses REAL data and REAL execution paths.
"""

import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.fact_store import FactSymbol, FactFile, FactRoute, FactDatabaseObject, Base
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from backend.agent.intent.semantic_query import SemanticQueryClass, TraversalDirection, SemanticQueryIntent
from backend.services.rim_metadata import _build_rim_metadata_block_impl

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("RIM_TRACE")

def find_analysis_id():
    """Find the Deep-Guard-Backend analysis ID."""
    engine = create_engine("sqlite:///./data/local.db")
    Session = sessionmaker(bind=engine)
    session = Session()

    # Query for Deep-Guard-Backend
    # Look for a repository that contains auth-related symbols
    symbols = session.query(FactSymbol).filter(
        FactSymbol.name.ilike("%auth%")
    ).limit(1).all()

    if symbols:
        analysis_id = symbols[0].analysis_id
        logger.info(f"Found analysis_id: {analysis_id} for repository with auth symbols")
        return analysis_id, session

    # Fallback: get first analysis
    try:
        symbol = session.query(FactSymbol).first()
        if symbol:
            analysis_id = symbol.analysis_id
            logger.info(f"Using first available analysis_id: {analysis_id}")
            return analysis_id, session
    except:
        pass

    logger.error("No analysis found in database")
    return None, session

def trace_rim_pipeline(analysis_id, session):
    """Trace the complete RIM pipeline."""

    question = "How does login feature work?"
    logger.info(f"=== TRACING RIM PIPELINE ===")
    logger.info(f"Question: {question}")
    logger.info(f"Analysis ID: {analysis_id}")

    # Phase 1: Retriever
    logger.info("\n=== PHASE 1: RETRIEVER ===")
    try:
        retriever = HybridRetriever(session, analysis_id)
        logger.info("HybridRetriever initialized")

        candidates = retriever.retrieve(question, top_k=5, expand_with_fact_store=False)
        logger.info(f"Candidates retrieved: {len(candidates)}")

        for i, cand in enumerate(candidates):
            logger.info(f"\nCandidate {i+1}:")
            logger.info(f"  Type: {type(cand).__name__}")
            if hasattr(cand, 'entity_name'):
                logger.info(f"  entity_name: {cand.entity_name}")
            if hasattr(cand, 'name'):
                logger.info(f"  name: {cand.name}")
            if hasattr(cand, 'score'):
                logger.info(f"  score: {cand.score}")
            if hasattr(cand, 'file_path'):
                logger.info(f"  file_path: {cand.file_path}")
            if hasattr(cand, 'entity_type'):
                logger.info(f"  entity_type: {cand.entity_type}")
            # Print all attributes
            for attr in dir(cand):
                if not attr.startswith('_') and not callable(getattr(cand, attr)):
                    try:
                        val = getattr(cand, attr)
                        logger.debug(f"  {attr}: {val}")
                    except:
                        pass
    except Exception as e:
        logger.error(f"Retriever failed: {e}", exc_info=True)
        return

    # Phase 2: Entity Extraction
    logger.info("\n=== PHASE 2: ENTITY EXTRACTION ===")
    seeds = []
    extracted_names = set()

    for i, cand in enumerate(candidates[:3]):
        logger.info(f"\nExtracting from candidate {i+1}:")

        entity_name = ""
        if hasattr(cand, "entity_name"):
            entity_name = cand.entity_name
            logger.info(f"  extracted entity_name: '{entity_name}'")
        elif isinstance(cand, dict):
            entity_name = cand.get("entity_name") or cand.get("name") or cand.get("match_name") or ""
            logger.info(f"  extracted from dict: '{entity_name}'")

        if not entity_name:
            logger.warning(f"  NO ENTITY NAME EXTRACTED")
            continue

        extracted_names.add(entity_name)

    logger.info(f"\nExtracted unique entity names: {extracted_names}")

    # Phase 3: Seed Resolution
    logger.info("\n=== PHASE 3: SEED RESOLUTION ===")

    for entity_name in extracted_names:
        logger.info(f"\nResolving: '{entity_name}'")

        # Try FactSymbol
        symbol = session.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.name.ilike(entity_name),
        ).first()

        if symbol:
            logger.info(f"  RESOLVED to FactSymbol: id={symbol.id}, name={symbol.name}, type={symbol.symbol_type}")
            seeds.append(("symbol", entity_name, symbol))
        else:
            logger.warning(f"  NOT RESOLVED (no matching FactSymbol)")

    logger.info(f"\nTotal seeds resolved: {len(seeds)}")

    # Phase 4: Graph Traversal
    logger.info("\n=== PHASE 4: GRAPH TRAVERSAL ===")

    traverser = FactStoreGraphTraverser(session, analysis_id)
    all_relationships = []
    traversal_log = []

    for seed_type, seed_name, target in seeds:
        logger.info(f"\nTraversing seed: {seed_name} (type: {seed_type})")

        # Determine which relationship classes to traverse
        if seed_type == "symbol":
            query_classes = [
                SemanticQueryClass.CONTAINMENT,
                SemanticQueryClass.CALLS_FORWARD,
                SemanticQueryClass.CALLS_REVERSE,
                SemanticQueryClass.INHERITS_FORWARD,
                SemanticQueryClass.INHERITS_REVERSE,
            ]
        else:
            query_classes = [SemanticQueryClass.CONTAINMENT]

        for query_class in query_classes:
            logger.info(f"\n  Query class: {query_class}")

            # Determine direction
            if query_class in (SemanticQueryClass.CALLS_REVERSE, SemanticQueryClass.INHERITS_REVERSE):
                direction = TraversalDirection.REVERSE
            else:
                direction = TraversalDirection.FORWARD

            logger.info(f"    Direction: {direction}")

            intent = SemanticQueryIntent(
                query_class=query_class,
                target_raw_name=seed_name,
                direction=direction,
                confidence=1.0,
            )

            try:
                result = traverser.traverse(intent, target)
                logger.info(f"    Relationships found: {len(result.related_entities)}")

                for j, entity in enumerate(result.related_entities[:8]):
                    entity_name_rel = entity.name if hasattr(entity, "name") else entity.get("name", "?")
                    entity_type_rel = entity.entity_type if hasattr(entity, "entity_type") else entity.get("entity_type", "?")
                    logger.info(f"      {j+1}. {entity_name_rel} ({entity_type_rel})")

                    rel_record = {
                        'from': seed_name,
                        'relationship': query_class.name,
                        'to': entity_name_rel,
                        'entity_type': entity_type_rel,
                    }
                    all_relationships.append(rel_record)
                    traversal_log.append(f"  {seed_name} --[{query_class.name}]--> {entity_name_rel}")

                if not result.related_entities:
                    logger.info(f"    NO RELATIONSHIPS FOUND")
                    traversal_log.append(f"  {seed_name} --[{query_class.name}]--> (NO RESULTS)")

            except Exception as e:
                logger.error(f"    Traversal failed: {e}", exc_info=True)

    # Phase 5: Metadata Generation
    logger.info("\n=== PHASE 5: METADATA GENERATION ===")

    try:
        block = _build_rim_metadata_block_impl(
            session,
            analysis_id,
            question,
            retriever,
            max_seed_entities=3,
            max_related_per_seed=8,
            max_block_chars=4000,
        )
        logger.info(f"RIM Metadata block generated:")
        logger.info(f"  Text length: {len(block.text)}")
        logger.info(f"  Relationship types: {block.relationship_types_used}")
        logger.info(f"  Content:\n{block.text}")
    except Exception as e:
        logger.error(f"Metadata generation failed: {e}", exc_info=True)

    # Summary
    logger.info("\n=== SUMMARY ===")
    logger.info(f"Seeds found: {len(seeds)}")
    logger.info(f"Relationships discovered: {len(all_relationships)}")
    logger.info(f"Traversal graph:")
    for line in traversal_log:
        logger.info(line)

    # Compare with expected
    logger.info("\n=== EXPECTED vs ACTUAL ===")
    logger.info("Expected entities: authMiddleware, authenticateToken, createSession, etc.")
    logger.info(f"Actual seeds: {[s[1] for s in seeds]}")
    logger.info(f"Actual relationships: {len(all_relationships)}")

    return {
        'seeds': seeds,
        'relationships': all_relationships,
        'metadata': block,
    }

if __name__ == "__main__":
    analysis_id, session = find_analysis_id()
    if analysis_id:
        result = trace_rim_pipeline(analysis_id, session)
        print("\n" + "="*80)
        print("TRACE COMPLETE - See logs above for detailed output")
        print("="*80)
    session.close()
