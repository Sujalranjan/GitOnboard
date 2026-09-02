"""
RIM Metadata Block Assembly: builds the upfront repository facts block.

Called once per comparison (RIM side only), before the loop starts.
Uses HybridRetriever for seed identification only (no candidate injection),
then FactStoreGraphTraverser for one-hop traversal to build a facts block.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from backend.agent.intent.semantic_query import SemanticQueryClass, TraversalDirection, SemanticQueryIntent
from backend.models.fact_store import FactSymbol, FactFile, FactRoute, FactDatabaseObject

logger = logging.getLogger(__name__)


@dataclass
class RimMetadataBlock:
    """Assembled RIM metadata block for one comparison side."""
    text: str  # Plain text facts to inject into system prompt
    seed_entities: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    relationship_types_used: List[str] = field(default_factory=list)


class TargetEntityResolver:
    """Resolve entity names to ORM objects."""

    def __init__(self, db, analysis_id: int):
        self.db = db
        self.analysis_id = analysis_id

    def resolve(self, entity_name: str) -> Optional[Any]:
        """Resolve entity name to FactSymbol/FactFile/FactRoute/FactDatabaseObject."""
        # Try FactSymbol
        symbol = self.db.query(FactSymbol).filter(
            FactSymbol.analysis_id == self.analysis_id,
            FactSymbol.name.ilike(entity_name),
        ).first()
        if symbol:
            return symbol

        # Try FactFile
        file = self.db.query(FactFile).filter(
            FactFile.analysis_id == self.analysis_id,
            FactFile.path.ilike(f"%{entity_name}%"),
        ).first()
        if file:
            return file

        # Try FactRoute
        route = self.db.query(FactRoute).filter(
            FactRoute.analysis_id == self.analysis_id,
            FactRoute.path.ilike(f"%{entity_name}%"),
        ).first()
        if route:
            return route

        # Try FactDatabaseObject
        db_obj = self.db.query(FactDatabaseObject).filter(
            FactDatabaseObject.analysis_id == self.analysis_id,
            FactDatabaseObject.name.ilike(entity_name),
        ).first()
        if db_obj:
            return db_obj

        return None


def build_rim_metadata_block(
    db,
    analysis_id: int,
    question: str,
    retriever: HybridRetriever,
    max_seed_entities: int = 3,
    max_related_per_seed: int = 8,
    max_block_chars: int = 4000,
) -> RimMetadataBlock:
    """
    Build RIM metadata block from question and repository graph.

    Algorithm:
    1. Use HybridRetriever (lexical+semantic, NO expansion) to identify seed entities
    2. Resolve seeds to ORM objects
    3. Traverse a fixed set of one-hop relationships per seed type
    4. Render facts as plain text lines, cap by character count

    Args:
        db: SQLAlchemy session
        analysis_id: Analysis ID from database
        question: User question (used for seed identification)
        retriever: HybridRetriever instance (lexical/semantic search, no expansion)
        max_seed_entities: Maximum seeds to traverse (3)
        max_related_per_seed: Cap on related entities per traversal (8)
        max_block_chars: Maximum character length of output text (4000)

    Returns:
        RimMetadataBlock with text, seeds, relationships, relationship_types_used
    """
    logger.info(f"[RIM Metadata] Building metadata block for: {question}")

    block = RimMetadataBlock(text="")
    resolver = TargetEntityResolver(db, analysis_id)
    traverser = FactStoreGraphTraverser(db, analysis_id)

    # 1. Seed identification (HybridRetriever, NO expansion)
    try:
        candidates = retriever.retrieve(question, top_k=5, expand_with_fact_store=False)
        logger.debug(f"[RIM Metadata] Retrieved {len(candidates)} seed candidates")
    except Exception as e:
        logger.warning(f"[RIM Metadata] Seed retrieval failed: {e}")
        candidates = []

    if not candidates:
        block.text = "RIM_METADATA: No structural facts could be resolved for this question in this repository's index."
        logger.info("[RIM Metadata] No seeds resolved; returning empty block")
        return block

    # 2. Resolve seeds to ORM objects
    seeds = []
    for cand in candidates[:max_seed_entities]:
        # Extract entity name from candidate
        entity_name = cand.get("entity_name") or cand.get("symbol") or cand.get("path") or ""
        if not entity_name:
            continue

        target = resolver.resolve(entity_name)
        if target:
            seeds.append((entity_name, target, cand))
            logger.debug(f"[RIM Metadata] Resolved seed: {entity_name} -> {type(target).__name__}")

    if not seeds:
        block.text = "RIM_METADATA: No structural facts could be resolved for this question in this repository's index."
        logger.info("[RIM Metadata] Seeds could not be resolved")
        return block

    # 3. Traverse one-hop relationships per seed
    facts_lines = []
    seen_rel_types = set()

    for seed_name, target, _ in seeds:
        logger.debug(f"[RIM Metadata] Traversing seed: {seed_name}")

        # Determine which relationship classes to traverse based on target type
        query_classes_to_traverse = []

        if isinstance(target, FactSymbol):
            # For symbols: CONTAINMENT, CALLS_FORWARD, CALLS_REVERSE, INHERITS_FORWARD, INHERITS_REVERSE
            query_classes_to_traverse = [
                SemanticQueryClass.CONTAINMENT,
                SemanticQueryClass.CALLS_FORWARD,
                SemanticQueryClass.CALLS_REVERSE,
                SemanticQueryClass.INHERITS_FORWARD,
                SemanticQueryClass.INHERITS_REVERSE,
            ]
        elif isinstance(target, FactFile):
            # For files: CONTAINMENT, IMPORTS_FORWARD, IMPORTS_REVERSE
            query_classes_to_traverse = [
                SemanticQueryClass.CONTAINMENT,
                SemanticQueryClass.IMPORTS_FORWARD,
                SemanticQueryClass.IMPORTS_REVERSE,
            ]
        elif isinstance(target, FactRoute):
            # For routes: ROUTE_HANDLER
            query_classes_to_traverse = [
                SemanticQueryClass.ROUTE_HANDLER,
            ]
        elif isinstance(target, FactDatabaseObject):
            # For database objects: DATABASE_ACCESS
            query_classes_to_traverse = [
                SemanticQueryClass.DATABASE_ACCESS,
            ]

        for query_class in query_classes_to_traverse:
            # Determine direction
            if query_class in (SemanticQueryClass.CALLS_REVERSE, SemanticQueryClass.IMPORTS_REVERSE,
                              SemanticQueryClass.INHERITS_REVERSE):
                direction = TraversalDirection.REVERSE
            else:
                direction = TraversalDirection.FORWARD

            intent = SemanticQueryIntent(
                query_class=query_class,
                target_raw_name=seed_name,
                direction=direction,
                confidence=1.0,
            )

            try:
                result = traverser.traverse(intent, target)
            except Exception as e:
                logger.warning(f"[RIM Metadata] Traversal failed for {seed_name} / {query_class}: {e}")
                continue

            # Add related entities as fact lines
            related_count = 0
            for entity in result.related_entities[:max_related_per_seed]:
                if related_count >= max_related_per_seed:
                    break

                # Render fact line
                line = self._render_fact_line(seed_name, result.query_class, entity)
                if line:
                    facts_lines.append(line)
                    related_count += 1

                    # Track relationship types used
                    rel_type_str = self._query_class_to_rel_type(result.query_class)
                    if rel_type_str not in seen_rel_types:
                        seen_rel_types.add(rel_type_str)

            # If traversal returned nothing, emit explicit "not found" line
            if not result.related_entities:
                explanation = result.explanation or "No relationships found"
                if "No" in explanation or "not" in explanation.lower():
                    fact_line = f"  {seed_name}: {explanation}"
                    facts_lines.append(fact_line)

    # 4. Cap by character count
    current_text = "\n".join(facts_lines)
    if len(current_text) > max_block_chars:
        current_text = current_text[:max_block_chars]
        current_text = current_text.rsplit("\n", 1)[0]  # Remove partial line
        current_text += f"\n  ... (more relationships available, use query_rim to explore further)"

    # 5. Build final text with header
    if facts_lines:
        block.text = current_text
    else:
        block.text = "RIM_METADATA: No structural facts could be resolved for this question in this repository's index."

    block.relationship_types_used = sorted(list(seen_rel_types))

    logger.info(
        f"[RIM Metadata] Block built: {len(facts_lines)} fact lines, "
        f"types={block.relationship_types_used}, "
        f"chars={len(block.text)}"
    )
    return block


def _render_fact_line(seed_name: str, query_class: SemanticQueryClass, entity: Any) -> str:
    """Render a single relationship fact as a plain text line."""
    entity_name = entity.name if hasattr(entity, "name") else entity.get("name", "")
    entity_type = entity.entity_type if hasattr(entity, "entity_type") else entity.get("entity_type", "")
    location = entity.location if hasattr(entity, "location") else entity.get("location", "")
    line_no = entity.line_number if hasattr(entity, "line_number") else entity.get("line_number", "")

    # Map query class to relationship verb
    if query_class == SemanticQueryClass.CALLS_FORWARD:
        verb = "CALLS"
    elif query_class == SemanticQueryClass.CALLS_REVERSE:
        verb = "CALLED_BY"
    elif query_class == SemanticQueryClass.IMPORTS_FORWARD:
        verb = "IMPORTS"
    elif query_class == SemanticQueryClass.IMPORTS_REVERSE:
        verb = "IMPORTED_BY"
    elif query_class == SemanticQueryClass.INHERITS_FORWARD:
        verb = "INHERITS_FROM"
    elif query_class == SemanticQueryClass.INHERITS_REVERSE:
        verb = "EXTENDED_BY"
    elif query_class == SemanticQueryClass.CONTAINMENT:
        verb = "CONTAINS"
    elif query_class == SemanticQueryClass.ROUTE_HANDLER:
        verb = "HANDLED_BY"
    elif query_class == SemanticQueryClass.DATABASE_ACCESS:
        verb = "ACCESSED_BY"
    else:
        verb = "RELATES_TO"

    # Build location part
    location_part = ""
    if location:
        if line_no:
            location_part = f" ({location}:{line_no})"
        else:
            location_part = f" ({location})"

    return f"  {seed_name} {verb} {entity_name}{location_part}"


def _query_class_to_rel_type(query_class: SemanticQueryClass) -> str:
    """Map SemanticQueryClass to relationship type string."""
    if query_class == SemanticQueryClass.CALLS_FORWARD or query_class == SemanticQueryClass.CALLS_REVERSE:
        return "CALLS"
    elif query_class == SemanticQueryClass.IMPORTS_FORWARD or query_class == SemanticQueryClass.IMPORTS_REVERSE:
        return "IMPORTS"
    elif query_class == SemanticQueryClass.INHERITS_FORWARD or query_class == SemanticQueryClass.INHERITS_REVERSE:
        return "INHERITS"
    elif query_class == SemanticQueryClass.CONTAINMENT:
        return "CONTAINS"
    elif query_class == SemanticQueryClass.ROUTE_HANDLER:
        return "ROUTE_HANDLER"
    elif query_class == SemanticQueryClass.DATABASE_ACCESS:
        return "DATABASE_ACCESS"
    else:
        return "GENERIC"


# Bind functions to module for imports
def build_rim_metadata_block(
    db,
    analysis_id: int,
    question: str,
    retriever: HybridRetriever,
    max_seed_entities: int = 3,
    max_related_per_seed: int = 8,
    max_block_chars: int = 4000,
) -> RimMetadataBlock:
    """Build RIM metadata block from question and repository graph."""
    return _build_rim_metadata_block_impl(db, analysis_id, question, retriever, max_seed_entities, max_related_per_seed, max_block_chars)


def _build_rim_metadata_block_impl(
    db,
    analysis_id: int,
    question: str,
    retriever: HybridRetriever,
    max_seed_entities: int = 3,
    max_related_per_seed: int = 8,
    max_block_chars: int = 4000,
) -> RimMetadataBlock:
    """Implementation of build_rim_metadata_block (same function, avoiding name collision)."""
    logger.info(f"[RIM Metadata] Building metadata block for: {question}")

    block = RimMetadataBlock(text="")
    resolver = TargetEntityResolver(db, analysis_id)
    traverser = FactStoreGraphTraverser(db, analysis_id)

    # 1. Seed identification (HybridRetriever, NO expansion)
    try:
        candidates = retriever.retrieve(question, top_k=5, expand_with_fact_store=False)
        logger.debug(f"[RIM Metadata] Retrieved {len(candidates)} seed candidates")
    except Exception as e:
        logger.warning(f"[RIM Metadata] Seed retrieval failed: {e}")
        candidates = []

    if not candidates:
        block.text = "RIM_METADATA: No structural facts could be resolved for this question in this repository's index."
        logger.info("[RIM Metadata] No seeds resolved; returning empty block")
        return block

    # 2. Resolve seeds to ORM objects
    seeds = []
    for cand in candidates[:max_seed_entities]:
        entity_name = cand.get("entity_name") or cand.get("symbol") or cand.get("path") or ""
        if not entity_name:
            continue

        target = resolver.resolve(entity_name)
        if target:
            seeds.append((entity_name, target, cand))
            logger.debug(f"[RIM Metadata] Resolved seed: {entity_name} -> {type(target).__name__}")

    if not seeds:
        block.text = "RIM_METADATA: No structural facts could be resolved for this question in this repository's index."
        logger.info("[RIM Metadata] Seeds could not be resolved")
        return block

    # 3. Traverse one-hop relationships per seed
    facts_lines = []
    seen_rel_types = set()

    for seed_name, target, _ in seeds:
        logger.debug(f"[RIM Metadata] Traversing seed: {seed_name}")

        query_classes_to_traverse = []

        if isinstance(target, FactSymbol):
            query_classes_to_traverse = [
                SemanticQueryClass.CONTAINMENT,
                SemanticQueryClass.CALLS_FORWARD,
                SemanticQueryClass.CALLS_REVERSE,
                SemanticQueryClass.INHERITS_FORWARD,
                SemanticQueryClass.INHERITS_REVERSE,
            ]
        elif isinstance(target, FactFile):
            query_classes_to_traverse = [
                SemanticQueryClass.CONTAINMENT,
                SemanticQueryClass.IMPORTS_FORWARD,
                SemanticQueryClass.IMPORTS_REVERSE,
            ]
        elif isinstance(target, FactRoute):
            query_classes_to_traverse = [
                SemanticQueryClass.ROUTE_HANDLER,
            ]
        elif isinstance(target, FactDatabaseObject):
            query_classes_to_traverse = [
                SemanticQueryClass.DATABASE_ACCESS,
            ]

        for query_class in query_classes_to_traverse:
            if query_class in (SemanticQueryClass.CALLS_REVERSE, SemanticQueryClass.IMPORTS_REVERSE,
                              SemanticQueryClass.INHERITS_REVERSE):
                direction = TraversalDirection.REVERSE
            else:
                direction = TraversalDirection.FORWARD

            intent = SemanticQueryIntent(
                query_class=query_class,
                target_raw_name=seed_name,
                direction=direction,
                confidence=1.0,
            )

            try:
                result = traverser.traverse(intent, target)
            except Exception as e:
                logger.warning(f"[RIM Metadata] Traversal failed for {seed_name} / {query_class}: {e}")
                continue

            related_count = 0
            for entity in result.related_entities[:max_related_per_seed]:
                if related_count >= max_related_per_seed:
                    break

                line = _render_fact_line(seed_name, result.query_class, entity)
                if line:
                    facts_lines.append(line)
                    related_count += 1

                    rel_type_str = _query_class_to_rel_type(result.query_class)
                    if rel_type_str not in seen_rel_types:
                        seen_rel_types.add(rel_type_str)

            if not result.related_entities:
                explanation = result.explanation or "No relationships found"
                if "No" in explanation or "not" in explanation.lower():
                    fact_line = f"  {seed_name}: {explanation}"
                    facts_lines.append(fact_line)

    # 4. Cap by character count
    current_text = "\n".join(facts_lines)
    if len(current_text) > max_block_chars:
        current_text = current_text[:max_block_chars]
        current_text = current_text.rsplit("\n", 1)[0]
        current_text += f"\n  ... (more relationships available, use query_rim to explore further)"

    # 5. Build final text with header
    if facts_lines:
        block.text = current_text
    else:
        block.text = "RIM_METADATA: No structural facts could be resolved for this question in this repository's index."

    block.relationship_types_used = sorted(list(seen_rel_types))

    logger.info(
        f"[RIM Metadata] Block built: {len(facts_lines)} fact lines, "
        f"types={block.relationship_types_used}, "
        f"chars={len(block.text)}"
    )
    return block
