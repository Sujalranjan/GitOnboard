import uuid
from typing import List, Dict, Tuple, Any
from backend.intelligence.capabilities.model import (
    CapabilityDetection,
    Capability,
    CapabilityCategory,
)

class CapabilityDeduplicator:
    """
    Normalizes and deduplicates raw CapabilityDetections by resource/scope.
    Merges evidence records, member symbols, and rule IDs deterministically.
    """

    def consolidate(self, raw_detections: List[CapabilityDetection]) -> List[Capability]:
        grouped: Dict[str, List[CapabilityDetection]] = {}

        for det in raw_detections:
            # Group key: category + normalized name
            key = f"{det.category.value}:{det.name.strip().lower()}"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(det)

        final_capabilities: List[Capability] = []

        for idx, (key, det_list) in enumerate(grouped.items()):
            primary = det_list[0]
            
            # Combine member lists deterministically
            seen_members: Set[Tuple[str, str]] = set()
            combined_members: List[str] = []
            
            # Combine evidence list deterministically
            seen_ev_keys: Set[Tuple[str, str]] = set()
            combined_evidence: List[Dict[str, Any]] = []
            
            rule_ids: List[str] = []

            for det in det_list:
                if det.rule_id and det.rule_id not in rule_ids:
                    rule_ids.append(det.rule_id)

                for sym_id, role in det.members:
                    mem_key = (sym_id, role)
                    if mem_key not in seen_members:
                        seen_members.add(mem_key)
                        combined_members.append(sym_id)

                for ev in det.evidence:
                    ev_key = (ev.get("fact_type", ""), ev.get("symbol_id", ""))
                    if ev_key not in seen_ev_keys:
                        seen_ev_keys.add(ev_key)
                        combined_evidence.append(ev)

            # Responsibilities summary
            responsibilities = [
                f"Rule [{', '.join(rule_ids)}] detected {primary.name}"
            ]

            keywords = [primary.category.value.lower()] + [r.lower() for r in rule_ids]

            # Stable ID generation based on category & normalized name hash
            cap_id = f"cap:{primary.category.value.lower()}:{uuid.uuid5(uuid.NAMESPACE_DNS, key).hex[:8]}"

            cap = Capability(
                id=cap_id,
                purpose=primary.name,
                category=primary.category,
                responsibilities=responsibilities,
                keywords=keywords,
                representative_sources=combined_members,
                confidence=1.0,
                evidence=combined_evidence,
                rule_id=rule_ids[0] if rule_ids else None,
                metadata={
                    "rule_ids": rule_ids,
                    "member_roles": [{"symbol_id": sym, "role": r} for sym, r in seen_members],
                }
            )

            final_capabilities.append(cap)

        return final_capabilities
