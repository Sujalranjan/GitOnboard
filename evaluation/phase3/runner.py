# Minimal Phase3Runner placeholder
from typing import List, Dict
from .extractor import extract_claims
from .classifier import ClaimClassifier
from .citation import CitationEvaluator
from .leakage import LeakageAnalyzer

class Phase3Runner:
    @staticmethod
    def run(
        raw_writer_output: Dict,
        repository: str,
        known_evidence: Dict,
        verified_claims: List,
        known_file_paths: List[str],
    ) -> Dict:
        """Execute the Phase 3 evaluation pipeline.
        Returns a dict with keys ``claims`` and ``leakage`` for the test suite.
        """
        claims = extract_claims(raw_writer_output, repository)
        # Classify each claim (mutates claim objects in place for simplicity)
        for claim in claims:
            result = ClaimClassifier.classify_claim(
                claim=claim,
                known_evidence=known_evidence,
                verified_claims=verified_claims,
                known_file_paths=known_file_paths,
            )
            # Attach classification result attributes for later inspection if needed
            claim.support_status = result.support_status
            claim.hallucination_categories = result.hallucination_categories
            claim.citation_evaluations = result.citation_evaluations
        leakage = LeakageAnalyzer.analyze_repository(
            repo_id=repository,
            raw_writer_output=raw_writer_output,
            claims=claims,
            known_evidence=known_evidence,
            verified_claims=verified_claims,
            known_file_paths=known_file_paths,
        )
        return {"claims": claims, "leakage": leakage}
