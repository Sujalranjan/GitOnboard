import re
import math
from typing import List, Dict, Set, Optional, Any, Tuple
from collections import Counter

class CodeTokenizer:
    """
    Code-aware tokenizer that preserves programming symbols, identifiers,
    and supports camelCase, snake_case, PascalCase, and path/route splitting.
    """
    # Common programming keywords/operators to keep
    IDENTIFIER_REGEX = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
    PUNCT_SPLIT = re.compile(r"[/\\.:\-_\s]+")

    @classmethod
    def split_identifier_subwords(cls, ident: str) -> List[str]:
        """
        Splits camelCase, PascalCase, or snake_case identifiers into subwords.
        e.g. 'get_user_by_jwt_token' -> ['get', 'user', 'by', 'jwt', 'token']
        e.g. 'AnalysisArtifact' -> ['analysis', 'artifact']
        e.g. 'TaskManager' -> ['task', 'manager']
        """
        # Split on underscores / hyphens first
        parts = [p for p in re.split(r"[_\-]+", ident) if p]
        subwords = []
        for part in parts:
            # Split camelCase / PascalCase
            # Handles things like "HTTPResponse" -> "HTTP", "Response" or "getUser" -> "get", "User"
            words = re.findall(r"[A-Z]+(?=[A-Z][a-z0-9]|\b)|[A-Z]?[a-z0-9]+|[A-Z]+", part)
            for w in words:
                w_lower = w.lower().strip()
                if w_lower:
                    subwords.append(w_lower)
        return subwords

    @classmethod
    def tokenize(cls, text: str, include_subwords: bool = True) -> List[str]:
        """
        Tokenizes code or natural language into code-aware search tokens.
        Preserves original identifier as a whole token AND adds decomposed subwords.
        """
        if not text:
            return []
        
        # Clean text
        raw_tokens = cls.PUNCT_SPLIT.split(text)
        tokens: List[str] = []
        
        for raw in raw_tokens:
            cleaned = raw.strip()
            if not cleaned:
                continue
            
            cleaned_lower = cleaned.lower()
            tokens.append(cleaned_lower)
            
            if include_subwords and (any(c.isupper() for c in cleaned) or "_" in cleaned or "-" in cleaned):
                subwords = cls.split_identifier_subwords(cleaned)
                for sw in subwords:
                    if sw != cleaned_lower and len(sw) > 1:
                        tokens.append(sw)
                        
        return tokens


class BM25Index:
    """
    In-memory BM25 (Okapi BM25) implementation tailored for code documents.
    Operates without heavy external C-extensions, fully deterministic and fast.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_len: List[int] = []
        self.avg_doc_len: float = 0.0
        self.corpus_size: int = 0
        self.doc_term_freqs: List[Counter] = []
        self.idf: Dict[str, float] = {}
        self.documents: List[Dict[str, Any]] = []

    def index(self, docs: List[Dict[str, Any]], text_key: str = "search_text"):
        """
        Indexes a list of document dicts.
        Each doc should have at least doc[text_key] containing the text to index.
        """
        self.documents = docs
        self.corpus_size = len(docs)
        self.doc_len = []
        self.doc_term_freqs = []
        
        if self.corpus_size == 0:
            self.avg_doc_len = 0.0
            self.idf = {}
            return

        df: Dict[str, int] = {}
        total_len = 0

        for doc in docs:
            text = doc.get(text_key, "")
            tokens = CodeTokenizer.tokenize(text, include_subwords=True)
            length = len(tokens)
            self.doc_len.append(length)
            total_len += length
            
            tf = Counter(tokens)
            self.doc_term_freqs.append(tf)
            
            for term in tf.keys():
                df[term] = df.get(term, 0) + 1

        self.avg_doc_len = total_len / self.corpus_size if self.corpus_size > 0 else 0.0

        # Calculate standard Okapi BM25 IDF with smoothing
        self.idf = {}
        for term, freq in df.items():
            # idf = ln((N - n + 0.5) / (n + 0.5) + 1.0)
            self.idf[term] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def search(self, query: str, top_k: int = 30) -> List[Tuple[Dict[str, Any], float]]:
        """
        Scores and ranks documents against the query.
        Returns list of (document, score) tuples.
        """
        if self.corpus_size == 0:
            return []

        query_tokens = CodeTokenizer.tokenize(query, include_subwords=True)
        if not query_tokens:
            return []

        scores = [0.0] * self.corpus_size

        for term in query_tokens:
            if term not in self.idf:
                continue
            idf_val = self.idf[term]
            
            for doc_idx, tf_counter in enumerate(self.doc_term_freqs):
                tf = tf_counter.get(term, 0)
                if tf == 0:
                    continue
                
                doc_l = self.doc_len[doc_idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_l / (self.avg_doc_len or 1.0)))
                term_score = idf_val * ((tf * (self.k1 + 1.0)) / denom)
                scores[doc_idx] += term_score

        # Pair with documents and filter zero scores
        scored_docs = [
            (self.documents[idx], scores[idx])
            for idx in range(self.corpus_size)
            if scores[idx] > 0.0
        ]
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return scored_docs[:top_k]
