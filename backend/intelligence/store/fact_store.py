import logging
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.models.fact_store import (
    FactFile,
    FactSymbol,
    FactRelationship,
    FactRoute,
    FactDatabaseObject,
    FactCapability,
    FactEvidence,
    FactCapabilityMember,
)
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.capabilities.model import Capability, CapabilityCategory

logger = logging.getLogger(__name__)

def save_rim_to_fact_store(db: Session, analysis_id: int, model: RepositoryModel):
    """
    Persists an in-memory RepositoryModel into canonical relational PostgreSQL Fact Store tables.
    Clears any prior facts for this analysis_id to allow idempotent re-analysis.
    """
    logger.info(f"Saving RIM facts to canonical PostgreSQL Fact Store for analysis_id={analysis_id}...")

    # Detect orphaned relationships (references to non-existent entities)
    # Warn but don't fail - persistence logic will skip them
    orphaned_rels = []
    for rel_id, rel in model.relationships.items():
        if rel.source_id not in model.entities:
            orphaned_rels.append(f"{rel_id}: missing source {rel.source_id}")
        if rel.target_id not in model.entities:
            orphaned_rels.append(f"{rel_id}: missing target {rel.target_id}")

    if orphaned_rels:
        logger.warning(
            f"RepositoryModel contains {len(orphaned_rels)} orphaned relationship references (will be skipped):\n" +
            "\n".join(orphaned_rels[:5]) +  # Show first 5 to keep warning readable
            (f"\n... and {len(orphaned_rels) - 5} more" if len(orphaned_rels) > 5 else "")
        )

    try:
        # Clear existing facts for this analysis_id to ensure clean transaction
        db.query(FactCapabilityMember).filter(
            FactCapabilityMember.capability_id.in_(
                db.query(FactCapability.id).filter(FactCapability.analysis_id == analysis_id)
            )
        ).delete(synchronize_session=False)
        
        db.query(FactEvidence).filter(FactEvidence.analysis_id == analysis_id).delete(synchronize_session=False)
        db.query(FactCapability).filter(FactCapability.analysis_id == analysis_id).delete(synchronize_session=False)
        db.query(FactDatabaseObject).filter(FactDatabaseObject.analysis_id == analysis_id).delete(synchronize_session=False)
        db.query(FactRoute).filter(FactRoute.analysis_id == analysis_id).delete(synchronize_session=False)
        db.query(FactRelationship).filter(FactRelationship.analysis_id == analysis_id).delete(synchronize_session=False)
        db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis_id).delete(synchronize_session=False)
        db.query(FactFile).filter(FactFile.analysis_id == analysis_id).delete(synchronize_session=False)
        db.flush()

        seen_file_ids = set()
        file_records = []
        file_id_map = {}  # repo_path -> file_db_id

        # 1. Save File entities first
        for entity_id, entity in model.entities.items():
            if entity.type == EntityType.FILE and entity.id not in seen_file_ids:
                seen_file_ids.add(entity.id)
                db_id = f"{analysis_id}:{entity.id}"
                f_path = entity.location.repository_path or entity.name
                p_lower = f_path.lower()
                
                # Classification signals
                is_agent = (
                    p_lower.endswith("agents.md") or 
                    p_lower.endswith("claude.md") or 
                    p_lower.endswith("agent.md") or 
                    p_lower.endswith("skill.md") or 
                    "copilot-instructions.md" in p_lower or
                    ".cursor/" in p_lower or 
                    ".agents/" in p_lower
                )
                is_doc = (
                    p_lower.endswith((".md", ".rst", ".mmd", ".markdown")) or
                    p_lower.startswith("docs/") or "/docs/" in p_lower or
                    p_lower.startswith("doc/") or "/doc/" in p_lower
                )
                is_test = (
                    p_lower.startswith(("tests/", "test/", "__tests__/", "spec/")) or
                    "/tests/" in p_lower or "/test/" in p_lower or
                    "/__tests__/" in p_lower or "/spec/" in p_lower or
                    p_lower.split("/")[-1].startswith("test_") or
                    p_lower.endswith(("_test.py", "_test.js", ".test.ts", ".test.js", ".spec.ts", ".spec.js"))
                )
                is_gen = (
                    "dist/" in p_lower or "build/" in p_lower or
                    "generated/" in p_lower or "out/" in p_lower
                )
                is_bin = (
                    p_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico", ".wasm", ".pyc", ".so", ".dll", ".exe", ".zip", ".tar", ".gz", ".bin", ".db", ".sqlite")) or
                    entity.metadata.get("is_binary", False)
                )

                file_rec = FactFile(
                    id=db_id,
                    analysis_id=analysis_id,
                    path=f_path,
                    language=entity.metadata.get("language"),
                    size=entity.metadata.get("size", entity.metadata.get("file_size", 0)),
                    content_hash=entity.metadata.get("content_hash"),
                    is_binary=is_bin,
                    is_generated=is_gen,
                    is_test=is_test,
                    is_documentation=is_doc,
                    is_agent_instruction=is_agent,
                    blob_name=entity.metadata.get("blob_name"),
                    snapshot_id=entity.metadata.get("snapshot_id"),
                    content_type=entity.metadata.get("content_type"),
                )
                file_records.append(file_rec)
                if entity.location.repository_path:
                    file_id_map[entity.location.repository_path] = db_id
                    file_id_map[entity.location.repository_path.replace("\\", "/").removeprefix("./").lstrip("/")] = db_id
                if entity.name:
                    file_id_map[entity.name] = db_id
                file_id_map[entity.id] = db_id

        if file_records:
            # Log blob verification before committing to database
            blob_count = sum(1 for f in file_records if f.blob_name)
            no_blob_count = sum(1 for f in file_records if not f.blob_name)
            logger.info(f"[FACT_STORE] Saving {len(file_records)} FactFile records:")
            logger.info(f"  - {blob_count} files WITH blob_name (uploaded to Azure)")
            logger.info(f"  - {no_blob_count} files WITHOUT blob_name (upload failed or skipped)")

            if no_blob_count > 0:
                no_blob_files = [f.path for f in file_records if not f.blob_name]
                logger.warning(f"[FACT_STORE] {no_blob_count} files without blob_name: {no_blob_files[:5]}" +
                              (f" ... and {no_blob_count - 5} more" if no_blob_count > 5 else ""))

            db.add_all(file_records)
            db.flush()
            logger.info(f"[FACT_STORE] FactFile records committed to database")

        # 2. Save Code Symbols
        seen_symbol_ids = set()
        symbol_records = []
        for entity_id, entity in model.entities.items():
            if entity.type not in (EntityType.FILE, EntityType.DIRECTORY) and entity.id not in seen_symbol_ids:
                seen_symbol_ids.add(entity.id)
                f_id = entity.metadata.get("file_id") if entity.metadata else None
                f_path = entity.location.repository_path if entity.location else None
                
                # Resolve foreign key to FactFile.id
                f_db_id = None
                if f_id and f_id in file_id_map:
                    f_db_id = file_id_map[f_id]
                elif f_path and f_path in file_id_map:
                    f_db_id = file_id_map[f_path]
                elif f_path and f_path.replace("\\", "/").removeprefix("./").lstrip("/") in file_id_map:
                    f_db_id = file_id_map[f_path.replace("\\", "/").removeprefix("./").lstrip("/")]

                db_id = f"{analysis_id}:{entity.id}"
                symbol_rec = FactSymbol(
                    id=db_id,
                    analysis_id=analysis_id,
                    file_id=f_db_id,
                    name=entity.name,
                    qualified_name=entity.qualified_name or entity.name,
                    symbol_type=entity.type.value if hasattr(entity.type, "value") else str(entity.type),
                    line_start=entity.location.start_line,
                    line_end=entity.location.end_line,
                    signature_hash=entity.metadata.get("signature_hash") if entity.metadata else None,
                    metadata_json=entity.metadata,
                )
                symbol_records.append(symbol_rec)

        if symbol_records:
            db.add_all(symbol_records)
            db.flush()

        # 3. Save Relationships
        seen_rel_ids = set()
        rel_records = []
        skipped_rels = 0
        for rel_id, rel in model.relationships.items():
            if rel.id not in seen_rel_ids:
                seen_rel_ids.add(rel.id)
                # Validate BOTH source and target exist before creating relationship
                source_exists = rel.source_id in seen_symbol_ids or rel.source_id in seen_file_ids
                target_exists = rel.target_id in seen_symbol_ids or rel.target_id in seen_file_ids

                if source_exists and target_exists:
                    rel_type_str = rel.type.value if hasattr(rel.type, "value") else str(rel.type)
                    db_id = f"{analysis_id}:{rel.id}"
                    rel_rec = FactRelationship(
                        id=db_id,
                        analysis_id=analysis_id,
                        from_symbol_id=f"{analysis_id}:{rel.source_id}",
                        to_symbol_id=f"{analysis_id}:{rel.target_id}",
                        rel_type=rel_type_str,
                        evidence_line=rel.metadata.get("line"),
                        evidence_snippet=rel.metadata.get("snippet"),
                        status=rel.metadata.get("status", "CONFIRMED"),
                    )
                    rel_records.append(rel_rec)
                else:
                    skipped_rels += 1
                    if not source_exists:
                        logger.debug(f"Skipping relationship {rel.id}: source {rel.source_id} not found")
                    if not target_exists:
                        logger.debug(f"Skipping relationship {rel.id}: target {rel.target_id} not found")

        logger.info(f"Saved {len(rel_records)} relationships (skipped {skipped_rels} due to missing entities)")
        if rel_records:
            db.add_all(rel_records)
            db.flush()

        # 4. Save Routes
        route_records = []
        seen_route_ids = set()
        
        # Build mapping of route_id -> handler_symbol_id from relationships (e.g. HANDLED_BY or EXPOSES)
        route_handler_map = {}
        for rel in model.relationships.values():
            rel_type_str = rel.type.value if hasattr(rel.type, "value") else str(rel.type)
            if rel_type_str == "EXPOSES":
                route_handler_map[rel.target_id] = rel.source_id
            elif rel_type_str == "HANDLED_BY":
                route_handler_map[rel.source_id] = rel.target_id

        for idx, entity in enumerate(model.entities.values()):
            if entity.type == EntityType.ROUTE or "http_method" in entity.metadata or "route_path" in entity.metadata:
                r_id = f"route_{analysis_id}_{idx}_{entity.id}"
                if r_id not in seen_route_ids:
                    seen_route_ids.add(r_id)
                    method = entity.metadata.get("http_method", entity.metadata.get("method", "GET"))
                    path = entity.metadata.get("route_path", entity.metadata.get("path", entity.name))
                    handler_id = entity.metadata.get("handler_symbol_id", entity.metadata.get("handler_id")) or route_handler_map.get(entity.id)

                    handler_db_id = f"{analysis_id}:{handler_id}" if handler_id else None

                    route_rec = FactRoute(
                        id=r_id,
                        analysis_id=analysis_id,
                        symbol_id=f"{analysis_id}:{entity.id}" if (entity.id in seen_symbol_ids or entity.id in seen_file_ids) else None,
                        method=method.upper(),
                        path=path,
                        handler_symbol_id=handler_db_id,
                    )
                    route_records.append(route_rec)

        if route_records:
            db.add_all(route_records)
            db.flush()

        # 5. Save Database Objects
        db_obj_records = []
        seen_db_obj_ids = set()
        for idx, entity in enumerate(model.entities.values()):
            if entity.type in (EntityType.TABLE, EntityType.DATABASE, EntityType.COLUMN) or entity.metadata.get("is_db_model"):
                db_id = f"dbobj_{analysis_id}_{idx}_{entity.id}"
                if db_id not in seen_db_obj_ids:
                    seen_db_obj_ids.add(db_id)
                    db_obj_rec = FactDatabaseObject(
                        id=db_id,
                        analysis_id=analysis_id,
                        symbol_id=f"{analysis_id}:{entity.id}" if (entity.id in seen_symbol_ids or entity.id in seen_file_ids) else None,
                        object_type=entity.type.value if hasattr(entity.type, "value") else "table",
                        name=entity.name,
                    )
                    db_obj_records.append(db_obj_rec)

        if db_obj_records:
            db.add_all(db_obj_records)
            db.flush()

        # 6. Save Capabilities, Evidence, and Members
        seen_cap_ids = set()
        for cap_id, cap in model.capabilities.items():
            if cap.id not in seen_cap_ids:
                seen_cap_ids.add(cap.id)
                cap_db_id = f"{analysis_id}:{cap.id}"
                cap_rec = FactCapability(
                    id=cap_db_id,
                    analysis_id=analysis_id,
                    name=cap.purpose or (cap.category.value if hasattr(cap.category, "value") else str(cap.category)),
                    capability_type=cap.category.value if hasattr(cap.category, "value") else str(cap.category),
                    status="CONFIRMED" if cap.confidence >= 0.7 else "INFERRED",
                    evidence_summary=", ".join(cap.responsibilities) if cap.responsibilities else "Detected via static analysis",
                )
                db.add(cap_rec)
                db.flush()

                # Evidence
                for idx, ev in enumerate(cap.evidence):
                    ev_id = f"ev_{analysis_id}_{cap.id}_{idx}"
                    sym_id = ev.get("symbol_id")
                    sym_db_id = f"{analysis_id}:{sym_id}" if sym_id else None

                    ev_rec = FactEvidence(
                        id=ev_id,
                        analysis_id=analysis_id,
                        fact_type=ev.get("fact_type", ev.get("type", "static_pattern")),
                        symbol_id=sym_db_id if (sym_id in seen_symbol_ids or sym_id in seen_file_ids) else None,
                        details=ev,
                        location=ev.get("location"),
                    )
                    db.add(ev_rec)
                    db.flush()

                # Capability Members from representative_sources and metadata role mapping
                member_role_map = {}
                if hasattr(cap, "metadata") and isinstance(cap.metadata, dict) and "member_roles" in cap.metadata:
                    for item in cap.metadata["member_roles"]:
                        member_role_map[item["symbol_id"]] = item["role"]

                member_candidates = list(cap.representative_sources)
                for ev in cap.evidence:
                    if ev.get("symbol_id"):
                        member_candidates.append(ev.get("symbol_id"))

                seen_mem_syms = set()
                for idx, sym_id in enumerate(member_candidates):
                    if sym_id not in seen_mem_syms and (sym_id in seen_symbol_ids or sym_id in seen_file_ids):
                        seen_mem_syms.add(sym_id)
                        assigned_role = member_role_map.get(sym_id, "member")
                        member_rec = FactCapabilityMember(
                            id=f"mem_{analysis_id}_{cap.id}_{idx}_{sym_id}",
                            capability_id=cap_db_id,
                            symbol_id=f"{analysis_id}:{sym_id}",
                            role=assigned_role,
                            evidence_id=None,
                        )
                        db.add(member_rec)

        db.commit()
        logger.info(f"Successfully saved {len(file_records)} files, {len(symbol_records)} symbols, and {len(rel_records)} relationships to Fact Store.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error persisting RIM facts to Fact Store for analysis_id={analysis_id}: {e}", exc_info=True)
        raise e


def load_rim_from_fact_store(db: Session, analysis_id: int) -> RepositoryModel:
    """
    Reconstructs an in-memory RepositoryModel directly by querying canonical PostgreSQL Fact Store tables.
    """
    logger.info(f"Reconstructing RIM from canonical Fact Store for analysis_id={analysis_id}...")

    # Query tables
    file_records = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).all()
    symbol_records = db.query(FactSymbol).filter(FactSymbol.analysis_id == analysis_id).all()
    rel_records = db.query(FactRelationship).filter(FactRelationship.analysis_id == analysis_id).all()
    cap_records = db.query(FactCapability).filter(FactCapability.analysis_id == analysis_id).all()

    entities: Dict[str, Entity] = {}

    # Reconstruct File Entities
    for f in file_records:
        raw_id = f.id.split(":", 1)[1] if ":" in f.id else f.id
        entities[raw_id] = Entity(
            id=raw_id,
            type=EntityType.FILE,
            name=f.path.split("/")[-1],
            location=SourceLocation(repository_path=f.path, start_line=1, end_line=1, language=f.language or "Python"),
            metadata={
                "language": f.language,
                "content_hash": f.content_hash,
                "blob_name": f.blob_name,
                "snapshot_id": f.snapshot_id,
                "content_type": f.content_type,
                "size": f.size,
                "is_binary": f.is_binary,
            },
        )

    # Reconstruct Symbol Entities
    for s in symbol_records:
        raw_id = s.id.split(":", 1)[1] if ":" in s.id else s.id
        try:
            etype = EntityType(s.symbol_type)
        except ValueError:
            etype = EntityType.FUNCTION

        entities[raw_id] = Entity(
            id=raw_id,
            type=etype,
            name=s.name,
            qualified_name=s.qualified_name,
            location=SourceLocation(
                repository_path=s.file.path if s.file else "",
                start_line=s.line_start or 1,
                end_line=s.line_end or 1,
                language="Python",
            ),
            metadata=s.metadata_json or {},
        )

    # Reconstruct Relationships
    relationships: Dict[str, Relationship] = {}
    for r in rel_records:
        raw_id = r.id.split(":", 1)[1] if ":" in r.id else r.id
        raw_src = r.from_symbol_id.split(":", 1)[1] if ":" in r.from_symbol_id else r.from_symbol_id
        raw_tgt = r.to_symbol_id.split(":", 1)[1] if ":" in r.to_symbol_id else r.to_symbol_id
        try:
            rtype = RelationshipType(r.rel_type)
        except ValueError:
            rtype = RelationshipType.USES

        relationships[raw_id] = Relationship(
            id=raw_id,
            type=rtype,
            source_id=raw_src,
            target_id=raw_tgt,
            metadata={
                "line": r.evidence_line,
                "snippet": r.evidence_snippet,
                "status": r.status,
            },
        )

    # Reconstruct Capabilities
    capabilities: Dict[str, Capability] = {}
    for c in cap_records:
        raw_id = c.id.split(":", 1)[1] if ":" in c.id else c.id
        try:
            category = CapabilityCategory(c.capability_type)
        except ValueError:
            category = CapabilityCategory.BUSINESS_OPERATION

        capabilities[raw_id] = Capability(
            id=raw_id,
            purpose=c.name,
            category=category,
            responsibilities=[c.evidence_summary] if c.evidence_summary else [],
            keywords=[],
            representative_sources=[],
            confidence=1.0 if c.status == "CONFIRMED" else 0.5,
            evidence=[],
        )

    model = RepositoryModel(
        metadata=RepositoryMetadata(name="AnalysisRepo", path="/repo", languages=["Python"]),
        entities=entities,
        relationships=relationships,
        capabilities=capabilities,
    )
    return model
