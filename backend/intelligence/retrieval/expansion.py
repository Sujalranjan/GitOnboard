import logging
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from backend.models.fact_store import (
    FactSymbol,
    FactFile,
    FactRelationship,
    FactRoute,
    FactDatabaseObject,
    FactCapability,
    FactCapabilityMember,
)

logger = logging.getLogger(__name__)

class FactStoreExpander:
    """
    Intelligently expands retrieved candidate symbols using deterministic
    PostgreSQL Fact Store relationships (callers, callees, definitions, routes, database objects).
    Applies strict bounds to prevent context explosion.
    """

    def __init__(self, db: Session, analysis_id: int, max_expansions_per_seed: int = 3, max_total_context: int = 25):
        self.db = db
        self.analysis_id = analysis_id
        self.max_expansions_per_seed = max_expansions_per_seed
        self.max_total_context = max_total_context

    def expand_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes top fused candidates and decorates/expands them with deterministic structural facts:
        - callers and callees
        - associated HTTP routes
        - database entities / tables
        - capability memberships
        """
        if not candidates or not self.analysis_id:
            return candidates

        expanded_results: List[Dict[str, Any]] = []
        seen_entity_ids: Set[str] = set()

        # Step 1: Add seed candidates first with enriched Fact Store info
        for cand in candidates:
            cand_id = cand.get("id") or cand.get("symbol_id")
            cand_name = cand.get("name") or cand.get("match_name")
            cand_file = cand.get("file_path")

            # Try to resolve symbol in DB if ID is missing or relative
            sym_rec = None
            if cand_id and ":" in str(cand_id):
                sym_rec = self.db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.id == cand_id
                ).first()
            elif cand_name and cand_file:
                # Find matching symbol by name and file path
                sym_rec = self.db.query(FactSymbol).join(FactFile).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.name == cand_name,
                    FactFile.path == cand_file
                ).first()
            elif cand_name:
                sym_rec = self.db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.name == cand_name
                ).first()

            enriched_cand = dict(cand)
            if sym_rec:
                clean_sym_id = sym_rec.id.split(":", 1)[1] if ":" in sym_rec.id else sym_rec.id
                enriched_cand["symbol_id"] = sym_rec.id
                enriched_cand["id"] = clean_sym_id
                enriched_cand["line_start"] = sym_rec.line_start
                enriched_cand["line_end"] = sym_rec.line_end
                enriched_cand["qualified_name"] = sym_rec.qualified_name
                if sym_rec.file:
                    enriched_cand["file_path"] = sym_rec.file.path
                    enriched_cand["language"] = sym_rec.file.language

                # Check if it has an associated route
                route = self.db.query(FactRoute).filter(
                    FactRoute.analysis_id == self.analysis_id,
                    (FactRoute.symbol_id == sym_rec.id) | (FactRoute.handler_symbol_id == sym_rec.id)
                ).first()
                if route:
                    enriched_cand["route"] = f"{route.method} {route.path}"

                # Check if it has capability memberships
                cap_member = self.db.query(FactCapabilityMember).join(FactCapability).filter(
                    FactCapability.analysis_id == self.analysis_id,
                    FactCapabilityMember.symbol_id == sym_rec.id,
                ).first()
                if cap_member and cap_member.capability:
                    enriched_cand["capability"] = cap_member.capability.name

                seen_entity_ids.add(sym_rec.id)

            expanded_results.append(enriched_cand)

        # Step 2: Limited structural expansion (callers / callees)
        expansion_items: List[Dict[str, Any]] = []
        for cand in expanded_results[:10]:  # Only expand top 10 seeds
            sym_id = cand.get("symbol_id")
            if not sym_id:
                continue

            # Query outgoing relationships (Callees / Dependencies)
            outgoing = self.db.query(FactRelationship).filter(
                FactRelationship.analysis_id == self.analysis_id,
                FactRelationship.from_symbol_id == sym_id
            ).limit(self.max_expansions_per_seed).all()

            for rel in outgoing:
                if rel.to_symbol_id not in seen_entity_ids and len(expanded_results) + len(expansion_items) < self.max_total_context:
                    target_sym = self.db.query(FactSymbol).filter(
                        FactSymbol.analysis_id == self.analysis_id,
                        FactSymbol.id == rel.to_symbol_id
                    ).first()
                    if target_sym:
                        seen_entity_ids.add(target_sym.id)
                        expansion_items.append({
                            "id": target_sym.id.split(":", 1)[1] if ":" in target_sym.id else target_sym.id,
                            "symbol_id": target_sym.id,
                            "name": target_sym.name,
                            "qualified_name": target_sym.qualified_name,
                            "type": target_sym.symbol_type,
                            "file_path": target_sym.file.path if target_sym.file else "",
                            "line_start": target_sym.line_start,
                            "line_end": target_sym.line_end,
                            "expansion_reason": f"callee_of:{cand.get('name')}",
                            "rel_type": rel.rel_type
                        })

            # Query incoming relationships (Callers)
            incoming = self.db.query(FactRelationship).filter(
                FactRelationship.analysis_id == self.analysis_id,
                FactRelationship.to_symbol_id == sym_id
            ).limit(self.max_expansions_per_seed).all()

            for rel in incoming:
                if rel.from_symbol_id not in seen_entity_ids and len(expanded_results) + len(expansion_items) < self.max_total_context:
                    source_sym = self.db.query(FactSymbol).filter(
                        FactSymbol.analysis_id == self.analysis_id,
                        FactSymbol.id == rel.from_symbol_id
                    ).first()
                    if source_sym:
                        seen_entity_ids.add(source_sym.id)
                        expansion_items.append({
                            "id": source_sym.id.split(":", 1)[1] if ":" in source_sym.id else source_sym.id,
                            "symbol_id": source_sym.id,
                            "name": source_sym.name,
                            "qualified_name": source_sym.qualified_name,
                            "type": source_sym.symbol_type,
                            "file_path": source_sym.file.path if source_sym.file else "",
                            "line_start": source_sym.line_start,
                            "line_end": source_sym.line_end,
                            "expansion_reason": f"caller_of:{cand.get('name')}",
                            "rel_type": rel.rel_type
                        })

        expanded_results.extend(expansion_items)
        return expanded_results[:self.max_total_context]
