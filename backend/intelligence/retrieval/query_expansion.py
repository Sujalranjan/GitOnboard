"""
Query expansion and fallback strategies for natural-language repository queries.

Handles the vocabulary bridge problem:
- User asks: "What is the authentication flow?"
- Code vocabulary: "auth", "middleware", "token", "authenticate", "validate"

Implements general strategies that work for arbitrary repositories:
1. Query decomposition (break natural language into components)
2. Stopword removal and term normalization
3. Fallback to partial matches
4. Semantic search as fallback to lexical
"""

import logging
from typing import List, Set, Tuple
import re

logger = logging.getLogger(__name__)


class QueryExpander:
    """Expands and decomposes queries for retrieval fallback."""

    # Common English stop words to filter from queries
    STOPWORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'what', 'when', 'where',
        'why', 'how', 'which', 'who', 'whom', 'whose', 'that', 'this', 'these',
        'those', 'as', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'over', 'under', 'again', 'further',
        'then', 'once', 'here', 'there', 'when', 'should', 'could', 'would'
    }

    @classmethod
    def extract_key_terms(cls, query: str) -> List[str]:
        """
        Extract content words from query by removing stop words and normalizing.

        Example:
            "What is the authentication flow?" → ["authentication", "flow"]
            "How do I validate tokens?" → ["validate", "tokens"]
        """
        # Lowercase and remove punctuation except hyphen/underscore
        query = query.lower()
        # Remove special characters but preserve word boundaries
        words = re.findall(r'\b[a-z_-]+\b', query)

        # Filter out stop words
        key_terms = [w for w in words if w not in cls.STOPWORDS and len(w) > 1]

        return key_terms

    @classmethod
    def decompose_query(cls, query: str) -> Tuple[List[str], List[str]]:
        """
        Decompose query into primary terms (content) and fallback terms (substrings).

        Returns:
            (primary_terms, fallback_terms)
            - primary: full extracted terms (e.g., ["authentication", "flow"])
            - fallback: single characters/substrings for substring matching

        Example:
            "What is the authentication flow?"
            → primary: ["authentication", "flow"]
            → fallback: ["auth", "flow", "ment"]
        """
        primary_terms = cls.extract_key_terms(query)

        # For fallback, create substring variants
        # "authentication" → ["auth", "tication", "entication"]
        fallback_terms = []
        for term in primary_terms:
            if len(term) > 4:
                # Add prefix (first 4 chars) and suffix
                fallback_terms.append(term[:4])
                if len(term) > 8:
                    fallback_terms.append(term[-4:])
            else:
                # For short words, keep as-is
                fallback_terms.append(term)

        return primary_terms, fallback_terms

    @classmethod
    def generate_retrieval_strategy(cls, query: str) -> dict:
        """
        Generate a multi-level retrieval strategy for a query.

        Returns dict with:
        - level_1_primary: Full query (try exact match first)
        - level_2_key_terms: Individual key terms
        - level_3_substrings: Substring/prefix matches
        - level_4_semantic: Fallback to semantic search (if available)

        This allows retriever to progressively fall back if earlier levels find nothing.
        """
        primary_terms, fallback_terms = cls.decompose_query(query)

        return {
            "original_query": query,
            "strategy": "multi_level_fallback",
            "level_1": {
                "type": "exact",
                "query": query,
                "description": "Full query on BM25 index"
            },
            "level_2": {
                "type": "key_terms",
                "queries": primary_terms,
                "description": "Individual key terms (content words only)"
            },
            "level_3": {
                "type": "substring",
                "queries": fallback_terms,
                "description": "Substring/prefix fallback"
            },
            "level_4": {
                "type": "semantic",
                "query": query,
                "description": "Semantic search as final fallback"
            }
        }


class RetrievalFallbackStrategy:
    """
    Manages multi-level fallback retrieval when primary strategy fails.

    When lexical (BM25) returns 0 results, automatically tries:
    1. Decomposed key terms
    2. Substring/prefix matching
    3. Semantic search (if available)
    """

    def __init__(self, retriever: "HybridRetriever"):
        """Initialize with retriever instance."""
        self.retriever = retriever
        self.logger = logging.getLogger(__name__)

    def retrieve_with_fallback(
        self,
        query: str,
        top_k: int = 15,
        expand_with_fact_store: bool = True
    ) -> List[dict]:
        """
        Execute retrieval with automatic fallback strategy.

        Algorithm:
        1. Try full query on BM25
        2. If empty, try key terms separately
        3. If still empty, try substrings
        4. If still empty, try semantic search
        5. Return best results from any level that succeeded

        Returns list of RetrieverResult objects.
        """
        strategy = QueryExpander.generate_retrieval_strategy(query)
        self.logger.info(f"[Retrieval] Executing strategy for: {query}")

        # Level 1: Try exact query
        results = self.retriever.retrieve(
            query,
            top_k=top_k,
            expand_with_fact_store=expand_with_fact_store
        )

        if results:
            self.logger.info(f"[Retrieval] Level 1 (exact) found {len(results)} results")
            return results

        self.logger.info("[Retrieval] Level 1 (exact) returned empty, trying Level 2 (key terms)")

        # Level 2: Try individual key terms
        primary_terms, _ = QueryExpander.decompose_query(query)
        level_2_results = []
        for term in primary_terms:
            term_results = self.retriever.retrieve(
                term,
                top_k=top_k,
                expand_with_fact_store=expand_with_fact_store
            )
            level_2_results.extend(term_results)

        if level_2_results:
            # Deduplicate and re-rank
            seen_ids = set()
            deduped = []
            for r in level_2_results:
                rid = r.id if hasattr(r, 'id') else r.get('id')
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    deduped.append(r)
            self.logger.info(f"[Retrieval] Level 2 (key terms) found {len(deduped)} results")
            return deduped[:top_k]

        self.logger.info("[Retrieval] Level 2 (key terms) returned empty, trying Level 3 (substrings)")

        # Level 3: Try substring matching via modified queries
        _, fallback_terms = QueryExpander.decompose_query(query)
        level_3_results = []
        for term in fallback_terms:
            term_results = self.retriever.retrieve(
                term,
                top_k=top_k,
                expand_with_fact_store=expand_with_fact_store
            )
            level_3_results.extend(term_results)

        if level_3_results:
            seen_ids = set()
            deduped = []
            for r in level_3_results:
                rid = r.id if hasattr(r, 'id') else r.get('id')
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    deduped.append(r)
            self.logger.info(f"[Retrieval] Level 3 (substrings) found {len(deduped)} results")
            return deduped[:top_k]

        self.logger.info("[Retrieval] All lexical strategies returned empty, would try Level 4 (semantic) if available")
        return []
