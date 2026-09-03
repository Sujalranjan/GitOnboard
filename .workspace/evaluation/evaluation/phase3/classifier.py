"""
Phase 3 Claim Support Classifier - Classifies atomic claims against authoritative repository
evidence and AST without secondary LLMs.
"""
from __future__ import annotations
import os
import re
from typing import Dict, List, Optional, Set

from backend.summary.schemas import (
    DeployableUnit,
    EvidenceItem,
    EvidenceSourceType,
    RepositoryClaim,
    SourceClassification,
    VerificationStatus,
)
from .schemas import (
    AtomicClaim,
    ClaimType,
    HallucinationCategory,
    SupportStatus,
    CitationStatus,
)
from .citation import CitationEvaluator


class ClaimClassifier:
    """
    Classifies atomic claims deterministically against repository evidence.
    """

    @classmethod
    def classify_claim(
        cls,
        claim: AtomicClaim,
        known_evidence: Dict[str, EvidenceItem],
        verified_claims: List[RepositoryClaim],
        known_file_paths: List[str],
        deployable_units: Optional[List[DeployableUnit]] = None,
        ground_truth: Optional[Dict[str, Any]] = None,
    ) -> AtomicClaim:
        text_lower = claim.text.lower()
        
        # 1. Evaluate Citations (Tracked separately under citation quality)
        if claim.citations:
            claim.citation_evaluations = CitationEvaluator.evaluate_citations(
                citations=claim.citations,
                claim_text=claim.text,
                known_evidence=known_evidence,
            )


        # Normalize known file paths
        normalized_files = set(p.replace("\\", "/").strip("/") for p in known_file_paths)
        normalized_dirs = set()
        for p in normalized_files:
            parts = p.split("/")
            for i in range(1, len(parts)):
                normalized_dirs.add("/".join(parts[:i]))
        normalized_dirs.add("")
        normalized_dirs.add("/")

        authoritative_unit_roots = {u.root_path.replace("\\", "/").strip("/") for u in (deployable_units or [])}
        authoritative_unit_roots.add("")
        authoritative_unit_roots.add("/")

        authoritative_techs = set()
        for vc in verified_claims:
            authoritative_techs.add(vc.subject.lower())
        for ev in known_evidence.values():
            if ev.symbol_name:
                authoritative_techs.add(ev.symbol_name.lower())
            if ev.context_metadata and "dependency" in ev.context_metadata:
                authoritative_techs.add(str(ev.context_metadata["dependency"]).lower())

        ground_truth = ground_truth or {}
        gt_langs = set(l.lower() for l in ground_truth.get("languages", []))
        gt_frameworks = set(f.lower() for f in ground_truth.get("frameworks", []))
        gt_dbs = set(d.lower() for d in ground_truth.get("databases", []))
        gt_all_techs = gt_langs | gt_frameworks | gt_dbs | authoritative_techs

        # 2. Path & File Claims
        if claim.claim_type in {ClaimType.PATH, ClaimType.FILE}:
            # Extract all quoted strings from claim
            quoted_strings = re.findall(r"['\"]([^'\"]+)['\"]", claim.text)
            target_path = ""
            # Prioritize quoted string following 'path' or 'file', or containing '/' or '.'
            for q in quoted_strings:
                if "/" in q or "\\" in q or "." in q or q in normalized_dirs or q in normalized_files:
                    target_path = q
                    break
            if not target_path and quoted_strings:
                target_path = quoted_strings[-1]
            if not target_path:
                for word in claim.text.split():
                    if "/" in word or "\\" in word or "." in word:
                        target_path = word.strip(" '\".,;:()")
                        break

            norm_target = target_path.replace("\\", "/").strip("/")
            
            # Check if path or file exists
            if norm_target in normalized_files or norm_target in normalized_dirs or norm_target in authoritative_unit_roots:
                claim.support_status = SupportStatus.SUPPORTED
                claim.evidence_detail = f"Path/File '{target_path}' verified in repository snapshot."
            else:
                claim.support_status = SupportStatus.UNSUPPORTED
                if "." in norm_target.split("/")[-1]:
                    claim.hallucination_categories.append(HallucinationCategory.FABRICATED_FILE)
                else:
                    claim.hallucination_categories.append(HallucinationCategory.FABRICATED_PATH)
                claim.evidence_detail = f"Path/File '{target_path}' does NOT exist in repository snapshot."
            return claim

        # 3. Technology / Dependency / Database Claims
        if claim.claim_type in {ClaimType.TECHNOLOGY, ClaimType.DEPENDENCY, ClaimType.DATABASE}:
            tech_match = re.search(r"uses\s+([a-zA-Z0-9_\-\.]+)", text_lower) or re.search(r"database\s+['\"]?([a-zA-Z0-9_\-\.]+)['\"]?", text_lower)
            target_tech = tech_match.group(1) if tech_match else ""
            if not target_tech:
                for word in re.findall(r'[a-zA-Z0-9_\-\.]+', text_lower):
                    if word in gt_all_techs:
                        target_tech = word
                        break

            # Check for known contradiction (e.g. SQLite claimed when PostgreSQL is configured)
            contradicted_claims = [c for c in verified_claims if c.status == VerificationStatus.CONTRADICTED]
            for cc in contradicted_claims:
                if (target_tech and target_tech in cc.subject.lower()) or (cc.subject.lower() in text_lower):
                    claim.support_status = SupportStatus.CONTRADICTED
                    claim.hallucination_categories.append(HallucinationCategory.INCORRECT_TECHNOLOGY)
                    claim.evidence_detail = f"Technology '{target_tech or cc.subject}' is explicitly CONTRADICTED by codebase evidence."
                    return claim

            # Check if supported by authoritative evidence or ground truth
            is_supported = False
            if target_tech:
                is_supported = (target_tech in gt_all_techs or any(target_tech in k for k in gt_all_techs))
            else:
                is_supported = any(tech in text_lower for tech in gt_all_techs)

            if is_supported:
                claim.support_status = SupportStatus.SUPPORTED
                claim.evidence_detail = f"Technology verified in manifest dependencies, AST, or repository config."
            else:
                # If claim asserts a concrete unsupported framework/library
                unsupported_known = ["django", "flask", "fastapi", "spring", "rails", "express", "sqlite", "postgres", "mysql", "mongodb", "redis", "kafka", "rabbitmq"]
                if any(kw in text_lower for kw in unsupported_known if kw not in gt_all_techs):
                    claim.support_status = SupportStatus.UNSUPPORTED
                    claim.hallucination_categories.append(HallucinationCategory.INCORRECT_TECHNOLOGY)
                    claim.evidence_detail = f"Technology assertion not found in repository manifests or source imports."
                else:
                    claim.support_status = SupportStatus.UNRESOLVED
                    claim.evidence_detail = f"Generic technology claim cannot be strictly validated from AST alone."
            return claim

        # 4. Symbol Claims
        if claim.claim_type == ClaimType.SYMBOL:
            sym_match = re.search(r"['\"]([a-zA-Z0-9_]+)['\"]", claim.text)
            target_sym = sym_match.group(1) if sym_match else ""
            if target_sym and any(ev.symbol_name == target_sym for ev in known_evidence.values()):
                claim.support_status = SupportStatus.SUPPORTED
                claim.evidence_detail = f"Symbol '{target_sym}' found in AST index."
            else:
                claim.support_status = SupportStatus.UNSUPPORTED
                claim.hallucination_categories.append(HallucinationCategory.FABRICATED_SYMBOL)
                claim.evidence_detail = f"Symbol '{target_sym}' not found in AST index."
            return claim

        # 5. Contradiction Claims (Discrepancies)
        if claim.claim_type == ClaimType.CONTRADICTION:
            # Check if there is an authoritative contradiction computed by ClaimVerifier
            authoritative_contradictions = [c for c in verified_claims if c.status == VerificationStatus.CONTRADICTED]
            matched = False
            for ac in authoritative_contradictions:
                if ac.subject.lower() in text_lower:
                    matched = True
                    break

            if matched:
                claim.support_status = SupportStatus.SUPPORTED
                claim.evidence_detail = "Discrepancy verified against authoritative contradiction analysis."
            else:
                claim.support_status = SupportStatus.UNSUPPORTED
                claim.hallucination_categories.append(HallucinationCategory.FALSE_CONTRADICTION)
                claim.evidence_detail = "False contradiction: Writer invented a discrepancy not backed by evidence."
            return claim

        # 6. Default / Architecture / Behavior / Other
        # If valid citations exist and entail the statement, mark SUPPORTED
        if claim.citations and all(ce.status == CitationStatus.VALID for ce in claim.citation_evaluations):
            claim.support_status = SupportStatus.SUPPORTED
            claim.evidence_detail = "Verified via valid and entailed evidence citations."
        else:
            # When evidence is neutral or descriptive, mark UNRESOLVED (not hallucination)
            claim.support_status = SupportStatus.UNRESOLVED
            claim.evidence_detail = "Descriptive claim without discrete AST verification target."

        return claim
