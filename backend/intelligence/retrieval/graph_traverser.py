"""
Fact Store Graph Traverser: Executes analysis-scoped deterministic relationship traversal
on FactRelationship, FactRoute, and FactDatabaseObject tables.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.models.fact_store import (
    FactFile,
    FactSymbol,
    FactRelationship,
    FactRoute,
    FactDatabaseObject,
)
from backend.agent.intent.semantic_query import (
    SemanticQueryIntent,
    SemanticQueryClass,
    TraversalDirection,
)
from backend.intelligence.retrieval.traversal_handlers import (
    traverse_containment,
    traverse_imports_forward,
    traverse_imports_reverse,
    traverse_calls_forward,
    traverse_calls_reverse,
    traverse_inherits_forward,
    traverse_inherits_reverse,
    traverse_route_handler,
    traverse_database_access,
    traverse_generic_lookup,
)

logger = logging.getLogger(__name__)


@dataclass
class TraversedEntity:
    name: str
    entity_type: str  # "file", "function", "class", "method", "module", "route", "table"
    location: Optional[str] = None
    line_number: Optional[int] = None
    relationship_role: str = ""  # e.g. "imported_module", "dependent_file", "callee", "caller", "base_class", "subclass", "handler", "accessing_code"
    data: Dict[str, Any] = field(default_factory=dict)
    path: Optional[List[str]] = None
    relationships: Optional[List[str]] = None


@dataclass
class RelationshipTraversalResult:
    query_class: SemanticQueryClass
    direction: TraversalDirection
    target_entity: Optional[Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]]
    target_display_name: str
    target_type: str
    related_entities: List[TraversedEntity] = field(default_factory=list)
    raw_edges: List[FactRelationship] = field(default_factory=list)
    explanation: str = ""
    resolution: str = "STATIC_CONFIRMED"


class FactStoreGraphTraverser:
    """
    Executes directed, analysis-scoped graph traversal on the canonical Fact Store.
    """

    def __init__(self, db: Session, analysis_id: int):
        self.db = db
        self.analysis_id = analysis_id

    def traverse(
        self,
        intent: SemanticQueryIntent,
        target: Optional[Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]]
    ) -> RelationshipTraversalResult:
        """
        Dispatches and executes the appropriate graph traversal based on query intent.
        """
        if not self.analysis_id:
            return RelationshipTraversalResult(
                query_class=intent.query_class,
                direction=intent.direction,
                target_entity=None,
                target_display_name=intent.target_raw_name,
                target_type="unknown",
                explanation="No active analysis provided.",
                resolution="ENTITY_NOT_FOUND",
            )

        if not target:
            return RelationshipTraversalResult(
                query_class=intent.query_class,
                direction=intent.direction,
                target_entity=None,
                target_display_name=intent.target_raw_name,
                target_type="unknown",
                explanation=f"Target '{intent.target_raw_name}' was not found in this repository index.",
                resolution="ENTITY_NOT_FOUND",
            )

        if intent.direction == TraversalDirection.BOTH:
            return self._traverse_both_directions(intent, target)

        # 1. CONTAINMENT
        if intent.query_class == SemanticQueryClass.CONTAINMENT:
            res = self._traverse_containment(target)
        # 2. IMPORTS_FORWARD
        elif intent.query_class == SemanticQueryClass.IMPORTS_FORWARD:
            res = self._traverse_imports_forward(target)
        # 3. IMPORTS_REVERSE
        elif intent.query_class == SemanticQueryClass.IMPORTS_REVERSE:
            res = self._traverse_imports_reverse(target)
        # 4. CALLS_FORWARD
        elif intent.query_class == SemanticQueryClass.CALLS_FORWARD:
            res = self._traverse_calls_forward(target)
        # 5. CALLS_REVERSE
        elif intent.query_class == SemanticQueryClass.CALLS_REVERSE:
            res = self._traverse_calls_reverse(target)
        # 6. INHERITS_FORWARD
        elif intent.query_class == SemanticQueryClass.INHERITS_FORWARD:
            res = self._traverse_inherits_forward(target)
        # 7. INHERITS_REVERSE
        elif intent.query_class == SemanticQueryClass.INHERITS_REVERSE:
            res = self._traverse_inherits_reverse(target)
        # 8. ROUTE_HANDLER
        elif intent.query_class == SemanticQueryClass.ROUTE_HANDLER:
            res = self._traverse_route_handler(target)
        # 9. DATABASE_ACCESS
        elif intent.query_class == SemanticQueryClass.DATABASE_ACCESS:
            res = self._traverse_database_access(target)
        # 10. GENERIC_LOOKUP
        else:
            res = self._traverse_generic_lookup(target)

        res.resolution = "STATIC_CONFIRMED" if res.related_entities else "NO_STATIC_EDGE_FOUND"
        return res

    # ──────────────────────────────────────────────────────────────────────────
    # INDIVIDUAL TRAVERSAL HANDLERS
    # ──────────────────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────────────────
    # INDIVIDUAL TRAVERSAL HANDLERS (Delegated to traversal_handlers)
    # ──────────────────────────────────────────────────────────────────────────

    def _traverse_containment(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_containment(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_imports_forward(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_imports_forward(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_imports_reverse(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_imports_reverse(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_calls_forward(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_calls_forward(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_calls_reverse(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_calls_reverse(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_inherits_forward(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_inherits_forward(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_inherits_reverse(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_inherits_reverse(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_route_handler(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_route_handler(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_database_access(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_database_access(self.db, self.analysis_id, target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_generic_lookup(
        self,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        return traverse_generic_lookup(target, TraversedEntity, RelationshipTraversalResult)

    def _traverse_both_directions(
        self,
        intent: SemanticQueryIntent,
        target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]
    ) -> RelationshipTraversalResult:
        """Execute both forward and reverse traversal and merge results."""
        fwd_class = intent.query_class
        rev_class = intent.query_class
        if intent.query_class in (SemanticQueryClass.CALLS_FORWARD, SemanticQueryClass.CALLS_REVERSE):
            fwd_class, rev_class = SemanticQueryClass.CALLS_FORWARD, SemanticQueryClass.CALLS_REVERSE
        elif intent.query_class in (SemanticQueryClass.IMPORTS_FORWARD, SemanticQueryClass.IMPORTS_REVERSE):
            fwd_class, rev_class = SemanticQueryClass.IMPORTS_FORWARD, SemanticQueryClass.IMPORTS_REVERSE
        elif intent.query_class in (SemanticQueryClass.INHERITS_FORWARD, SemanticQueryClass.INHERITS_REVERSE):
            fwd_class, rev_class = SemanticQueryClass.INHERITS_FORWARD, SemanticQueryClass.INHERITS_REVERSE

        fwd_intent = SemanticQueryIntent(
            query_class=fwd_class,
            target_raw_name=intent.target_raw_name,
            direction=TraversalDirection.FORWARD,
            confidence=intent.confidence,
        )
        rev_intent = SemanticQueryIntent(
            query_class=rev_class,
            target_raw_name=intent.target_raw_name,
            direction=TraversalDirection.REVERSE,
            confidence=intent.confidence,
        )

        res_fwd = self.traverse(fwd_intent, target)
        res_rev = self.traverse(rev_intent, target)

        merged_related: List[TraversedEntity] = list(res_fwd.related_entities)
        seen_keys = {
            (e.name, e.relationship_role, e.location)
            for e in merged_related
        }
        for e in res_rev.related_entities:
            key = (e.name, e.relationship_role, e.location)
            if key not in seen_keys:
                seen_keys.add(key)
                merged_related.append(e)

        merged_edges = list(res_fwd.raw_edges)
        edge_ids = {edge.id for edge in merged_edges}
        for edge in res_rev.raw_edges:
            if edge.id not in edge_ids:
                edge_ids.add(edge.id)
                merged_edges.append(edge)

        target_name = getattr(target, "name", getattr(target, "path", intent.target_raw_name))
        resolution = "STATIC_CONFIRMED" if merged_related else "NO_STATIC_EDGE_FOUND"
        explanation = f"Found {len(merged_related)} bidirectional relationships for '{target_name}' ({len(res_fwd.related_entities)} outgoing, {len(res_rev.related_entities)} incoming)."

        return RelationshipTraversalResult(
            query_class=intent.query_class,
            direction=TraversalDirection.BOTH,
            target_entity=target,
            target_display_name=target_name,
            target_type=res_fwd.target_type or res_rev.target_type,
            related_entities=merged_related,
            raw_edges=merged_edges,
            explanation=explanation,
            resolution=resolution,
        )

    def _map_type_direction_to_query_class(self, relationship_type: str, direction: str) -> SemanticQueryClass:
        rt = (relationship_type or "GENERIC").upper()
        d = (direction or "FORWARD").upper()
        if rt == "CALLS":
            return SemanticQueryClass.CALLS_FORWARD if d != "REVERSE" else SemanticQueryClass.CALLS_REVERSE
        elif rt == "IMPORTS":
            return SemanticQueryClass.IMPORTS_FORWARD if d != "REVERSE" else SemanticQueryClass.IMPORTS_REVERSE
        elif rt == "INHERITS":
            return SemanticQueryClass.INHERITS_FORWARD if d != "REVERSE" else SemanticQueryClass.INHERITS_REVERSE
        elif rt == "CONTAINS":
            return SemanticQueryClass.CONTAINMENT
        elif rt == "ROUTE_HANDLER":
            return SemanticQueryClass.ROUTE_HANDLER
        elif rt == "DATABASE_ACCESS":
            return SemanticQueryClass.DATABASE_ACCESS
        else:
            return SemanticQueryClass.GENERIC_LOOKUP

    def traverse_bounded(
        self,
        target: Optional[Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]],
        relationship_type: str = "GENERIC",
        direction: str = "FORWARD",
        scope: str = "LOCAL",
        depth: int = 1,
        limit: int = 15,
        target_raw_name: str = "",
    ) -> RelationshipTraversalResult:
        """
        Executes bounded, scope-aware graph traversal.
        - LOCAL: 1-hop direct relationships
        - NEIGHBORHOOD: Bounded multi-hop traversal (depth 1 to 3)
        - GLOBAL: Repository-wide relationship traversal (depth 1 to 3)
        """
        scope_norm = (scope or "LOCAL").upper()
        dir_norm = (direction or "FORWARD").upper()
        rel_type_norm = (relationship_type or "GENERIC").upper()

        if dir_norm not in ("FORWARD", "REVERSE", "BOTH"):
            dir_norm = "FORWARD"

        if scope_norm == "LOCAL":
            max_depth = 1
        else:
            max_depth = max(1, min(int(depth or 1), 3))

        max_limit = max(1, min(int(limit or 15), 50))

        if not target:
            return RelationshipTraversalResult(
                query_class=self._map_type_direction_to_query_class(rel_type_norm, dir_norm),
                direction=TraversalDirection(dir_norm),
                target_entity=None,
                target_display_name=target_raw_name,
                target_type="unknown",
                explanation=f"Target '{target_raw_name}' was not found in this repository index.",
                resolution="ENTITY_NOT_FOUND",
            )

        root_name = getattr(target, "name", getattr(target, "path", target_raw_name or "target"))

        if max_depth == 1:
            intent = SemanticQueryIntent(
                query_class=self._map_type_direction_to_query_class(rel_type_norm, dir_norm),
                target_raw_name=root_name,
                direction=TraversalDirection(dir_norm),
                confidence=1.0,
            )
            res = self.traverse(intent, target)
            for e in res.related_entities:
                if not e.path:
                    e.path = [root_name, e.name]
                if not e.relationships:
                    e.relationships = [rel_type_norm]
            res.related_entities = res.related_entities[:max_limit]
            res.resolution = "STATIC_CONFIRMED" if res.related_entities else "NO_STATIC_EDGE_FOUND"
            return res

        # Multi-hop BFS traversal (depth 2 or 3)
        queue: List[tuple] = [(target, [root_name], [], 0)]
        root_key = getattr(target, "id", root_name)
        visited_keys = {root_key}
        all_discovered: List[TraversedEntity] = []
        all_edges: List[FactRelationship] = []

        while queue and len(all_discovered) < max_limit:
            curr_target, curr_path, curr_rels, curr_d = queue.pop(0)
            if curr_d >= max_depth:
                continue

            step_intent = SemanticQueryIntent(
                query_class=self._map_type_direction_to_query_class(rel_type_norm, dir_norm),
                target_raw_name=getattr(curr_target, "name", getattr(curr_target, "path", "")),
                direction=TraversalDirection(dir_norm),
                confidence=1.0,
            )
            step_res = self.traverse(step_intent, curr_target)
            all_edges.extend(step_res.raw_edges)

            for ent in step_res.related_entities:
                ent_key = ent.data.get("symbol_id") or ent.data.get("file_id") or ent.name
                if ent.name in curr_path:
                    continue  # Prevent cycle

                child_path = curr_path + [ent.name]
                child_rels = curr_rels + [rel_type_norm]
                ent.path = child_path
                ent.relationships = child_rels
                all_discovered.append(ent)

                if len(all_discovered) >= max_limit:
                    break

                if curr_d + 1 < max_depth and ent_key not in visited_keys:
                    visited_keys.add(ent_key)
                    next_node = None
                    if ent.data.get("symbol_id"):
                        next_node = self.db.query(FactSymbol).filter(
                            FactSymbol.analysis_id == self.analysis_id,
                            FactSymbol.id == ent.data["symbol_id"]
                        ).first()
                    elif ent.data.get("file_id"):
                        next_node = self.db.query(FactFile).filter(
                            FactFile.analysis_id == self.analysis_id,
                            FactFile.id == ent.data["file_id"]
                        ).first()
                    else:
                        next_node = self.db.query(FactSymbol).filter(
                            FactSymbol.analysis_id == self.analysis_id,
                            FactSymbol.name == ent.name
                        ).first()
                    if next_node:
                        queue.append((next_node, child_path, child_rels, curr_d + 1))

        resolution = "STATIC_CONFIRMED" if all_discovered else "NO_STATIC_EDGE_FOUND"
        explanation = (
            f"Discovered {len(all_discovered)} entities across {max_depth}-hop {scope_norm} traversal "
            f"for '{root_name}' ({rel_type_norm}, {dir_norm})."
        )
        return RelationshipTraversalResult(
            query_class=self._map_type_direction_to_query_class(rel_type_norm, dir_norm),
            direction=TraversalDirection(dir_norm),
            target_entity=target,
            target_display_name=root_name,
            target_type=getattr(target, "symbol_type", "file" if isinstance(target, FactFile) else "entity"),
            related_entities=all_discovered,
            raw_edges=all_edges,
            explanation=explanation,
            resolution=resolution,
        )
