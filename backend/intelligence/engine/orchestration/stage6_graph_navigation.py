"""
Stage 6: Bounded Graph Navigation

Traverses repository model relationships starting from Stage 5 retrieval results.
Uses existing QueryLayer bidirectional APIs with strict depth and breadth limits.
"""
import logging
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import deque

from backend.intelligence.retrieval.schema import RetrieverResult
from backend.intelligence.query_layer import QueryLayer
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity

logger = logging.getLogger(__name__)


@dataclass
class GraphNavigationResult:
    """Output from Stage 6 graph traversal."""
    seed_entities: List[RetrieverResult]
    discovered_entities: Dict[str, Entity] = field(default_factory=dict)
    traversal_edges: List[Dict[str, str]] = field(default_factory=list)
    traversal_depth: int = 0
    entity_count: int = 0
    edge_count: int = 0
    traversal_time: float = 0.0
    validation_errors: List[str] = field(default_factory=list)


class GraphNavigator:
    """
    Performs bounded BFS traversal from retrieval result anchors.

    Constraints:
    - max_depth: 3 hops from seed
    - max_breadth: limit edges per entity to prevent explosion
    - deduplication: track visited nodes
    - validation: verify entities/files exist
    """

    def __init__(
        self,
        model: RepositoryModel,
        max_depth: int = 3,
        max_edges_per_entity: int = 5,
    ):
        self.model = model
        self.query_layer = QueryLayer(model)
        self.max_depth = max_depth
        self.max_edges_per_entity = max_edges_per_entity

    def navigate(
        self,
        retrieval_results: List[RetrieverResult],
        max_entities: Optional[int] = None,
    ) -> GraphNavigationResult:
        """
        Execute bounded BFS traversal from retrieval result anchors.

        Args:
            retrieval_results: Seed entities from Stage 5
            max_entities: Hard limit on discovered entities (safety)

        Returns:
            GraphNavigationResult with discovered entities and edges
        """
        import time
        start_time = time.time()

        result = GraphNavigationResult(seed_entities=retrieval_results)

        if not retrieval_results:
            logger.warning("[Stage 6] No retrieval results to navigate from")
            result.traversal_time = time.time() - start_time
            return result

        # Map RetrieverResult IDs to entity IDs (exact match preferred)
        seed_entity_ids: Set[str] = set()
        for ret_result in retrieval_results:
            entity_id = None

            # Strategy 1: Try direct ID lookup first
            if ret_result.id in self.model.entities:
                entity_id = ret_result.id

            # Strategy 2: Try with analysis_id prefix (if ID comes from retriever without prefix)
            if entity_id is None:
                # Check if metadata contains symbol_id with prefix
                symbol_id = ret_result.metadata.get("symbol_id") if ret_result.metadata else None
                if symbol_id and symbol_id in self.model.entities:
                    entity_id = symbol_id

            # Strategy 3: Try extracting bare ID from symbol_id and matching
            if entity_id is None and ret_result.metadata:
                symbol_id = ret_result.metadata.get("symbol_id")
                if symbol_id and ":" in symbol_id:
                    # symbol_id format: "847126:urn:type:path#qualified_name"
                    # Extract just the "urn:..." part
                    bare_id = ":".join(symbol_id.split(":")[1:])
                    if bare_id in self.model.entities:
                        entity_id = bare_id

            # Strategy 4: Fuzzy match by name (fallback)
            if entity_id is None and ret_result.entity_name:
                if "FUNCTION" in str(ret_result.entity_type).upper():
                    funcs = self.query_layer.find_function(ret_result.entity_name)
                    if funcs:
                        entity_id = funcs[0].id
                elif "CLASS" in str(ret_result.entity_type).upper():
                    classes = self.query_layer.get_class(ret_result.entity_name)
                    if classes:
                        entity_id = classes[0].id

            # Add to seed set if found via any strategy
            if entity_id:
                seed_entity_ids.add(entity_id)
            else:
                result.validation_errors.append(
                    f"Seed entity not found: {ret_result.entity_name} (id={ret_result.id})"
                )

        if not seed_entity_ids:
            logger.warning("[Stage 6] No valid seed entities from retrieval results")
            result.traversal_time = time.time() - start_time
            return result

        logger.info(f"[Stage 6] Starting traversal from {len(seed_entity_ids)} seed entities")

        # BFS with depth tracking
        visited: Set[str] = set()
        queue: deque[Tuple[str, int]] = deque()  # (entity_id, depth)

        # Initialize with seeds at depth 0
        for seed_id in seed_entity_ids:
            if seed_id in self.model.entities:
                queue.append((seed_id, 0))
                visited.add(seed_id)
                result.discovered_entities[seed_id] = self.model.entities[seed_id]

        max_safe_entities = max_entities or 100  # Safety limit

        # BFS traversal
        while queue and len(visited) < max_safe_entities:
            entity_id, depth = queue.popleft()

            if depth >= self.max_depth:
                continue

            entity = self.model.entities.get(entity_id)
            if not entity:
                continue

            # Get related entities (forward and reverse)
            related_ids: List[str] = []

            # Use QueryLayer bidirectional APIs
            try:
                related_ids.extend(self.query_layer.get_calls(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_called_by(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_imports(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_imported_by(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_dependencies(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_depended_by(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_uses(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_used_by(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_inherits(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_extended_by(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_implements(entity_id)[:self.max_edges_per_entity])
                related_ids.extend(self.query_layer.get_implementers(entity_id)[:self.max_edges_per_entity])
            except Exception as e:
                logger.warning(f"[Stage 6] Error querying relationships for {entity_id}: {e}")
                continue

            # Deduplicate and filter
            related_ids = list(set(related_ids))

            # Record edges and enqueue new entities
            for related_id in related_ids:
                if related_id and related_id in self.model.entities:
                    # Record edge with relationship type (infer from method calls)
                    edge = {
                        "source_id": entity_id,
                        "target_id": related_id,
                        "depth": depth + 1,
                    }
                    result.traversal_edges.append(edge)

                    # Enqueue if not visited
                    if related_id not in visited and len(visited) < max_safe_entities:
                        visited.add(related_id)
                        queue.append((related_id, depth + 1))
                        result.discovered_entities[related_id] = self.model.entities[related_id]
                        result.traversal_depth = max(result.traversal_depth, depth + 1)

        # Validation: ensure discovered entities/files exist
        for entity_id, entity in result.discovered_entities.items():
            if not entity:
                result.validation_errors.append(f"Discovered entity is null: {entity_id}")
            elif not entity.location or not entity.location.repository_path:
                result.validation_errors.append(f"Entity has no file path: {entity_id}")

        result.entity_count = len(result.discovered_entities)
        result.edge_count = len(result.traversal_edges)
        result.traversal_time = time.time() - start_time

        logger.info(
            f"[Stage 6] Traversal complete: {result.entity_count} entities, "
            f"{result.edge_count} edges, depth {result.traversal_depth}, "
            f"time {result.traversal_time:.2f}s"
        )

        return result
