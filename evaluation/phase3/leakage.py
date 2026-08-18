"""
Phase 3 Leakage & False Rejection Analyzer - Executes the existing production
DeterministicValidator and measures whether invalid claims leak into final summary.
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.summary.validator import DeterministicValidator
from backend.summary.schemas import DeployableUnit, EvidenceItem, RejectedClaim, RepositoryClaim, StructuredSummary
from .schemas import (
    AtomicClaim,
    CitationQualityMetrics,
    CitationStatus,
    ClaimType,
    FinalSummaryStatus,
    RepositoryPhase3Result,
    SupportStatus,
    ValidatorDecision,
)


class LeakageAnalyzer:
    """
    Executes DeterministicValidator on raw Writer output and computes leakage & false rejection metrics.
    """

    @classmethod
    def analyze_repository(
        cls,
        repo_id: str,
        raw_writer_output: Dict[str, Any],
        claims: List[AtomicClaim],
        known_evidence: Dict[str, EvidenceItem],
        verified_claims: List[RepositoryClaim],
        deployable_units: Optional[List[DeployableUnit]] = None,
        known_file_paths: Optional[List[str]] = None,
    ) -> RepositoryPhase3Result:
        # 1. Execute the EXACT production DeterministicValidator
        sanitized_summary, rejected_claims, validator_stats = DeterministicValidator.validate_and_sanitize(
            raw_data=raw_writer_output,
            known_evidence=known_evidence,
            verified_claims=verified_claims,
            deployable_units=deployable_units,
            known_file_paths=known_file_paths,
        )

        final_summary_json = sanitized_summary.model_dump()
        final_summary_text = json.dumps(final_summary_json).lower()

        # Build lookup of rejected statements / reasons
        rejected_reasons: Dict[str, str] = {}
        for rc in rejected_claims:
            stmt_clean = rc.statement.lower()
            rejected_reasons[stmt_clean] = rc.reason

        # 2. Map decisions to atomic claims
        for claim in claims:
            c_text_lower = claim.text.lower()

            # Check if this claim matches any rejected claim
            matched_rejection = None
            for stmt, reason in rejected_reasons.items():
                keywords = [k for k in stmt.split() if len(k) > 3 and k not in {"deployable", "unit", "path", "technology", "discrepancy"}]
                if stmt in c_text_lower or (keywords and all(k in c_text_lower for k in keywords)):
                    matched_rejection = reason
                    break

            if matched_rejection:
                claim.validator = ValidatorDecision(decision="REJECT", reason=matched_rejection)
            else:
                claim.validator = ValidatorDecision(decision="ACCEPT", reason=None)

            # Check if claim target is genuinely present in the final published summary
            if claim.validator.decision == "REJECT":
                claim.final_summary = FinalSummaryStatus(present=False)
            elif claim.claim_type == ClaimType.TECHNOLOGY:
                t_names = [t.get("name", "").lower() for t in final_summary_json.get("technologies", [])]
                match_tech = re.search(r"uses\s+([a-zA-Z0-9_\-\.]+)", c_text_lower)
                t_target = match_tech.group(1) if match_tech else ""
                tech_in_final = (t_target in t_names) if t_target else any(t in c_text_lower for t in t_names if t)
                claim.final_summary = FinalSummaryStatus(present=tech_in_final)
            elif claim.claim_type == ClaimType.PATH:
                u_paths = [u.get("root_path", "").strip("/").lower() for u in final_summary_json.get("deployable_units", [])]
                quoted = re.findall(r"['\"]([^'\"]+)['\"]", claim.text)
                target_p = quoted[-1].strip("/").lower() if quoted else ""
                path_in_final = (target_p in u_paths) if target_p else False
                claim.final_summary = FinalSummaryStatus(present=path_in_final)
            elif claim.claim_type == ClaimType.CONTRADICTION:
                discs = final_summary_json.get("discrepancies", [])
                disc_in_final = len(discs) > 0 and any(d.get("claimed_in_doc", "").lower() in c_text_lower for d in discs)
                claim.final_summary = FinalSummaryStatus(present=disc_in_final)
            else:
                claim.final_summary = FinalSummaryStatus(present=(claim.validator.decision == "ACCEPT"))

        # 3. Calculate per-repository metrics
        total = len(claims)
        supported = sum(1 for c in claims if c.support_status == SupportStatus.SUPPORTED)
        unsupported = sum(1 for c in claims if c.support_status == SupportStatus.UNSUPPORTED)
        contradicted = sum(1 for c in claims if c.support_status == SupportStatus.CONTRADICTED)
        unresolved = sum(1 for c in claims if c.support_status == SupportStatus.UNRESOLVED)

        evaluable = supported + unsupported + contradicted
        hallucination_rate = ((unsupported + contradicted) / total * 100.0) if total > 0 else 0.0
        conditional_hallucination_rate = ((unsupported + contradicted) / evaluable * 100.0) if evaluable > 0 else 0.0
        unsupported_rate = (unsupported / total * 100.0) if total > 0 else 0.0
        contradiction_rate = (contradicted / total * 100.0) if total > 0 else 0.0

        # Category counts (Content Hallucinations)
        all_cats = [cat for c in claims for cat in c.hallucination_categories]
        fab_paths = all_cats.count("FABRICATED_PATH")
        fab_files = all_cats.count("FABRICATED_FILE")
        fab_symbols = all_cats.count("FABRICATED_SYMBOL")
        false_contras = all_cats.count("FALSE_CONTRADICTION")
        inc_techs = all_cats.count("INCORRECT_TECHNOLOGY")

        # Citation Quality Metrics (Tracked separately from content hallucination)
        all_citation_evals = [ce for c in claims for ce in c.citation_evaluations]
        total_cites = len(all_citation_evals)
        valid_cites = sum(1 for ce in all_citation_evals if ce.status == CitationStatus.VALID)
        invalid_id_cites = sum(1 for ce in all_citation_evals if ce.status == CitationStatus.INVALID_ID)
        unentailed_cites = sum(1 for ce in all_citation_evals if ce.status == CitationStatus.NOT_ENTAILED)
        cite_validity_rate = (valid_cites / total_cites * 100.0) if total_cites > 0 else 100.0
        cite_entailment_rate = (valid_cites / (valid_cites + unentailed_cites) * 100.0) if (valid_cites + unentailed_cites) > 0 else 100.0

        citation_quality = CitationQualityMetrics(
            total_citations=total_cites,
            valid_citations=valid_cites,
            invalid_id_citations=invalid_id_cites,
            unentailed_citations=unentailed_cites,
            validity_rate=round(cite_validity_rate, 2),
            entailment_rate=round(cite_entailment_rate, 2),
        )

        # Invalid claims before validator
        invalid_claims = [c for c in claims if c.support_status in {SupportStatus.UNSUPPORTED, SupportStatus.CONTRADICTED}]
        invalid_count = len(invalid_claims)
        invalid_rejected = sum(1 for c in invalid_claims if c.validator.decision == "REJECT")
        invalid_leaked = sum(1 for c in invalid_claims if c.final_summary.present is True)
        leakage_rate = (invalid_leaked / invalid_count * 100.0) if invalid_count > 0 else 0.0

        # Refined False Rejection Definition:
        # A false rejection occurs when a claim is SUPPORTED AND correctly evidenced (all citations VALID or verified directly),
        # but is nonetheless rejected by the validator.
        supported_claims = [c for c in claims if c.support_status == SupportStatus.SUPPORTED]
        supp_count = len(supported_claims)

        correctly_evidenced_supported = [
            c for c in supported_claims
            if not c.citations or all(ce.status == CitationStatus.VALID for ce in c.citation_evaluations)
        ]
        correctly_evidenced_count = len(correctly_evidenced_supported)
        correctly_evidenced_rejected = sum(
            1 for c in correctly_evidenced_supported if c.validator.decision == "REJECT"
        )
        false_rejection_rate = (
            (correctly_evidenced_rejected / correctly_evidenced_count * 100.0)
            if correctly_evidenced_count > 0 else 0.0
        )

        return RepositoryPhase3Result(
            repository=repo_id,
            total_claims=total,
            evaluable_claims=evaluable,
            supported=supported,
            unsupported=unsupported,
            contradicted=contradicted,
            unresolved=unresolved,
            hallucination_rate=round(hallucination_rate, 2),
            conditional_hallucination_rate=round(conditional_hallucination_rate, 2),
            unsupported_rate=round(unsupported_rate, 2),
            contradiction_rate=round(contradiction_rate, 2),
            fabricated_paths=fab_paths,
            fabricated_files=fab_files,
            fabricated_symbols=fab_symbols,
            false_contradictions=false_contras,
            incorrect_technologies=inc_techs,
            citation_quality=citation_quality,
            invalid_claims_before_validator=invalid_count,
            invalid_claims_rejected=invalid_rejected,
            invalid_claims_leaked=invalid_leaked,
            leakage_rate=round(leakage_rate, 2),
            supported_claims=supp_count,
            supported_correctly_evidenced_claims=correctly_evidenced_count,
            supported_correctly_evidenced_rejected=correctly_evidenced_rejected,
            false_rejection_rate=round(false_rejection_rate, 2),
            claims=claims,
        )
