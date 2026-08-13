import uuid
from typing import List, Dict
from ..rim.repository import RepositoryModel
from .model import (
    Capability,
    CapabilityDetection,
    CapabilityRelationship,
    CapabilityRelationshipType,
)
from .detectors import (
    AuthenticationDetector,
    CRUDDetector,
    BackgroundTaskDetector,
    FileUploadDetector,
    CapabilityDeduplicator,
)

class CapabilityBuilderEngine:
    """
    Deterministic rule-based Capability Builder Engine for Layer 6.
    Replaces legacy candidate/taxonomy inference with explicit multi-fact graph detectors.
    """

    def __init__(self):
        self.detectors = [
            AuthenticationDetector(),
            CRUDDetector(),
            BackgroundTaskDetector(),
            FileUploadDetector(),
        ]
        self.deduplicator = CapabilityDeduplicator()

    def run(self, model: RepositoryModel) -> RepositoryModel:
        if not hasattr(model, "capabilities") or model.capabilities is None:
            model.capabilities = {}
        if not hasattr(model, "capability_relationships") or model.capability_relationships is None:
            model.capability_relationships = {}

        raw_detections: List[CapabilityDetection] = []

        # 1. Run all multi-fact deterministic detectors
        for detector in self.detectors:
            detections = detector.detect(model)
            raw_detections.extend(detections)

        # 2. Consolidate and deduplicate detections into final Capabilities
        final_capabilities = self.deduplicator.consolidate(raw_detections)

        model.capabilities = {cap.id: cap for cap in final_capabilities}

        # 3. Dependency Projection
        # Map raw entity CALLS/USES edges to Capability DEPENDS_ON edges
        entity_to_cap: Dict[str, str] = {}
        for cap in final_capabilities:
            for src in cap.representative_sources:
                entity_to_cap[src] = cap.id

        added_edges = set()
        for rel in model.relationships.values():
            rel_type_str = rel.type.value if hasattr(rel.type, "value") else str(rel.type)
            if rel_type_str in ("CALLS", "USES", "EXPOSES"):
                src_cap_id = entity_to_cap.get(rel.source_id)
                tgt_cap_id = entity_to_cap.get(rel.target_id)

                if src_cap_id and tgt_cap_id and src_cap_id != tgt_cap_id:
                    edge_key = f"{src_cap_id}->{tgt_cap_id}"
                    if edge_key not in added_edges:
                        added_edges.add(edge_key)

                        rel_type = CapabilityRelationshipType.DEPENDS_ON
                        if rel_type_str == "USES" and model.capabilities[tgt_cap_id].category.value == "PERSISTENCE":
                            rel_type = CapabilityRelationshipType.PERSISTS

                        cap_rel = CapabilityRelationship(
                            id=f"crel:{uuid.uuid4().hex[:8]}",
                            type=rel_type,
                            source_id=src_cap_id,
                            target_id=tgt_cap_id,
                            metadata={"inferred_from": rel.id}
                        )
                        model.capability_relationships[cap_rel.id] = cap_rel

        return model
