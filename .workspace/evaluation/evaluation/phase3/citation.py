"""
Phase 3 Citation Evaluator - Deterministically evaluates evidence ID validity and entailment
against authoritative repository evidence.
"""
from __future__ import annotations
import re
from typing import Dict, List, Optional

from backend.summary.schemas import EvidenceItem, EvidenceSourceType, SourceClassification
from .schemas import CitationEvaluation, CitationStatus


class CitationEvaluator:
    """
    Evaluates evidence ID validity and entailment for atomic claims without secondary LLMs.
    """

    @staticmethod
    def evaluate_citations(
        citations: List[str],
        claim_text: str,
        known_evidence: Dict[str, EvidenceItem],
    ) -> List[CitationEvaluation]:
        evaluations: List[CitationEvaluation] = []

        for eid in citations:
            if eid not in known_evidence:
                evaluations.append(
                    CitationEvaluation(
                        evidence_id=eid,
                        status=CitationStatus.INVALID_ID,
                        detail=f"Evidence ID '{eid}' does not exist in repository evidence index."
                    )
                )
                continue

            ev = known_evidence[eid]
            claim_lower = claim_text.lower()
            snippet_lower = (ev.snippet or "").lower()
            symbol_lower = (ev.symbol_name or "").lower()
            file_lower = (ev.file_path or "").lower()

            # Test-only evidence cannot entail strong application production claims
            if ev.source_classification == SourceClassification.TEST and "strongly_supported" in claim_lower:
                evaluations.append(
                    CitationEvaluation(
                        evidence_id=eid,
                        status=CitationStatus.NOT_ENTAILED,
                        detail=f"Evidence '{eid}' comes from test file '{ev.file_path}', which cannot entail application production usage."
                    )
                )
                continue

            # Check if key words from claim appear in snippet, symbol, or file path
            # Extract key nouns/identifiers from claim
            words = [w for w in re.findall(r'[a-zA-Z0-9_\-\.]+', claim_lower) if len(w) > 2 and w not in {"the", "and", "uses", "project", "for", "with", "status", "category", "unit", "root", "path", "role", "doc", "code"}]
            
            matched = any(w in snippet_lower or w in symbol_lower or w in file_lower for w in words)
            if ev.source_type == EvidenceSourceType.MANIFEST_DEPENDENCY:
                matched = True  # Manifest dependency evidence is authoritative for package names

            if matched:
                evaluations.append(
                    CitationEvaluation(
                        evidence_id=eid,
                        status=CitationStatus.VALID,
                        detail=f"Evidence '{eid}' in '{ev.file_path}' entails claim."
                    )
                )
            else:
                evaluations.append(
                    CitationEvaluation(
                        evidence_id=eid,
                        status=CitationStatus.NOT_ENTAILED,
                        detail=f"Evidence '{eid}' ({ev.file_path}: '{ev.snippet[:50]}...') does not entail claim '{claim_text}'."
                    )
                )

        return evaluations
