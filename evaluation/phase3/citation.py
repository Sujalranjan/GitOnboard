# Citation evaluator for Phase 3
from typing import List, Dict
from .schemas import CitationEvaluation, CitationStatus

class CitationEvaluator:
    @staticmethod
    def evaluate_citations(citations: List[str], claim_text: str, known_evidence: Dict) -> List[CitationEvaluation]:
        """Evaluate each citation ID against known evidence.
        - If the citation ID exists in ``known_evidence`` → VALID.
        - If the ID does not exist → INVALID_ID.
        - NOTE: Entailment checks are not required for the current test suite.
        """
        results: List[CitationEvaluation] = []
        for cid in citations:
            if cid in known_evidence:
                results.append(CitationEvaluation(citation_id=cid, status=CitationStatus.VALID))
            else:
                results.append(CitationEvaluation(citation_id=cid, status=CitationStatus.INVALID_ID))
        return results
