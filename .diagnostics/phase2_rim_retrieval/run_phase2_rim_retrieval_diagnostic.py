#!/usr/bin/env python3
"""
Phase 2 Diagnostic: Trace RIM retrieval pipeline for auth query.
Tests each stage: retriever → resolver → traverser
"""

import logging
import sys
from pathlib import Path

# Add repo to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))

from backend.ai.service import get_llm_service
from backend.services.rim_metadata import (
    build_rim_metadata_block,
    TargetEntityResolver,
)
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Use PostgreSQL database like the backend does
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gionboard_user:gionboard_password@localhost:5432/gionboard",
)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
from backend.agent.intent.semantic_query import (
    SemanticQueryClass,
    TraversalDirection,
    SemanticQueryIntent,
)
from backend.models.fact_store import FactSymbol, FactFile, FactRoute

# Enable debug logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    db = SessionLocal()
    repo_name = "GitOnboard"
    question = "How does authentication work in this repo?"

    try:
        # Get analysis
        from backend.routers.repo.services.analysis import get_latest_analysis
        from backend.models.user import User

        # Get the first user (or create if needed)
        user = db.query(User).first()
        if not user:
            print("[✗] No users in database. Create a user first.")
            return False

        repo, analysis = get_latest_analysis(repo_name, db, current_user=user)
        analysis_id = analysis.id
        print(f"\n{'=' * 70}")
        print(f"PHASE 2: RIM Retrieval Pipeline Diagnostic")
        print(f"{'=' * 70}")
        print(f"Repository: {repo_name}")
        print(f"Analysis ID: {analysis_id}")
        print(f"Question: {question}\n")

        # ──────────────────────────────────────────────────────────────
        # STAGE 1: HybridRetriever
        # ──────────────────────────────────────────────────────────────
        print(f"{'=' * 70}")
        print("STAGE 1: HybridRetriever.retrieve()")
        print(f"{'=' * 70}")

        retriever = HybridRetriever(
            db=db,
            analysis_id=analysis_id,
            enable_graph_expansion=True,
            graph_expansion_depth=2,
            graph_expansion_nodes_per_hop=3,
        )
        candidates = retriever.retrieve(
            question, top_k=5, expand_with_fact_store=False, enable_graph_expansion=True
        )
        print(f"[✓] Retrieved {len(candidates)} candidates\n")

        if len(candidates) == 0:
            print("[✗] STAGE 1 FAILED: No candidates retrieved!")
            print("    This means HybridRetriever couldn't find any auth-related entities.")
            return False

        for i, cand in enumerate(candidates[:10]):
            entity_name = (
                cand.get("entity_name")
                if isinstance(cand, dict)
                else getattr(cand, "entity_name", "?")
            )
            entity_type = (
                cand.get("entity_type")
                if isinstance(cand, dict)
                else getattr(cand, "entity_type", "?")
            )
            file_path = (
                cand.get("file_path")
                if isinstance(cand, dict)
                else getattr(cand, "file_path", "?")
            )
            print(f"  [{i}] {entity_name}")
            print(f"       Type: {entity_type}")
            print(f"       File: {file_path}")

        # ──────────────────────────────────────────────────────────────
        # STAGE 2: TargetEntityResolver
        # ──────────────────────────────────────────────────────────────
        print(f"\n{'=' * 70}")
        print("STAGE 2: TargetEntityResolver.resolve()")
        print(f"{'=' * 70}\n")

        resolver = TargetEntityResolver(db, analysis_id)
        seeds = []
        resolved_count = 0

        for i, cand in enumerate(candidates):
            entity_name = (
                cand.get("entity_name")
                if isinstance(cand, dict)
                else getattr(cand, "entity_name", None)
            )
            entity_type = (
                cand.get("entity_type")
                if isinstance(cand, dict)
                else getattr(cand, "entity_type", None)
            )

            if not entity_name:
                print(f"  [{i}] SKIP: No entity_name")
                continue

            target = resolver.resolve(entity_name, entity_type)
            if target:
                seeds.append((entity_name, target))
                target_type = type(target).__name__
                print(f"  [{i}] ✓ {entity_name} -> {target_type}")
                resolved_count += 1
            else:
                print(f"  [{i}] ✗ {entity_name} (type={entity_type}) - resolution failed")

        print(f"\n[✓] Resolved {resolved_count} / {len(candidates)} candidates")

        if len(seeds) == 0:
            print("[✗] STAGE 2 FAILED: No candidates could be resolved!")
            print("    This means entity names don't match FactStore entries.")
            return False

        # ──────────────────────────────────────────────────────────────
        # STAGE 3: FactStoreGraphTraverser
        # ──────────────────────────────────────────────────────────────
        print(f"\n{'=' * 70}")
        print("STAGE 3: FactStoreGraphTraverser.traverse()")
        print(f"{'=' * 70}\n")

        traverser = FactStoreGraphTraverser(db, analysis_id)
        total_relationships = 0
        total_traversals = 0

        for seed_name, target in seeds:
            # Determine what relationship types to traverse based on target type
            if isinstance(target, FactSymbol):
                query_classes = [
                    SemanticQueryClass.CALLS_FORWARD,
                    SemanticQueryClass.CALLS_REVERSE,
                    SemanticQueryClass.CONTAINMENT,
                ]
            elif isinstance(target, FactFile):
                query_classes = [
                    SemanticQueryClass.IMPORTS_FORWARD,
                    SemanticQueryClass.IMPORTS_REVERSE,
                    SemanticQueryClass.CONTAINMENT,
                ]
            elif isinstance(target, FactRoute):
                query_classes = [SemanticQueryClass.ROUTE_HANDLER]
            else:
                query_classes = []

            print(f"[Seed: {seed_name}] ({type(target).__name__})")

            for query_class in query_classes:
                direction = (
                    TraversalDirection.REVERSE
                    if "REVERSE" in query_class.name
                    else TraversalDirection.FORWARD
                )
                intent = SemanticQueryIntent(
                    query_class=query_class,
                    target_raw_name=seed_name,
                    direction=direction,
                    confidence=1.0,
                )

                try:
                    result = traverser.traverse(intent, target)
                    rel_count = len(result.related_entities)
                    total_traversals += 1
                    total_relationships += rel_count

                    status = "✓" if rel_count > 0 else "○"
                    print(f"  [{status}] {query_class.name:20s}: {rel_count} relationships")

                    if rel_count > 0:
                        for entity in result.related_entities[:3]:
                            entity_name_str = (
                                entity.name if hasattr(entity, "name") else "?"
                            )
                            location_str = (
                                entity.location if hasattr(entity, "location") else ""
                            )
                            print(f"       → {entity_name_str} ({location_str})")

                except Exception as e:
                    print(f"  [✗] {query_class.name:20s}: ERROR - {e}")

            print()

        print(
            f"\n[Summary] Traversals: {total_traversals}, "
            f"Total Relationships Found: {total_relationships}"
        )

        if total_relationships == 0:
            print("[✗] STAGE 3 WARNING: No relationships found!")
            print("    Graph traversal returned 0 edges. Check if analysis completed.")

        # ──────────────────────────────────────────────────────────────
        # STAGE 4: Full metadata block
        # ──────────────────────────────────────────────────────────────
        print(f"\n{'=' * 70}")
        print("STAGE 4: build_rim_metadata_block()")
        print(f"{'=' * 70}\n")

        metadata = build_rim_metadata_block(
            db,
            analysis_id,
            question,
            retriever,
            max_seed_entities=3,
            max_related_per_seed=8,
            max_block_chars=2000,
        )

        has_facts = metadata.text and "No structural" not in metadata.text
        status = "✓" if has_facts else "✗"
        print(f"[{status}] Metadata block generated")
        print(f"    Anchor entities: {len(metadata.anchor_entities)}")
        print(f"    Expanded entities: {len(metadata.expanded_entities)}")
        print(f"    Relationships: {len(metadata.relationships)}")
        print(f"    Relationship types: {metadata.relationship_types_used}")
        print(f"    Text length: {len(metadata.text)} chars")

        print(f"\n[RIM Metadata Text Preview]:")
        print("─" * 70)
        preview = metadata.text[:800]
        if len(metadata.text) > 800:
            preview += "\n... (truncated)"
        print(preview)
        print("─" * 70)

        # ──────────────────────────────────────────────────────────────
        # FINAL VERDICT
        # ──────────────────────────────────────────────────────────────
        print(f"\n{'=' * 70}")
        print("PHASE 2 VERDICT")
        print(f"{'=' * 70}\n")

        success = (
            len(candidates) > 0
            and len(seeds) > 0
            and total_relationships > 0
            and has_facts
        )

        if success:
            print("[✓] PHASE 2 PASSED")
            print(
                f"    RIM pipeline successfully retrieved {len(seeds)} seed entities"
            )
            print(f"    and {total_relationships} relationships.")
            print(f"    LLM has repository-specific facts to work with.")
        else:
            print("[✗] PHASE 2 FAILED")
            if len(candidates) == 0:
                print("    Issue: HybridRetriever found no candidates")
            elif len(seeds) == 0:
                print("    Issue: TargetEntityResolver couldn't resolve candidates")
            elif total_relationships == 0:
                print("    Issue: FactStoreGraphTraverser found no relationships")
            else:
                print("    Issue: Metadata block generation failed")

        return success

    finally:
        db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
