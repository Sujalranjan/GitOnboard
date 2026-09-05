"""
Bounded Graph Expander: Produces connected RIM subgraphs from anchor nodes.

Provides multi-hop graph traversal with strict bounds on depth and node count to prevent
context explosion while capturing meaningful relationship context.
"""
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Set, Tuple
from sqlalchemy.orm import Session

from backend.models.fact_store import (
    FactSymbol,
    FactFile,
    FactRelationship,
)

logger = logging.getLogger(__name__)


@dataclass
class ExpandedNode:
    """Represents an expanded node with provenance and relationship context."""
    id: str
    symbol_id: str
    name: str
    type: str
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    qualified_name: Optional[str] = None
    relationship_role: str = ""  # e.g., "callee", "caller", "imported_module", etc.
    rel_type: str = ""  # CALLS, IMPORTS, CONTAINS, etc.
    distance_from_anchor: int = 0  # 0 for anchor, 1 for direct connection, etc.
    anchor_name: str = ""  # Name of anchor that led to this node
    data: Dict[str, Any] = None


class BoundedGraphExpander:
    """
    Expands anchor nodes via bounded graph traversal using FactStoreGraphTraverser.

    Produces connected RIM subgraphs instead of isolated symbols by:
    1. Taking anchor nodes from retrieval
    2. Performing bounded multi-hop traversal
    3. Respecting depth and node count limits
    4. Deduplicating expanded nodes
    5. Preserving anchor node provenance and relationship context
    """

    def __init__(
        self,
        db: Session,
        analysis_id: int,
        max_depth: int = 2,
        max_nodes_per_hop: int = 3,
        max_total_nodes: int = 30,
    ):
        """
        Args:
            db: SQLAlchemy session
            analysis_id: Analysis ID to scope traversal
            max_depth: Maximum hops from anchor node
            max_nodes_per_hop: Maximum nodes to explore at each hop level
            max_total_nodes: Hard limit on total expanded nodes
        """
        self.db = db
        self.analysis_id = analysis_id
        self.max_depth = max_depth
        self.max_nodes_per_hop = max_nodes_per_hop
        self.max_total_nodes = max_total_nodes

    def expand_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Expands retrieval candidates via bounded graph traversal.

        Resolves Files and Directories to contained Symbols for graph traversal,
        while preserving original retrieval results.

        Args:
            candidates: Initial retrieval results (anchor nodes)

        Returns:
            Enriched results with expanded nodes and relationship context
        """
        if not candidates or not self.analysis_id:
            return candidates

        # Keep anchors separate with provenance
        anchor_nodes: Dict[str, Dict[str, Any]] = {}
        expanded_nodes: Dict[str, ExpandedNode] = {}
        seen_ids: Set[str] = set()

        logger.info(
            f"[GraphExpand] Starting expansion of {len(candidates)} anchor nodes "
            f"(analysis_id={self.analysis_id}, max_depth={self.max_depth}, max_nodes_per_hop={self.max_nodes_per_hop})"
        )

        # Log candidate types for debugging
        candidate_types = {}
        for cand in candidates:
            ctype = cand.get("entity_type") or cand.get("type", "unknown")
            candidate_types[ctype] = candidate_types.get(ctype, 0) + 1

        logger.info(f"[GraphExpand] Candidate types: {candidate_types}")

        # Step 1: Process anchors and resolve to symbols
        for cand in candidates:
            anchor_node = self._process_anchor(cand)
            if anchor_node:
                anchor_nodes[anchor_node.get("symbol_id") or anchor_node.get("id")] = anchor_node
                sym_id = anchor_node.get("symbol_id") or anchor_node.get("id")
                if sym_id:
                    seen_ids.add(sym_id)

        logger.info(
            f"[GraphExpand] Processed {len(anchor_nodes)} anchor nodes from {len(candidates)} candidates"
        )

        # Step 2: Expand from each anchor with bounded BFS
        for anchor_id, anchor_dict in anchor_nodes.items():
            if len(expanded_nodes) >= self.max_total_nodes:
                logger.info(
                    f"[GraphExpand] Reached max_total_nodes limit ({self.max_total_nodes})"
                )
                break

            self._expand_from_anchor(
                anchor_id, anchor_dict, expanded_nodes, seen_ids
            )

        # Step 3: Convert anchors to output format
        results = []
        for anchor_id, anchor_dict in anchor_nodes.items():
            results.append(anchor_dict)

        # Step 4: Add expanded nodes to results
        for expanded_id, expanded_node in list(expanded_nodes.items())[: self.max_total_nodes - len(anchor_nodes)]:
            results.append(self._expanded_node_to_dict(expanded_node))

        logger.info(
            f"[GraphExpand] Expansion complete: {len(anchor_nodes)} anchors + "
            f"{len(list(expanded_nodes.items())[:self.max_total_nodes - len(anchor_nodes)])} expanded = {len(results)} total"
        )

        return results

    def _resolve_graph_anchors(self, candidate: Dict[str, Any]) -> List[FactSymbol]:
        """
        Resolve a retrieval candidate to graph-compatible FactSymbol anchors.

        Handles:
        - Direct Symbol candidates → return as-is
        - File candidates → extract contained symbols
        - Directory candidates → extract symbols from files in directory (limited)
        - External candidates → return empty (no graph anchor)

        Returns list of FactSymbols that can be used for graph traversal.
        """
        candidate_type = (candidate.get("entity_type") or candidate.get("type", "")).upper()
        candidate_id = candidate.get("id") or candidate.get("symbol_id")

        # Case A: Direct Symbol candidate
        if "SYMBOL" in candidate_type or "FUNCTION" in candidate_type or "CLASS" in candidate_type or "METHOD" in candidate_type:
            if candidate.get("symbol_id"):
                sym = self.db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.id == candidate.get("symbol_id")
                ).first()
                if sym:
                    return [sym]
            elif candidate_id and ":" in str(candidate_id):
                sym = self.db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.id == candidate_id
                ).first()
                if sym:
                    return [sym]
            return []

        # Case B: File candidate → extract contained symbols
        if "FILE" in candidate_type:
            file_path = candidate.get("file_path")
            if file_path:
                file_obj = self.db.query(FactFile).filter(
                    FactFile.analysis_id == self.analysis_id,
                    FactFile.path == file_path
                ).first()
                if file_obj:
                    if file_obj.symbols:
                        logger.debug(
                            f"[GraphExpand] File '{file_path}' contains {len(file_obj.symbols)} symbols"
                        )
                        # Return all symbols in the file (limited by max_nodes_per_hop during expansion)
                        return file_obj.symbols[:self.max_nodes_per_hop]
                    else:
                        logger.debug(f"[GraphExpand] File '{file_path}' has no symbols")
                else:
                    logger.debug(
                        f"[GraphExpand] File '{file_path}' not found in analysis {self.analysis_id}"
                    )
            return []

        # Case C: Directory candidate → limit expansion
        if "DIRECTORY" in candidate_type:
            directory_path = candidate.get("file_path")
            if directory_path:
                # Get files in this directory (not recursive)
                files = self.db.query(FactFile).filter(
                    FactFile.analysis_id == self.analysis_id,
                    FactFile.path.like(f"{directory_path}/%"),
                    ~FactFile.path.like(f"{directory_path}/%/%")  # Not recursive
                ).limit(3).all()  # Limit to 3 files

                symbols = []
                for file_obj in files:
                    if file_obj.symbols:
                        symbols.extend(file_obj.symbols[:2])  # Max 2 symbols per file
                        if len(symbols) >= self.max_nodes_per_hop:
                            break
                return symbols[:self.max_nodes_per_hop]
            return []

        # Case D: External or other types → no graph anchor
        return []

    def _process_anchor(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process and resolve an anchor node to a FactSymbol.

        Uses the new graph anchor resolution to handle Files, Directories, etc.
        Preserves original retrieval metadata.
        """
        cand_id = candidate.get("id") or candidate.get("symbol_id")
        cand_name = candidate.get("name") or candidate.get("match_name")
        cand_file = candidate.get("file_path")
        symbol_id = candidate.get("symbol_id")

        # Try to resolve symbol
        sym_rec = None
        resolution_method = None

        # Strategy 1: Use pre-resolved symbol_id
        if symbol_id:
            sym_rec = self.db.query(FactSymbol).filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.id == symbol_id
            ).first()
            if sym_rec:
                resolution_method = "symbol_id_field"

        # Strategy 2: Query by full ID
        if not sym_rec and cand_id and ":" in str(cand_id):
            sym_rec = self.db.query(FactSymbol).filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.id == cand_id
            ).first()
            if sym_rec:
                resolution_method = "full_id"

        # Strategy 3: Query by name and file path
        if not sym_rec and cand_name and cand_file:
            sym_rec = self.db.query(FactSymbol).join(FactFile).filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.name == cand_name,
                FactFile.path == cand_file
            ).first()
            if sym_rec:
                resolution_method = "name_file_match"

        # Strategy 4: Query by name only
        if not sym_rec and cand_name:
            sym_rec = self.db.query(FactSymbol).filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.name == cand_name
            ).first()
            if sym_rec:
                resolution_method = "name_only"

        if not sym_rec:
            # Try the new anchor resolution for Files, Directories, etc.
            graph_anchors = self._resolve_graph_anchors(candidate)

            if graph_anchors:
                # Use the first resolved symbol as the primary anchor
                sym_rec = graph_anchors[0]
                logger.debug(
                    f"[GraphExpand] Anchor '{cand_name}': Resolved via graph_anchor_resolution "
                    f"to {sym_rec.id} (found {len(graph_anchors)} symbols)"
                )
            else:
                logger.debug(
                    f"[GraphExpand] Failed to resolve anchor: name={cand_name}, "
                    f"file={cand_file}, type={candidate.get('type')}"
                )
                # Return unresolved anchor as-is (preserve File/Directory results)
                return dict(candidate)

        # Enrich with symbol metadata
        enriched = dict(candidate)
        enriched["symbol_id"] = sym_rec.id
        enriched["id"] = sym_rec.id.split(":", 1)[1] if ":" in sym_rec.id else sym_rec.id
        enriched["name"] = sym_rec.name
        enriched["line_start"] = sym_rec.line_start
        enriched["line_end"] = sym_rec.line_end
        enriched["qualified_name"] = sym_rec.qualified_name
        enriched["type"] = sym_rec.symbol_type
        if sym_rec.file:
            enriched["file_path"] = sym_rec.file.path

        enriched["is_anchor"] = True
        enriched["expansion_source"] = "anchor"

        logger.debug(
            f"[GraphExpand] Anchor '{cand_name}': Resolved via {resolution_method} "
            f"to {sym_rec.id}"
        )

        return enriched

    def _expand_from_anchor(
        self,
        anchor_id: str,
        anchor_dict: Dict[str, Any],
        expanded_nodes: Dict[str, ExpandedNode],
        seen_ids: Set[str],
    ) -> None:
        """Perform bounded BFS expansion from an anchor node."""
        anchor_name = anchor_dict.get("name", anchor_dict.get("id"))

        # BFS queue: (symbol_id, depth)
        queue: List[Tuple[str, int]] = [(anchor_id, 0)]
        processed: Set[str] = {anchor_id}

        while queue and len(expanded_nodes) < self.max_total_nodes:
            current_id, current_depth = queue.pop(0)

            # Respect depth limit
            if current_depth >= self.max_depth:
                continue

            logger.debug(
                f"[GraphExpand] Expanding from anchor '{anchor_name}' at depth {current_depth}"
            )

            # Get relationships at this depth
            neighbors = self._get_neighbors(current_id, current_depth, anchor_name)

            for neighbor in neighbors[: self.max_nodes_per_hop]:
                neighbor_id = neighbor["symbol_id"]

                if neighbor_id in seen_ids or neighbor_id in processed:
                    continue

                if len(expanded_nodes) >= self.max_total_nodes:
                    logger.debug(
                        f"[GraphExpand] Reached max_total_nodes limit from anchor '{anchor_name}'"
                    )
                    break

                seen_ids.add(neighbor_id)
                processed.add(neighbor_id)

                # Create expanded node
                expanded_node = ExpandedNode(
                    id=neighbor_id.split(":", 1)[1] if ":" in neighbor_id else neighbor_id,
                    symbol_id=neighbor_id,
                    name=neighbor["name"],
                    type=neighbor.get("type", "symbol"),
                    file_path=neighbor.get("file_path", ""),
                    line_start=neighbor.get("line_start"),
                    line_end=neighbor.get("line_end"),
                    qualified_name=neighbor.get("qualified_name"),
                    relationship_role=neighbor.get("relationship_role", ""),
                    rel_type=neighbor.get("rel_type", ""),
                    distance_from_anchor=current_depth + 1,
                    anchor_name=anchor_name,
                    data=neighbor.get("data", {}),
                )

                expanded_nodes[neighbor_id] = expanded_node
                logger.debug(
                    f"[GraphExpand] Added neighbor from anchor '{anchor_name}': "
                    f"{neighbor['name']} (distance={current_depth + 1})"
                )

                # Add to queue for further expansion
                queue.append((neighbor_id, current_depth + 1))

    def _get_neighbors(
        self, symbol_id: str, depth: int, anchor_name: str
    ) -> List[Dict[str, Any]]:
        """Get neighboring nodes via direct relationship queries."""
        neighbors = []

        # Query outgoing relationships (callees, dependencies, imports)
        outgoing = self.db.query(FactRelationship).filter(
            FactRelationship.analysis_id == self.analysis_id,
            FactRelationship.from_symbol_id == symbol_id
        ).limit(self.max_nodes_per_hop).all()

        for rel in outgoing:
            target_sym = self.db.query(FactSymbol).filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.id == rel.to_symbol_id
            ).first()

            if target_sym:
                neighbors.append({
                    "symbol_id": target_sym.id,
                    "name": target_sym.name,
                    "qualified_name": target_sym.qualified_name,
                    "type": target_sym.symbol_type,
                    "file_path": target_sym.file.path if target_sym.file else "",
                    "line_start": target_sym.line_start,
                    "line_end": target_sym.line_end,
                    "relationship_role": self._role_from_rel_type(rel.rel_type, "forward"),
                    "rel_type": rel.rel_type,
                    "data": {"rel_id": rel.id, "evidence_line": rel.evidence_line},
                })

        # Query incoming relationships (callers, dependents)
        incoming = self.db.query(FactRelationship).filter(
            FactRelationship.analysis_id == self.analysis_id,
            FactRelationship.to_symbol_id == symbol_id
        ).limit(self.max_nodes_per_hop).all()

        for rel in incoming:
            source_sym = self.db.query(FactSymbol).filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.id == rel.from_symbol_id
            ).first()

            if source_sym:
                neighbors.append({
                    "symbol_id": source_sym.id,
                    "name": source_sym.name,
                    "qualified_name": source_sym.qualified_name,
                    "type": source_sym.symbol_type,
                    "file_path": source_sym.file.path if source_sym.file else "",
                    "line_start": source_sym.line_start,
                    "line_end": source_sym.line_end,
                    "relationship_role": self._role_from_rel_type(rel.rel_type, "reverse"),
                    "rel_type": rel.rel_type,
                    "data": {"rel_id": rel.id, "evidence_line": rel.evidence_line},
                })

        return neighbors

    def _role_from_rel_type(self, rel_type: str, direction: str) -> str:
        """Convert relationship type to human-readable role."""
        role_map = {
            "CALLS": {"forward": "callee", "reverse": "caller"},
            "IMPORTS": {"forward": "imported_module", "reverse": "dependent_file"},
            "CONTAINS": {"forward": "contained_symbol", "reverse": "container"},
            "INHERITS": {"forward": "base_class", "reverse": "subclass"},
            "USES": {"forward": "used_entity", "reverse": "using_entity"},
            "QUERIES": {"forward": "queried_table", "reverse": "querying_code"},
            "READS": {"forward": "read_entity", "reverse": "reading_code"},
            "WRITES": {"forward": "written_entity", "reverse": "writing_code"},
            "EXPOSES": {"forward": "exposed_symbol", "reverse": "exposing_route"},
            "DECLARES": {"forward": "declared_symbol", "reverse": "declaring_entity"},
            "HANDLED_BY": {"forward": "handler", "reverse": "handled_by"},
            "DEPENDS_ON": {"forward": "dependency", "reverse": "dependent"},
        }

        if rel_type in role_map:
            return role_map[rel_type].get(direction, rel_type.lower())

        return rel_type.lower()

    def _expanded_node_to_dict(self, node: ExpandedNode) -> Dict[str, Any]:
        """Convert ExpandedNode to output dictionary format."""
        return {
            "id": node.id,
            "symbol_id": node.symbol_id,
            "name": node.name,
            "type": node.type,
            "qualified_name": node.qualified_name,
            "file_path": node.file_path,
            "line_start": node.line_start,
            "line_end": node.line_end,
            "relationship_role": node.relationship_role,
            "rel_type": node.rel_type,
            "distance_from_anchor": node.distance_from_anchor,
            "anchor_name": node.anchor_name,
            "expansion_source": f"expanded_from:{node.anchor_name}",
            "expansion_distance": node.distance_from_anchor,
            "score_type": "expanded_graph",
            **(node.data or {}),
        }
