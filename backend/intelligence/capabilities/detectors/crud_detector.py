from typing import List, Dict, Set, Tuple
import re
from backend.intelligence.capabilities.detectors.base import BaseCapabilityDetector
from backend.intelligence.capabilities.model import (
    CapabilityCategory,
    CapabilityMemberRole,
    CapabilityDetection,
)
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.enums import EntityType, RelationshipType

class CRUDDetector(BaseCapabilityDetector):
    """
    Detects resource-centric CRUD capabilities by tracing Route -> Handler -> DB Model/Table
    and resolving resource identities. Excludes utility endpoints like /health, /metrics.
    """

    EXCLUDED_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/ping", "/version", "/favicon.ico"}

    def detect(self, rim: RepositoryModel) -> List[CapabilityDetection]:
        # Map route_id -> handler_id
        route_handlers: Dict[str, str] = {}
        for rel in rim.relationships.values():
            if rel.type == RelationshipType.HANDLED_BY:
                route_handlers[rel.source_id] = rel.target_id
            elif rel.type == RelationshipType.EXPOSES:
                route_handlers[rel.target_id] = rel.source_id

        # Build call graph index: caller_id -> target_id list
        call_targets: Dict[str, List[str]] = {}
        for rel in rim.relationships.values():
            if rel.type in (RelationshipType.CALLS, RelationshipType.USES, RelationshipType.HANDLED_BY, RelationshipType.EXPOSES):
                if rel.source_id not in call_targets:
                    call_targets[rel.source_id] = []
                call_targets[rel.source_id].append(rel.target_id)

        # Collect routes with HTTP method
        routes = [e for e in rim.entities.values() if e.type == EntityType.ROUTE or "http_method" in e.metadata or "route_path" in e.metadata]
        
        # Group by resource identity
        resource_routes: Dict[str, List[Tuple[Any, Any, Set[str]]]] = {}  # resource_name -> [(route, handler, db_tables)]

        for route in routes:
            r_path = route.metadata.get("route_path") or route.metadata.get("path") or route.name or ""
            r_method = (route.metadata.get("http_method") or route.metadata.get("method") or "GET").upper()

            # Skip utility/health endpoints
            if r_path.lower() in self.EXCLUDED_PATHS or r_path.lower().startswith("/auth"):
                continue

            handler_id = route.metadata.get("handler_symbol_id") or route_handlers.get(route.id)
            handler = rim.entities.get(handler_id) if handler_id else None

            # Trace DB models/tables from handler
            db_table_ids: Set[str] = set()
            if handler_id:
                reachable = self._get_reachable_symbols(handler_id, rim, call_targets)
                for sid in reachable:
                    ent = rim.entities.get(sid)
                    if ent and (ent.type == EntityType.TABLE or ent.metadata.get("is_db_model")):
                        db_table_ids.add(ent.id)

            # Resolve resource identity
            resource_name = self._resolve_resource_name(r_path, db_table_ids, rim)
            if not resource_name:
                continue

            if resource_name not in resource_routes:
                resource_routes[resource_name] = []
            resource_routes[resource_name].append((route, handler, db_table_ids))

        detections: List[CapabilityDetection] = []

        for resource_name, route_tuples in resource_routes.items():
            # Must have at least one valid resource endpoint
            members: List[Tuple[str, str]] = []
            evidence: List[Dict[str, Any]] = []
            seen_symbols = set()

            for route, handler, db_tables in route_tuples:
                r_method = (route.metadata.get("http_method") or route.metadata.get("method") or "GET").upper()
                r_path = route.metadata.get("route_path") or route.metadata.get("path") or route.name or ""

                if route.id not in seen_symbols:
                    seen_symbols.add(route.id)
                    members.append((route.id, CapabilityMemberRole.ENTRY_POINT.value))
                    evidence.append({
                        "fact_type": "crud_route",
                        "symbol_id": route.id,
                        "details": f"{r_method} {r_path} -> Resource {resource_name}"
                    })

                if handler and handler.id not in seen_symbols:
                    seen_symbols.add(handler.id)
                    members.append((handler.id, CapabilityMemberRole.HANDLER.value))

                for tid in db_tables:
                    if tid not in seen_symbols:
                        seen_symbols.add(tid)
                        members.append((tid, CapabilityMemberRole.TABLE.value))
                        tbl_ent = rim.entities.get(tid)
                        if tbl_ent:
                            evidence.append({
                                "fact_type": "db_table",
                                "symbol_id": tid,
                                "details": f"Target DB Model/Table: {tbl_ent.name}"
                            })

            detections.append(CapabilityDetection(
                rule_id="CRUD_RESOURCE_MANAGEMENT",
                category=CapabilityCategory.CRUD,
                name=f"CRUD: {resource_name}",
                members=members,
                evidence=evidence,
            ))

        return detections

    def _resolve_resource_name(self, path: str, db_table_ids: Set[str], rim: RepositoryModel) -> str:
        # 1. Prefer linked DB Table / Model name
        for tid in db_table_ids:
            ent = rim.entities.get(tid)
            if ent:
                clean_name = ent.name.replace("Model", "").replace("Table", "").strip()
                if clean_name:
                    return clean_name.capitalize()

        # 2. Derive from route path segment e.g. /api/v1/users/{id} -> User
        parts = [p for p in path.split("/") if p and not p.startswith("{") and not p.startswith(":") and p.lower() not in ("api", "v1", "v2")]
        if parts:
            res = parts[0].rstrip("s")  # singularize e.g. users -> user
            if len(res) > 1 and res.lower() not in ("health", "metrics", "docs"):
                return res.capitalize()

        return ""

    def _get_reachable_symbols(self, start_id: str, rim: RepositoryModel, call_targets: Dict[str, List[str]], depth: int = 3) -> Set[str]:
        visited = set()
        queue = [(start_id, 0)]
        while queue:
            curr, d = queue.pop(0)
            if curr in visited or d > depth:
                continue
            visited.add(curr)
            for tgt in call_targets.get(curr, []):
                queue.append((tgt, d + 1))
        return visited
