"""
Documentation Context Budgeter - Applies deterministic budgeting across documentation tiers.
"""
from __future__ import annotations
import logging
from typing import List, Tuple
from .schemas import DiscoveredDoc, DocType, DocPriority, BudgetedDocContext

logger = logging.getLogger(__name__)

# Target budgets (characters)
TOTAL_MAX_CHARS = 24_000
PRIMARY_DOC_MAX_CHARS = 12_000   # 50%
SUPPORTING_DOC_MAX_CHARS = 8_400 # 35%
DIAGRAM_DOC_MAX_CHARS = 2_400    # 10%
AGENT_DOC_MAX_CHARS = 2_400      # 10% (strict cap)

MAX_SINGLE_DOC_CHARS = 4_000
MAX_AGENT_SINGLE_DOC_CHARS = 1_200


class DocContextBudgeter:
    """
    Enforces deterministic context limits.
    Truncates large files intelligently while preserving headings and introductory paragraphs.
    Ensures agent instruction files never dominate the prompt context.
    """

    def __init__(
        self,
        total_budget: int = TOTAL_MAX_CHARS,
        primary_budget: int = PRIMARY_DOC_MAX_CHARS,
        supporting_budget: int = SUPPORTING_DOC_MAX_CHARS,
        diagram_budget: int = DIAGRAM_DOC_MAX_CHARS,
        agent_budget: int = AGENT_DOC_MAX_CHARS,
    ):
        self.total_budget = total_budget
        self.primary_budget = primary_budget
        self.supporting_budget = supporting_budget
        self.diagram_budget = diagram_budget
        self.agent_budget = agent_budget

    def _truncate_doc(self, doc: DiscoveredDoc, max_chars: int) -> DiscoveredDoc:
        """Truncates a document safely while retaining title and headings."""
        if len(doc.content) <= max_chars:
            return doc

        lines = doc.content.splitlines()
        lead_lines: List[str] = []
        headings: List[str] = []
        char_count = 0

        target_lead = int(max_chars * 0.7)
        for line in lines:
            if char_count < target_lead:
                lead_lines.append(line)
                char_count += len(line) + 1
            elif line.strip().startswith("#"):
                headings.append(line.strip())

        truncated_content = "\n".join(lead_lines)
        if headings:
            truncated_content += "\n\n[Remaining Headings in File]:\n" + "\n".join(f"- {h}" for h in headings[:10])

        truncated_content += f"\n\n[... Content truncated: {len(doc.content)} total chars ...]"
        if len(truncated_content) > max_chars:
            truncated_content = truncated_content[:max_chars]

        return DiscoveredDoc(
            path=doc.path,
            filename=doc.filename,
            doc_type=doc.doc_type,
            priority=doc.priority,
            raw_size=doc.raw_size,
            line_count=doc.line_count,
            headings=doc.headings,
            content=truncated_content,
            is_truncated=True,
            token_estimate=len(truncated_content) // 4,
        )

    def budget(self, docs: List[DiscoveredDoc]) -> BudgetedDocContext:
        primary: List[DiscoveredDoc] = []
        supporting: List[DiscoveredDoc] = []
        diagrams: List[DiscoveredDoc] = []
        agent: List[DiscoveredDoc] = []
        omitted: List[str] = []

        primary_used = 0
        supporting_used = 0
        diagram_used = 0
        agent_used = 0
        total_used = 0

        # Sort by priority desc
        sorted_docs = sorted(docs, key=lambda d: (-d.priority.value, d.path))

        for doc in sorted_docs:
            total_rem = self.total_budget - total_used
            if total_rem <= 0:
                omitted.append(doc.path)
                continue

            # 1. Primary Docs (README, Architecture)
            if doc.priority >= DocPriority.HIGH and doc.doc_type in {DocType.PRIMARY_README, DocType.ARCHITECTURE, DocType.PRODUCT_SYSTEM_DOCS, DocType.CONTRIBUTING}:
                tier_rem = self.primary_budget - primary_used
                allowed = min(tier_rem, total_rem)
                if allowed < 50:
                    omitted.append(doc.path)
                    continue

                trimmed = self._truncate_doc(doc, min(MAX_SINGLE_DOC_CHARS, allowed))
                doc_len = len(trimmed.content)
                primary.append(trimmed)
                primary_used += doc_len
                total_used += doc_len

            # 2. Diagrams (.mmd)
            elif doc.doc_type == DocType.DIAGRAMS or doc.path.endswith(".mmd"):
                tier_rem = self.diagram_budget - diagram_used
                allowed = min(tier_rem, total_rem)
                if allowed < 50:
                    omitted.append(doc.path)
                    continue

                trimmed = self._truncate_doc(doc, min(1_500, allowed))
                doc_len = len(trimmed.content)
                diagrams.append(trimmed)
                diagram_used += doc_len
                total_used += doc_len

            # 3. Agent / Tool Instructions (Strictly Capped)
            elif doc.doc_type == DocType.AGENT_INSTRUCTIONS or doc.priority == DocPriority.AGENT_CONTEXT:
                tier_rem = self.agent_budget - agent_used
                allowed = min(tier_rem, total_rem)
                if allowed < 50:
                    omitted.append(doc.path)
                    continue

                trimmed = self._truncate_doc(doc, min(MAX_AGENT_SINGLE_DOC_CHARS, allowed))
                doc_len = len(trimmed.content)
                agent.append(trimmed)
                agent_used += doc_len
                total_used += doc_len

            # 4. Supporting Docs (API, Guides, Generic)
            else:
                tier_rem = self.supporting_budget - supporting_used
                allowed = min(tier_rem, total_rem)
                if allowed < 50:
                    omitted.append(doc.path)
                    continue

                trimmed = self._truncate_doc(doc, min(2_500, allowed))
                doc_len = len(trimmed.content)
                supporting.append(trimmed)
                supporting_used += doc_len
                total_used += doc_len

        return BudgetedDocContext(
            primary_docs=primary,
            supporting_docs=supporting,
            diagram_docs=diagrams,
            agent_docs=agent,
            omitted_docs=omitted,
            total_chars=total_used,
            total_tokens_est=total_used // 4,
        )
