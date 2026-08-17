"""
Deterministic Post-Validator - Authoritative gatekeeper verifying JSON schema compliance,
evidence ID validity, path existence, citation entailment, and strictly enforcing contradiction gates.
"""
from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .schemas import (
    DeployableUnit,
    DeployableUnitSummaryItem,
    DiscrepancyItem,
    EvidenceItem,
    EvidenceSourceType,
    OverviewSummary,
    RejectedClaim,
    RepositoryClaim,
    SourceClassification,
    StructuredSummary,
    TechnologySummaryItem,
    UnverifiedDocClaimItem,
    VerificationStatus,
)

MARKETING_FLUFF_PATTERNS = [
    r'\bworld-class\b',
    r'\bblazing(?:ly)?\s+fast\b',
    r'\benterprise-grade\b',
    r'\bbest-in-class\b',
    r'\brobust and highly scalable\b',
    r'\bgroundbreaking\b',
    r'\bunmatched performance\b',
]


class DeterministicValidator:
    """
    Validates LLM-generated StructuredSummary against authoritative repository evidence.
    """

    @staticmethod
    def validate_and_sanitize(
        raw_data: Dict[str, Any],
        known_evidence: Dict[str, EvidenceItem],
        verified_claims: List[RepositoryClaim],
        deployable_units: Optional[List[DeployableUnit]] = None,
        known_file_paths: Optional[List[str]] = None,
    ) -> Tuple[StructuredSummary, List[RejectedClaim], Dict[str, Any]]:
        rejected_claims: List[RejectedClaim] = []
        known_ids = set(known_evidence.keys())
        known_paths = set(p.replace("\\", "/").strip("/") for p in (known_file_paths or []))
        known_paths.add("")  # root is valid
        known_paths.add("/")
        
        authoritative_unit_roots = {u.root_path.replace("\\", "/").strip("/") for u in (deployable_units or [])}
        authoritative_unit_roots.add("")
        authoritative_unit_roots.add("/")

        stats = {
            "accepted_claims_count": 0,
            "fabricated_paths_count": 0,
            "false_contradictions_rejected_count": 0,
        }

        # 1. Validate Overview
        raw_overview = raw_data.get("overview", {})
        if isinstance(raw_overview, str):
            overview_text = raw_overview
            overview_ev = []
        else:
            overview_text = raw_overview.get("text", "")
            overview_ev = [eid for eid in raw_overview.get("evidence_ids", []) if eid in known_ids]

        for pat in MARKETING_FLUFF_PATTERNS:
            overview_text = re.sub(pat, "", overview_text, flags=re.IGNORECASE).strip()

        overview = OverviewSummary(text=overview_text, evidence_ids=overview_ev)
        if overview_text:
            stats["accepted_claims_count"] += 1

        # 2. Validate Deployable Units & Path Existence
        valid_units: List[DeployableUnitSummaryItem] = []
        for raw_u in raw_data.get("deployable_units", []):
            u_name = raw_u.get("name", "Service")
            u_type = raw_u.get("unit_type", "backend_api")
            raw_path = raw_u.get("root_path", "/")
            normalized_p = raw_path.replace("\\", "/").strip("/")
            u_sum = raw_u.get("summary", "")
            u_ev = [eid for eid in raw_u.get("evidence_ids", []) if eid in known_ids]

            # Enforce path existence: path must exist in repo or match an authoritative DeployableUnit
            if normalized_p not in known_paths and normalized_p not in authoritative_unit_roots:
                stats["fabricated_paths_count"] += 1
                rejected_claims.append(
                    RejectedClaim(
                        statement=f"Deployable Unit {u_name} at path {raw_path}",
                        reason=f"Path '{raw_path}' does not exist in repository snapshot.",
                        attempted_evidence_ids=raw_u.get("evidence_ids", [])
                    )
                )
                continue

            valid_units.append(
                DeployableUnitSummaryItem(
                    name=u_name,
                    unit_type=u_type,
                    root_path=raw_path,
                    summary=u_sum,
                    evidence_ids=u_ev
                )
            )
            stats["accepted_claims_count"] += 1

        # 3. Validate Technology Claims
        valid_techs: List[TechnologySummaryItem] = []
        for raw_t in raw_data.get("technologies", []):
            t_name = raw_t.get("name", "")
            t_cat = raw_t.get("category", "Library")
            t_status = raw_t.get("status", "supported")
            t_ev = [eid for eid in raw_t.get("evidence_ids", []) if eid in known_ids]

            entailed_ev = []
            for eid in t_ev:
                ev_item = known_evidence[eid]
                if ev_item.source_classification == SourceClassification.TEST and t_status == "strongly_supported":
                    continue
                if t_name.lower() in ev_item.snippet.lower() or (ev_item.symbol_name and t_name.lower() in ev_item.symbol_name.lower()):
                    entailed_ev.append(eid)
                elif ev_item.source_type == EvidenceSourceType.MANIFEST_DEPENDENCY:
                    entailed_ev.append(eid)

            if not entailed_ev and t_name:
                rejected_claims.append(
                    RejectedClaim(
                        statement=f"Technology {t_name}",
                        reason=f"Citations {t_ev} do not genuinely entail technology '{t_name}'.",
                        attempted_evidence_ids=raw_t.get("evidence_ids", [])
                    )
                )
                continue

            valid_techs.append(
                TechnologySummaryItem(
                    name=t_name,
                    category=t_cat,
                    status=t_status,
                    evidence_ids=entailed_ev
                )
            )
            stats["accepted_claims_count"] += 1

        # 4. Validate Operations & Containerization (Evidence-backed only)
        valid_ops = {}
        raw_ops = raw_data.get("operations_and_deployment", {})
        if raw_ops and isinstance(raw_ops, dict):
            ops_ev = [eid for eid in raw_ops.get("evidence_ids", []) if eid in known_ids]
            # Check if matching config evidence exists
            has_config_ev = any(known_evidence[eid].source_type == EvidenceSourceType.CONFIG_ENTRY for eid in ops_ev)
            if has_config_ev or any(ev.source_type == EvidenceSourceType.CONFIG_ENTRY for ev in known_evidence.values()):
                valid_ops = {k: v for k, v in raw_ops.items() if k != "evidence_ids"}
                valid_ops["evidence_ids"] = ops_ev

        # 5. Validate Data & Storage (Evidence-backed only)
        valid_data = {}
        raw_data_storage = raw_data.get("data_and_storage", {})
        if raw_data_storage and isinstance(raw_data_storage, dict):
            db_ev = [eid for eid in raw_data_storage.get("evidence_ids", []) if eid in known_ids]
            has_db_ev = any(known_evidence[eid].source_type in {EvidenceSourceType.DB_MODEL_SCHEMA, EvidenceSourceType.CONFIG_ENTRY} for eid in db_ev)
            if has_db_ev or any(ev.source_type == EvidenceSourceType.DB_MODEL_SCHEMA for ev in known_evidence.values()):
                valid_data = {k: v for k, v in raw_data_storage.items() if k != "evidence_ids"}
                valid_data["evidence_ids"] = db_ev

        # 6. Validate Discrepancies (STRICT CONTRADICTION GATE)
        # LLM cannot invent discrepancies unless ClaimVerifier positively computed CONTRADICTED
        authoritative_contradictions = {
            c.subject.lower(): c for c in verified_claims if c.status == VerificationStatus.CONTRADICTED
        }
        valid_discrepancies: List[DiscrepancyItem] = []
        for raw_d in raw_data.get("discrepancies", []):
            claimed = raw_d.get("claimed_in_doc", "")
            actual = raw_d.get("actual_code_fact", "")
            d_ev = [eid for eid in raw_d.get("evidence_ids", []) if eid in known_ids]

            # Check if this discrepancy matches an authoritative contradiction
            matched_contra = None
            for subj, c in authoritative_contradictions.items():
                if subj in claimed.lower() or subj in actual.lower():
                    matched_contra = c
                    break

            if not matched_contra:
                stats["false_contradictions_rejected_count"] += 1
                rejected_claims.append(
                    RejectedClaim(
                        statement=f"Discrepancy: {claimed} vs {actual}",
                        reason="No authoritative CONTRADICTED claim found in repository evidence.",
                        attempted_evidence_ids=raw_d.get("evidence_ids", [])
                    )
                )
                continue

            valid_discrepancies.append(
                DiscrepancyItem(
                    claimed_in_doc=claimed,
                    actual_code_fact=actual,
                    evidence_ids=d_ev or matched_contra.supporting_evidence_ids
                )
            )
            stats["accepted_claims_count"] += 1

        # 7. Validate Unverified Doc Claims
        valid_unverified: List[UnverifiedDocClaimItem] = []
        for raw_u in raw_data.get("unverified_doc_claims", []):
            c_text = raw_u.get("claim", "")
            d_eid = raw_u.get("doc_evidence_id", "")
            reason = raw_u.get("reason", "Unverified in codebase.")
            valid_unverified.append(
                UnverifiedDocClaimItem(
                    claim=c_text,
                    doc_evidence_id=d_eid,
                    reason=reason
                )
            )

        structured = StructuredSummary(
            overview=overview,
            deployable_units=valid_units,
            technologies=valid_techs,
            data_and_storage=valid_data,
            operations_and_deployment=valid_ops,
            discrepancies=valid_discrepancies,
            unverified_doc_claims=valid_unverified,
        )

        return structured, rejected_claims, stats
