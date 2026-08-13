from typing import List, Dict, Set, Tuple
from backend.intelligence.capabilities.detectors.base import BaseCapabilityDetector
from backend.intelligence.capabilities.model import (
    CapabilityCategory,
    CapabilityMemberRole,
    CapabilityDetection,
)
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.enums import EntityType, RelationshipType

class FileUploadDetector(BaseCapabilityDetector):
    """
    Detects File Upload capabilities by requiring HTTP route + UploadFile/File(...) parameter
    + file handling. Explicitly excludes internal open() calls without HTTP upload route.
    """

    UPLOAD_PARAM_KEYWORDS = {"uploadfile", "file", "bytes", "multipart"}
    UPLOAD_PATH_KEYWORDS = {"upload", "file", "attachment", "import"}

    def detect(self, rim: RepositoryModel) -> List[CapabilityDetection]:
        detections: List[CapabilityDetection] = []

        # Route -> Handler mapping
        route_handlers: Dict[str, str] = {}
        for rel in rim.relationships.values():
            if rel.type == RelationshipType.HANDLED_BY:
                route_handlers[rel.source_id] = rel.target_id
            elif rel.type == RelationshipType.EXPOSES:
                route_handlers[rel.target_id] = rel.source_id

        routes = [e for e in rim.entities.values() if e.type == EntityType.ROUTE or "http_method" in e.metadata or "route_path" in e.metadata]

        for route in routes:
            r_path = (route.metadata.get("route_path") or route.metadata.get("path") or route.name or "").lower()
            handler_id = route.metadata.get("handler_symbol_id") or route_handlers.get(route.id)
            handler = rim.entities.get(handler_id) if handler_id else None

            # Check route path & handler parameters for UploadFile / File / multipart
            has_upload_path = any(kw in r_path for kw in self.UPLOAD_PATH_KEYWORDS)
            
            params = handler.metadata.get("parameters", []) if handler else []
            param_str = str(params).lower()
            
            has_upload_param = any(kw in param_str for kw in self.UPLOAD_PARAM_KEYWORDS) or "uploadfile" in param_str or "file(" in param_str

            if has_upload_param or (has_upload_path and handler and ("file" in handler.name.lower() or "upload" in handler.name.lower())):
                rule_id = "FILE_UPLOAD_UPLOADFILE" if "uploadfile" in param_str else "FILE_UPLOAD_MULTIPART"
                members: List[Tuple[str, str]] = [(route.id, CapabilityMemberRole.ENTRY_POINT.value)]
                evidence = [{
                    "fact_type": "upload_route",
                    "symbol_id": route.id,
                    "details": f"File upload route path: {r_path}"
                }]

                if handler:
                    members.append((handler.id, CapabilityMemberRole.HANDLER.value))
                    evidence.append({
                        "fact_type": "upload_handler",
                        "symbol_id": handler.id,
                        "details": f"Upload handler {handler.name} with params={params}"
                    })

                detections.append(CapabilityDetection(
                    rule_id=rule_id,
                    category=CapabilityCategory.FILE_UPLOAD,
                    name=f"File Upload: {route.name}",
                    members=members,
                    evidence=evidence,
                ))

        return detections
