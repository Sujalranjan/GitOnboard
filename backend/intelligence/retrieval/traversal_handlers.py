"""
Individual Relationship Traversal Handlers for FactStoreGraphTraverser.
Dispatches specialized queries over FactRelationship, FactRoute, and FactDatabaseObject.
"""
from __future__ import annotations

import logging
from typing import List, Union, TYPE_CHECKING
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
    SemanticQueryClass,
    TraversalDirection,
)

if TYPE_CHECKING:
    from backend.intelligence.retrieval.graph_traverser import (
        TraversedEntity,
        RelationshipTraversalResult,
    )

logger = logging.getLogger(__name__)


def traverse_containment(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    related: List[TraversedEntity] = []

    if isinstance(target, FactFile):
        # Fetch symbols declared in file
        symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.file_id == target.id
        ).order_by(FactSymbol.line_start).all()

        for s in symbols:
            related.append(entity_cls(
                name=s.name,
                entity_type=s.symbol_type,
                location=target.path,
                line_number=s.line_start,
                relationship_role="defined_symbol",
                data={"qualified_name": s.qualified_name}
            ))
        return result_cls(
            query_class=SemanticQueryClass.CONTAINMENT,
            direction=TraversalDirection.FORWARD,
            target_entity=target,
            target_display_name=target.path,
            target_type="file",
            related_entities=related,
            explanation=f"Found {len(related)} symbols declared in '{target.path}'."
        )

    if isinstance(target, FactSymbol):
        # If class, fetch child members
        symbols = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            FactSymbol.file_id == target.file_id,
            FactSymbol.qualified_name.ilike(f"{target.qualified_name}.%")
        ).order_by(FactSymbol.line_start).all()

        for s in symbols:
            related.append(entity_cls(
                name=s.name,
                entity_type=s.symbol_type,
                location=target.file.path if target.file else "",
                line_number=s.line_start,
                relationship_role="declared_method",
                data={"qualified_name": s.qualified_name}
            ))
        return result_cls(
            query_class=SemanticQueryClass.CONTAINMENT,
            direction=TraversalDirection.FORWARD,
            target_entity=target,
            target_display_name=target.name,
            target_type=target.symbol_type,
            related_entities=related,
            explanation=f"Found {len(related)} members in '{target.name}'."
        )

    return result_cls(
        query_class=SemanticQueryClass.CONTAINMENT,
        direction=TraversalDirection.FORWARD,
        target_entity=target,
        target_display_name=getattr(target, "name", "target"),
        target_type="unknown",
        related_entities=[],
        explanation="Target does not support containment lookup.",
    )


def traverse_imports_forward(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    file_rec = target if isinstance(target, FactFile) else (target.file if getattr(target, "file", None) else None)
    if not file_rec:
        return result_cls(
            query_class=SemanticQueryClass.IMPORTS_FORWARD,
            direction=TraversalDirection.FORWARD,
            target_entity=target,
            target_display_name=getattr(target, "name", str(target)),
            target_type="symbol",
            related_entities=[],
            explanation=f"Target '{getattr(target, 'name', '')}' is not associated with a source file.",
        )

    edges = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.from_symbol_id == file_rec.id,
        FactRelationship.rel_type == "IMPORTS"
    ).all()

    related: List[TraversedEntity] = []
    for rel in edges:
        mod_name = (rel.to_symbol_id.split("#")[-1] if "#" in rel.to_symbol_id else rel.to_symbol_id.split(":")[-1])
        related.append(entity_cls(
            name=mod_name,
            entity_type="module",
            location=file_rec.path,
            line_number=rel.evidence_line,
            relationship_role="imported_module",
            data={"rel_id": rel.id, "to_symbol_id": rel.to_symbol_id}
        ))

    return result_cls(
        query_class=SemanticQueryClass.IMPORTS_FORWARD,
        direction=TraversalDirection.FORWARD,
        target_entity=file_rec,
        target_display_name=file_rec.path,
        target_type="file",
        related_entities=related,
        raw_edges=edges,
        explanation=f"File '{file_rec.path}' imports {len(related)} modules/packages."
    )


def traverse_imports_reverse(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    target_path = target.path if isinstance(target, FactFile) else getattr(target, "name", "")
    clean_mod = target_path.replace("/", ".").replace(".py", "").replace(".ts", "").replace(".js", "")
    mod_base = clean_mod.split(".")[-1]

    # Match incoming IMPORTS relationships
    conditions = [FactRelationship.to_symbol_id.ilike(f"%#{clean_mod}")]
    if isinstance(target, FactFile):
        conditions.append(FactRelationship.to_symbol_id == target.id)
    if mod_base != clean_mod:
        conditions.append(FactRelationship.to_symbol_id.ilike(f"%#{mod_base}"))

    edges = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.rel_type == "IMPORTS",
        or_(*conditions)
    ).all()

    # Find importing files
    from_file_ids = list({e.from_symbol_id for e in edges})
    importing_files = db.query(FactFile).filter(
        FactFile.analysis_id == analysis_id,
        FactFile.id.in_(from_file_ids)
    ).all() if from_file_ids else []

    related: List[TraversedEntity] = []
    for f in importing_files:
        related.append(entity_cls(
            name=f.path,
            entity_type="file",
            location=f.path,
            line_number=1,
            relationship_role="dependent_file",
            data={"file_id": f.id}
        ))

    return result_cls(
        query_class=SemanticQueryClass.IMPORTS_REVERSE,
        direction=TraversalDirection.REVERSE,
        target_entity=target,
        target_display_name=target_path,
        target_type="file" if isinstance(target, FactFile) else "module",
        related_entities=related,
        raw_edges=edges,
        explanation=f"Found {len(related)} files depending on / importing '{target_path}'."
    )


def traverse_calls_forward(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    if not isinstance(target, FactSymbol):
        return result_cls(
            query_class=SemanticQueryClass.CALLS_FORWARD,
            direction=TraversalDirection.FORWARD,
            target_entity=target,
            target_display_name=getattr(target, "name", str(target)),
            target_type="unknown",
            related_entities=[],
            explanation="Calls forward traversal requires a function or method target.",
        )

    edges = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.from_symbol_id == target.id,
        FactRelationship.rel_type == "CALLS"
    ).all()

    related: List[TraversedEntity] = []
    for rel in edges:
        callee_name = rel.to_symbol_id.split("#")[-1] if "#" in rel.to_symbol_id else rel.to_symbol_id.split(":")[-1]
        callee_name = callee_name.split(".")[-1]
        related.append(entity_cls(
            name=callee_name,
            entity_type="function",
            location=target.file.path if target.file else "",
            line_number=rel.evidence_line,
            relationship_role="callee",
            data={"rel_id": rel.id, "to_symbol_id": rel.to_symbol_id}
        ))

    return result_cls(
        query_class=SemanticQueryClass.CALLS_FORWARD,
        direction=TraversalDirection.FORWARD,
        target_entity=target,
        target_display_name=target.name,
        target_type=target.symbol_type,
        related_entities=related,
        raw_edges=edges,
        explanation=f"Function '{target.name}' invokes {len(related)} functions/methods."
    )


def traverse_calls_reverse(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    target_name = target.name if isinstance(target, FactSymbol) else getattr(target, "name", str(target))
    target_id = target.id if isinstance(target, FactSymbol) else ""
    target_qname = getattr(target, "qualified_name", target_name)

    conditions = [
        FactRelationship.to_symbol_id == target_id,
        FactRelationship.to_symbol_id.ilike(f"%#{target_qname}"),
        FactRelationship.to_symbol_id.ilike(f"%#{target_name}"),
        FactRelationship.to_symbol_id.ilike(f"%.{target_name}"),
    ]

    edges = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.rel_type == "CALLS",
        or_(*conditions)
    ).all()

    caller_ids = list({e.from_symbol_id for e in edges})
    caller_symbols = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis_id,
        FactSymbol.id.in_(caller_ids)
    ).all() if caller_ids else []

    related: List[TraversedEntity] = []
    for s in caller_symbols:
        related.append(entity_cls(
            name=s.name,
            entity_type=s.symbol_type,
            location=s.file.path if s.file else "",
            line_number=s.line_start,
            relationship_role="caller",
            data={"symbol_id": s.id}
        ))

    return result_cls(
        query_class=SemanticQueryClass.CALLS_REVERSE,
        direction=TraversalDirection.REVERSE,
        target_entity=target,
        target_display_name=target_name,
        target_type="function" if isinstance(target, FactSymbol) else "symbol",
        related_entities=related,
        raw_edges=edges,
        explanation=f"Found {len(related)} functions/methods that call '{target_name}'."
    )


def traverse_inherits_forward(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    if not isinstance(target, FactSymbol):
        return result_cls(
            query_class=SemanticQueryClass.INHERITS_FORWARD,
            direction=TraversalDirection.FORWARD,
            target_entity=target,
            target_display_name=getattr(target, "name", str(target)),
            target_type="unknown",
            related_entities=[],
            explanation="Inheritance traversal requires a class target.",
        )

    edges = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.from_symbol_id == target.id,
        FactRelationship.rel_type == "INHERITS"
    ).all()

    related: List[TraversedEntity] = []
    for rel in edges:
        base_name = rel.to_symbol_id.split("#")[-1] if "#" in rel.to_symbol_id else rel.to_symbol_id.split(":")[-1]
        base_name = base_name.split(".")[-1]
        related.append(entity_cls(
            name=base_name,
            entity_type="class",
            location=target.file.path if target.file else "",
            line_number=rel.evidence_line,
            relationship_role="base_class",
            data={"rel_id": rel.id, "to_symbol_id": rel.to_symbol_id}
        ))

    return result_cls(
        query_class=SemanticQueryClass.INHERITS_FORWARD,
        direction=TraversalDirection.FORWARD,
        target_entity=target,
        target_display_name=target.name,
        target_type="class",
        related_entities=related,
        raw_edges=edges,
        explanation=f"Class '{target.name}' inherits from {len(related)} base classes."
    )


def traverse_inherits_reverse(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    target_name = target.name if isinstance(target, FactSymbol) else getattr(target, "name", str(target))
    target_id = target.id if isinstance(target, FactSymbol) else ""
    target_qname = getattr(target, "qualified_name", target_name)

    conditions = [
        FactRelationship.to_symbol_id == target_id,
        FactRelationship.to_symbol_id.ilike(f"%#{target_qname}"),
        FactRelationship.to_symbol_id.ilike(f"%#{target_name}"),
        FactRelationship.to_symbol_id.ilike(f"%.{target_name}"),
    ]

    edges = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.rel_type == "INHERITS",
        or_(*conditions)
    ).all()

    derived_ids = list({e.from_symbol_id for e in edges})
    derived_symbols = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis_id,
        FactSymbol.id.in_(derived_ids)
    ).all() if derived_ids else []

    related: List[TraversedEntity] = []
    for s in derived_symbols:
        related.append(entity_cls(
            name=s.name,
            entity_type=s.symbol_type,
            location=s.file.path if s.file else "",
            line_number=s.line_start,
            relationship_role="subclass",
            data={"symbol_id": s.id}
        ))

    return result_cls(
        query_class=SemanticQueryClass.INHERITS_REVERSE,
        direction=TraversalDirection.REVERSE,
        target_entity=target,
        target_display_name=target_name,
        target_type="class",
        related_entities=related,
        raw_edges=edges,
        explanation=f"Found {len(related)} classes extending / inheriting from '{target_name}'."
    )


def traverse_route_handler(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    route_rec = target if isinstance(target, FactRoute) else None
    if not route_rec:
        return result_cls(
            query_class=SemanticQueryClass.ROUTE_HANDLER,
            direction=TraversalDirection.FORWARD,
            target_entity=target,
            target_display_name=getattr(target, "name", str(target)),
            target_type="unknown",
            related_entities=[],
            explanation="Route lookup requires a valid FactRoute entity.",
        )

    handler_sym = None
    if route_rec.handler_symbol_id:
        handler_sym = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id,
            or_(
                FactSymbol.id == route_rec.handler_symbol_id,
                FactSymbol.id == f"{analysis_id}:{route_rec.handler_symbol_id}",
                FactSymbol.id.ilike(f"%{route_rec.handler_symbol_id.split(':')[-1]}"),
            )
        ).first()

    if not handler_sym:
        # Check EXPOSES relationship
        rel = db.query(FactRelationship).filter(
            FactRelationship.analysis_id == analysis_id,
            or_(
                FactRelationship.to_symbol_id == route_rec.id,
                FactRelationship.to_symbol_id.ilike(f"%{route_rec.path}%"),
            ),
            FactRelationship.rel_type == "EXPOSES"
        ).first()
        if rel:
            handler_sym = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis_id,
                FactSymbol.id == rel.from_symbol_id
            ).first()

    related: List[TraversedEntity] = []
    if handler_sym:
        related.append(entity_cls(
            name=handler_sym.name,
            entity_type=handler_sym.symbol_type,
            location=handler_sym.file.path if handler_sym.file else "",
            line_number=handler_sym.line_start,
            relationship_role="route_handler",
            data={"route_path": route_rec.path, "route_method": route_rec.method}
        ))

    return result_cls(
        query_class=SemanticQueryClass.ROUTE_HANDLER,
        direction=TraversalDirection.FORWARD,
        target_entity=route_rec,
        target_display_name=f"{route_rec.method} {route_rec.path}",
        target_type="route",
        related_entities=related,
        explanation=f"Route '{route_rec.method} {route_rec.path}' is handled by '{handler_sym.name}'." if handler_sym else f"No handler mapped for route '{route_rec.method} {route_rec.path}'."
    )


def traverse_database_access(
    db: Session,
    analysis_id: int,
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    table_name = target.name if isinstance(target, FactDatabaseObject) else getattr(target, "name", str(target))
    table_id = target.symbol_id if isinstance(target, FactDatabaseObject) and target.symbol_id else (target.id if isinstance(target, FactSymbol) else "")

    conditions = [
        FactRelationship.to_symbol_id == table_id,
        FactRelationship.from_symbol_id == table_id,
        FactRelationship.to_symbol_id.ilike(f"%#{table_name}"),
        FactRelationship.from_symbol_id.ilike(f"%#{table_name}"),
        FactRelationship.to_symbol_id.ilike(f"%{table_name}%"),
    ]

    edges = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id,
        FactRelationship.rel_type.in_(["USES", "QUERIES", "READS", "WRITES", "IMPORTS"]),
        or_(*conditions)
    ).all()

    accessing_ids = list({e.from_symbol_id for e in edges if e.from_symbol_id != table_id} | {e.to_symbol_id for e in edges if e.to_symbol_id != table_id})
    accessing_symbols = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis_id,
        FactSymbol.id.in_(accessing_ids)
    ).all() if accessing_ids else []

    accessing_files = db.query(FactFile).filter(
        FactFile.analysis_id == analysis_id,
        FactFile.id.in_(accessing_ids)
    ).all() if accessing_ids else []

    related: List[TraversedEntity] = []
    for s in accessing_symbols:
        related.append(entity_cls(
            name=s.name,
            entity_type=s.symbol_type,
            location=s.file.path if s.file else "",
            line_number=s.line_start,
            relationship_role="accessing_code",
            data={"symbol_id": s.id}
        ))
    for f in accessing_files:
        related.append(entity_cls(
            name=f.path,
            entity_type="file",
            location=f.path,
            line_number=1,
            relationship_role="accessing_file",
            data={"file_id": f.id}
        ))

    db_tables = db.query(FactDatabaseObject).filter(
        FactDatabaseObject.analysis_id == analysis_id,
        or_(
            FactDatabaseObject.symbol_id.in_(accessing_ids),
            FactDatabaseObject.name.in_([e.to_symbol_id.split("#")[-1] for e in edges if e.to_symbol_id != table_id]),
            FactDatabaseObject.name.in_([e.from_symbol_id.split("#")[-1] for e in edges if e.from_symbol_id != table_id]),
        )
    ).all() if edges else []
    for dt in db_tables:
        if dt.name == table_name or dt.symbol_id == table_id:
            continue
        loc = ""
        line_num = 1
        if dt.symbol_id:
            sym = db.query(FactSymbol).filter(
                FactSymbol.analysis_id == analysis_id,
                FactSymbol.id == dt.symbol_id
            ).first()
            if sym:
                loc = sym.file.path if sym.file else ""
                line_num = sym.line_start
        related.append(entity_cls(
            name=dt.name,
            entity_type=dt.object_type or "database_table",
            location=loc,
            line_number=line_num,
            relationship_role="accessed_table",
            data={"table_id": dt.id, "object_type": dt.object_type}
        ))

    resolution = "STATIC_CONFIRMED" if related else "NO_STATIC_EDGE_FOUND"
    return result_cls(
        query_class=SemanticQueryClass.DATABASE_ACCESS,
        direction=TraversalDirection.REVERSE if isinstance(target, FactDatabaseObject) else TraversalDirection.FORWARD,
        target_entity=target,
        target_display_name=table_name,
        target_type="database_table" if isinstance(target, FactDatabaseObject) else "model",
        related_entities=related,
        raw_edges=edges,
        explanation=f"Found {len(related)} database/code relationships for '{table_name}'.",
        resolution=resolution,
    )


def traverse_generic_lookup(
    target: Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject],
    entity_cls,
    result_cls,
) -> RelationshipTraversalResult:
    name = getattr(target, "name", getattr(target, "path", "target"))
    entity_type = "file" if isinstance(target, FactFile) else ("symbol" if isinstance(target, FactSymbol) else "entity")
    loc = target.path if isinstance(target, FactFile) else (target.file.path if getattr(target, "file", None) else "")
    line = target.line_start if hasattr(target, "line_start") else 1

    related = [
        entity_cls(
            name=name,
            entity_type=entity_type,
            location=loc,
            line_number=line,
            relationship_role="matched_entity",
        )
    ]
    return result_cls(
        query_class=SemanticQueryClass.GENERIC_LOOKUP,
        direction=TraversalDirection.FORWARD,
        target_entity=target,
        target_display_name=name,
        target_type=entity_type,
        related_entities=related,
        explanation=f"Located '{name}' ({entity_type}).",
        resolution="STATIC_CONFIRMED",
    )
