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

        logger.info(f"[RIM EXPAND] Starting expansion of {len(candidates)} candidates")

        # Step 1: Add seed candidates first with enriched Fact Store info
        for cand in candidates:
            cand_id = cand.get("id") or cand.get("symbol_id")
            cand_name = cand.get("name") or cand.get("match_name")
            cand_file = cand.get("file_path")
            cand_type = cand.get("match_type") or cand.get("type")

            # Try to resolve symbol in DB if ID is missing or relative
            sym_rec = None
            resolution_method = None

            # Strategy 1: Use pre-resolved symbol_id (from semantic or lexical search)
            if cand.get("symbol_id"):
                sym_rec = self.db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.id == cand.get("symbol_id")
                ).first()
                if sym_rec:
                    resolution_method = "symbol_id_field"

            # Strategy 2: Query by full ID (e.g., database format with analysis_id prefix)
            if not sym_rec and cand_id and ":" in str(cand_id):
                sym_rec = self.db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.id == cand_id
                ).first()
                if sym_rec:
                    resolution_method = "full_id"

            # Strategy 3: Query by name and file path (most reliable for symbols)
            if not sym_rec and cand_name and cand_file:
                sym_rec = self.db.query(FactSymbol).join(FactFile).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.name == cand_name,
                    FactFile.path == cand_file
                ).first()
                if sym_rec:
                    resolution_method = "name_file_match"

            # Strategy 4: Query by name only (last resort)
            if not sym_rec and cand_name:
                sym_rec = self.db.query(FactSymbol).filter(
                    FactSymbol.analysis_id == self.analysis_id,
                    FactSymbol.name == cand_name
                ).first()
                if sym_rec:
                    resolution_method = "name_only"

            enriched_cand = dict(cand)
            if sym_rec:
                logger.info(f"[RIM EXPAND] Seed[{len(expanded_results)}] {cand_name}: Resolved via {resolution_method} to {sym_rec.id}")
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
            else:
                logger.info(f"[RIM EXPAND] Failed to resolve candidate: name={cand_name}, file={cand_file}, type={cand_type}")

            expanded_results.append(enriched_cand)

        # Step 2: Limited structural expansion (callers / callees)
        expansion_items: List[Dict[str, Any]] = []
        total_relationships_found = 0

        # Debug: sample some relationship IDs from database
        sample_rels = self.db.query(FactRelationship).filter(
            FactRelationship.analysis_id == self.analysis_id
        ).limit(5).all()
        if sample_rels:
            logger.info(f"[RIM EXPAND] Sample FactRelationship from DB (analysis_id={self.analysis_id}, total exist):")
            for rel in sample_rels:
                logger.info(f"[RIM EXPAND]   from={rel.from_symbol_id} to={rel.to_symbol_id} type={rel.rel_type}")

        # Debug: Get total counts by analysis
        total_rels_in_analysis = self.db.query(FactRelationship).filter(
            FactRelationship.analysis_id == self.analysis_id
        ).count()
        logger.info(f"[RIM EXPAND] Total FactRelationship records for analysis_id={self.analysis_id}: {total_rels_in_analysis}")

        for idx, cand in enumerate(expanded_results[:10]):  # Only expand top 10 seeds
            sym_id = cand.get("symbol_id")
            cand_name = cand.get("name")
            if not sym_id:
                logger.info(f"[RIM EXPAND] Seed[{idx}] {cand_name} has no symbol_id, skipping expansion")
                continue

            logger.info(f"[RIM EXPAND] Seed[{idx}] {cand_name}: trying to find relationships for sym_id={sym_id}")

            # Query outgoing relationships (Callees / Dependencies)
            outgoing = self.db.query(FactRelationship).filter(
                FactRelationship.analysis_id == self.analysis_id,
                FactRelationship.from_symbol_id == sym_id
            ).limit(self.max_expansions_per_seed).all()

            logger.info(f"[RIM EXPAND] Seed[{idx}] {cand_name} ({sym_id}): found {len(outgoing)} outgoing relationships")

            for rel in outgoing:
                if rel.to_symbol_id not in seen_entity_ids and len(expanded_results) + len(expansion_items) < self.max_total_context:
                    target_sym = self.db.query(FactSymbol).filter(
                        FactSymbol.analysis_id == self.analysis_id,
                        FactSymbol.id == rel.to_symbol_id
                    ).first()
                    if target_sym:
                        seen_entity_ids.add(target_sym.id)
                        total_relationships_found += 1
                        logger.info(f"[RIM EXPAND] Found callee via {rel.rel_type}: {target_sym.name}")
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

            logger.info(f"[RIM EXPAND] {cand_name} ({sym_id}): found {len(incoming)} incoming relationships")

            for rel in incoming:
                if rel.from_symbol_id not in seen_entity_ids and len(expanded_results) + len(expansion_items) < self.max_total_context:
                    source_sym = self.db.query(FactSymbol).filter(
                        FactSymbol.analysis_id == self.analysis_id,
                        FactSymbol.id == rel.from_symbol_id
                    ).first()
                    if source_sym:
                        seen_entity_ids.add(source_sym.id)
                        total_relationships_found += 1
                        logger.info(f"[RIM EXPAND] Found caller via {rel.rel_type}: {source_sym.name}")
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

        logger.info(f"[RIM EXPAND] Total expansion complete: {total_relationships_found} relationships found, {len(expansion_items)} new entities added")

        expanded_results.extend(expansion_items)
        return expanded_results[:self.max_total_context]
