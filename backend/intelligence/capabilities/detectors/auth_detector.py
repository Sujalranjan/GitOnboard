from typing import List, Set, Dict, Any, Tuple
import re
from backend.intelligence.capabilities.detectors.base import BaseCapabilityDetector
from backend.intelligence.capabilities.model import (
    CapabilityCategory,
    CapabilityMemberRole,
    CapabilityDetection,
)
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.enums import EntityType, RelationshipType

class AuthenticationDetector(BaseCapabilityDetector):
    """
    Multi-signal rule-based detector for Authentication capabilities.
    Evaluates exact combinations of route paths, handler call graphs, and DB table access.
    """

    AUTH_KEYWORDS = {"auth", "login", "token", "logout", "register", "signup", "signout", "oauth"}
    VERIFY_PASS_KEYWORDS = {"verify_password", "check_credentials", "verify_hash", "authenticate", "check_password"}
    HASH_PASS_KEYWORDS = {"hash_password", "get_password_hash", "hash", "passlib", "bcrypt", "argon2"}
    JWT_KEYWORDS = {"jwt", "create_access_token", "encode_token", "decode_token", "verify_token"}
    USER_DB_KEYWORDS = {"user", "users", "credential", "credentials", "account", "accounts", "session", "sessions", "token", "tokens"}

    def detect(self, rim: RepositoryModel) -> List[CapabilityDetection]:
        detections: List[CapabilityDetection] = []

        # Find all routes
        routes = [e for e in rim.entities.values() if e.type == EntityType.ROUTE or "http_method" in e.metadata or "route_path" in e.metadata]
        
        # Build call graph index: caller_id -> list of target entity IDs and names
        call_targets: Dict[str, List[str]] = {}
        for rel in rim.relationships.values():
            if rel.type in (RelationshipType.CALLS, RelationshipType.USES, RelationshipType.HANDLED_BY, RelationshipType.EXPOSES):
                if rel.source_id not in call_targets:
                    call_targets[rel.source_id] = []
                call_targets[rel.source_id].append(rel.target_id)

        # Route -> Handler mapping
        route_handlers: Dict[str, str] = {}
        for rel in rim.relationships.values():
            if rel.type == RelationshipType.HANDLED_BY:
                route_handlers[rel.source_id] = rel.target_id
            elif rel.type == RelationshipType.EXPOSES:
                route_handlers[rel.target_id] = rel.source_id

        for route in routes:
            r_path = (route.metadata.get("route_path") or route.metadata.get("path") or route.name or "").lower()
            handler_id = route.metadata.get("handler_symbol_id") or route_handlers.get(route.id)
            handler = rim.entities.get(handler_id) if handler_id else None

            # Trace reachable symbols and DB tables from handler
            reachable_ids = self._get_reachable_symbols(handler_id, rim, call_targets) if handler_id else set()
            reachable_entities = [rim.entities[sid] for sid in reachable_ids if sid in rim.entities]

            # Check reachable symbols for pass verifier, pass hasher, jwt, db tables
            called_func_names = [e.name.lower() for e in reachable_entities]
            db_tables = [e for e in reachable_entities if e.type == EntityType.TABLE or e.metadata.get("is_db_model")]

            has_user_db = any(
                any(kw in e.name.lower() for kw in self.USER_DB_KEYWORDS)
                for e in db_tables
            ) or any(
                any(kw in e.name.lower() for kw in self.USER_DB_KEYWORDS)
                for e in reachable_entities
            )

            has_verify_pass = any(
                any(kw in fname for kw in self.VERIFY_PASS_KEYWORDS)
                for fname in called_func_names
            ) or (handler and any(kw in handler.name.lower() for kw in self.VERIFY_PASS_KEYWORDS))

            has_hash_pass = any(
                any(kw in fname for kw in self.HASH_PASS_KEYWORDS)
                for fname in called_func_names
            ) or (handler and any(kw in handler.name.lower() for kw in self.HASH_PASS_KEYWORDS))

            has_jwt = any(
                any(kw in fname for kw in self.JWT_KEYWORDS)
                for fname in called_func_names
            ) or (handler and any(kw in handler.name.lower() for kw in self.JWT_KEYWORDS))

            # Rule 1: AUTH_CREDENTIAL_LOGIN
            if ("/login" in r_path or "/auth" in r_path or "/token" in r_path) and (has_verify_pass or (handler and "login" in handler.name.lower())) and has_user_db:
                members = [(route.id, CapabilityMemberRole.ENTRY_POINT.value)]
                evidence = [{"fact_type": "route_path", "symbol_id": route.id, "details": f"Path: {r_path}"}]
                if handler:
                    members.append((handler.id, CapabilityMemberRole.HANDLER.value))
                    evidence.append({"fact_type": "handler_calls", "symbol_id": handler.id, "details": f"Handler: {handler.name}"})
                for tbl in db_tables:
                    members.append((tbl.id, CapabilityMemberRole.TABLE.value))
                    evidence.append({"fact_type": "db_table", "symbol_id": tbl.id, "details": f"Table: {tbl.name}"})

                detections.append(CapabilityDetection(
                    rule_id="AUTH_CREDENTIAL_LOGIN",
                    category=CapabilityCategory.AUTHENTICATION,
                    name="Authenticate User Credentials",
                    members=members,
                    evidence=evidence,
                ))

            # Rule 2: AUTH_TOKEN_ENDPOINT
            elif ("/token" in r_path or "/jwt" in r_path or "/oauth" in r_path) and (has_jwt or has_verify_pass):
                members = [(route.id, CapabilityMemberRole.ENTRY_POINT.value)]
                evidence = [{"fact_type": "route_path", "symbol_id": route.id, "details": f"Token route path: {r_path}"}]
                if handler:
                    members.append((handler.id, CapabilityMemberRole.HANDLER.value))
                    evidence.append({"fact_type": "handler_calls", "symbol_id": handler.id, "details": f"Handler: {handler.name}"})

                detections.append(CapabilityDetection(
                    rule_id="AUTH_TOKEN_ENDPOINT",
                    category=CapabilityCategory.AUTHENTICATION,
                    name="Issue Authentication Token",
                    members=members,
                    evidence=evidence,
                ))

            # Rule 3: AUTH_SESSION_LOGOUT
            elif ("/logout" in r_path or "/signout" in r_path):
                members = [(route.id, CapabilityMemberRole.ENTRY_POINT.value)]
                evidence = [{"fact_type": "route_path", "symbol_id": route.id, "details": f"Logout path: {r_path}"}]
                if handler:
                    members.append((handler.id, CapabilityMemberRole.HANDLER.value))

                detections.append(CapabilityDetection(
                    rule_id="AUTH_SESSION_LOGOUT",
                    category=CapabilityCategory.AUTHENTICATION,
                    name="Terminate User Session",
                    members=members,
                    evidence=evidence,
                ))

            # Rule 4: AUTH_REGISTRATION
            elif ("/register" in r_path or "/signup" in r_path) and (has_hash_pass or has_user_db):
                members = [(route.id, CapabilityMemberRole.ENTRY_POINT.value)]
                evidence = [{"fact_type": "route_path", "symbol_id": route.id, "details": f"Registration path: {r_path}"}]
                if handler:
                    members.append((handler.id, CapabilityMemberRole.HANDLER.value))
                for tbl in db_tables:
                    members.append((tbl.id, CapabilityMemberRole.TABLE.value))

                detections.append(CapabilityDetection(
                    rule_id="AUTH_REGISTRATION",
                    category=CapabilityCategory.AUTHENTICATION,
                    name="Register User Account",
                    members=members,
                    evidence=evidence,
                ))

        return detections

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
