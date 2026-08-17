"""
Claim Verification Engine - Resolves multi-source evidence lifecycles and deterministically
computes verification statuses (STRONGLY_SUPPORTED, SUPPORTED, DECLARED_UNUSED, DOCUMENTED_UNVERIFIED, CONTRADICTED).
"""
from __future__ import annotations
import re
from typing import Dict, List, Optional, Set, Tuple

from .schemas import (
    ClaimCategory,
    EvidenceItem,
    EvidenceSourceType,
    RepositoryClaim,
    SourceClassification,
    TechnologyLifecycle,
    VerificationStatus,
)
from .chunker import DocChunk


KNOWN_MUTUALLY_EXCLUSIVE_TECHNOLOGIES: Dict[str, Set[str]] = {
    "sqlite": {"postgresql", "postgres", "mysql", "mariadb", "oracle", "mongodb"},
    "postgresql": {"sqlite"},
    "mysql": {"sqlite"},
}


class ClaimVerifier:
    """
    Evaluates evidence dimensions deterministically and computes verified claims.
    """

    @staticmethod
    def verify_technology_claims(
        evidence_items: List[EvidenceItem],
        doc_chunks: List[DocChunk],
        source_code_texts: Optional[Dict[str, str]] = None,
    ) -> List[RepositoryClaim]:
        source_code_texts = source_code_texts or {}
        claims: List[RepositoryClaim] = []

        # Group evidence by normalized technology subject
        evidence_by_tech: Dict[str, List[EvidenceItem]] = {}
        for ev in evidence_items:
            symbols = []
            if ev.symbol_name:
                symbols.append(ev.symbol_name.lower().strip())
            if ev.context_metadata:
                if 'dependency' in ev.context_metadata:
                    symbols.append(str(ev.context_metadata['dependency']).lower().strip())
                if 'image' in ev.context_metadata:
                    symbols.append(str(ev.context_metadata['image']).lower().strip())
            for s in symbols:
                # normalize psycopg2 -> postgresql / postgres
                if 'psycopg' in s or 'postgres' in s:
                    evidence_by_tech.setdefault('postgresql', []).append(ev)
                    evidence_by_tech.setdefault('postgres', []).append(ev)
                else:
                    evidence_by_tech.setdefault(s, []).append(ev)

        # Check doc chunks for mentioned technologies
        all_doc_text = " ".join(c.text.lower() for c in doc_chunks)

        # Set of all candidate technologies
        candidate_techs = set(evidence_by_tech.keys())
        # Add common technology keywords found in docs
        for common_kw in ["sqlite", "postgresql", "postgres", "redis", "fastapi", "django", "stripe", "celery", "kafka", "rabbitmq", "mongodb", "mysql"]:
            if re.search(rf'\b{common_kw}\b', all_doc_text):
                candidate_techs.add(common_kw)

        claim_idx = 0
        for tech in sorted(candidate_techs):
            claim_idx += 1
            ev_list = evidence_by_tech.get(tech, [])
            
            is_declared = any(e.source_type == EvidenceSourceType.MANIFEST_DEPENDENCY for e in ev_list)
            is_configured = any(e.source_type == EvidenceSourceType.CONFIG_ENTRY for e in ev_list)
            is_documented = bool(re.search(rf'\b{tech}\b', all_doc_text))
            
            # Check for application imports / usages in source code
            app_usages = [
                e for e in ev_list
                if e.source_classification == SourceClassification.APPLICATION
                and e.source_type in {EvidenceSourceType.IMPORT_STATEMENT, EvidenceSourceType.AST_INSTANTIATION, EvidenceSourceType.AST_CALL}
            ]
            
            # Also check text of application source files if raw AST was sparse
            if not app_usages:
                for f_path, f_code in source_code_texts.items():
                    if EvidenceExtractor.classify_source(f_path) == SourceClassification.APPLICATION:
                        if re.search(rf'\bimport\s+{tech}\b|from\s+{tech}\b|{tech}\.', f_code.lower()):
                            is_declared = is_declared or True
                            app_usages.append(
                                EvidenceItem(
                                    evidence_id=f"ev_app_{claim_idx:03d}",
                                    source_type=EvidenceSourceType.IMPORT_STATEMENT,
                                    source_classification=SourceClassification.APPLICATION,
                                    file_path=f_path,
                                    snippet=f"import {tech}",
                                    symbol_name=tech
                                )
                            )
                            break

            is_imported = bool(app_usages)
            is_used = bool(app_usages)
            app_usage_detected = bool(app_usages)
            active_usage_confirmed = is_declared and app_usage_detected

            lifecycle = TechnologyLifecycle(
                is_declared=is_declared,
                is_imported=is_imported,
                is_instantiated=is_used,
                is_used=is_used,
                is_configured=is_configured,
                is_runtime_integrated=active_usage_confirmed,
                is_documented=is_documented,
                application_usage_detected=app_usage_detected,
                active_usage_confirmed=active_usage_confirmed,
            )

            # Determine Verification Status
            status = VerificationStatus.UNKNOWN
            contra_ids = []
            
            # 1. Check for Positive Contradictions (e.g. Doc says SQLite, code uses Postgres)
            if is_documented and not is_declared and not is_configured and not app_usage_detected:
                # Check if a mutually exclusive alternative exists in code
                exclusive_alts = KNOWN_MUTUALLY_EXCLUSIVE_TECHNOLOGIES.get(tech, set())
                active_conflicts = [
                    alt for alt in exclusive_alts
                    if alt in evidence_by_tech and any(e.source_classification in {SourceClassification.APPLICATION, SourceClassification.CONFIGURATION} for e in evidence_by_tech[alt])
                ]
                if active_conflicts:
                    status = VerificationStatus.CONTRADICTED
                    for alt in active_conflicts:
                        contra_ids.extend(e.evidence_id for e in evidence_by_tech[alt])
                else:
                    status = VerificationStatus.DOCUMENTED_UNVERIFIED

            elif active_usage_confirmed:
                status = VerificationStatus.STRONGLY_SUPPORTED
            elif app_usage_detected or is_configured:
                status = VerificationStatus.SUPPORTED
            elif is_declared and not app_usage_detected and not is_configured:
                status = VerificationStatus.DECLARED_UNUSED
            elif is_configured and not app_usage_detected:
                status = VerificationStatus.CONFIGURED_ONLY
            elif is_documented and not app_usage_detected:
                status = VerificationStatus.DOCUMENTED_UNVERIFIED

            supporting_ids = [e.evidence_id for e in ev_list]

            claims.append(
                RepositoryClaim(
                    claim_id=f"claim_tech_{claim_idx:03d}",
                    category=ClaimCategory.TECHNOLOGY_DEPENDENCY,
                    subject=tech.capitalize(),
                    statement=f"{tech.capitalize()} is configured or referenced in the repository.",
                    status=status,
                    lifecycle=lifecycle,
                    supporting_evidence_ids=supporting_ids,
                    contradicting_evidence_ids=contra_ids,
                    verification_reasoning=f"lifecycle: declared={is_declared}, app_usage={app_usage_detected}, config={is_configured}, doc={is_documented}"
                )
            )

        return claims


# Import for helper function inside verifier
from .extractor import EvidenceExtractor
