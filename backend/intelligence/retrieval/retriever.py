import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models.user import User
from backend.intelligence.retrieval.lexical import BM25Index, CodeTokenizer
from backend.intelligence.retrieval.fusion import reciprocal_rank_fusion
from backend.intelligence.retrieval.expansion import FactStoreExpander
from backend.models.fact_store import FactSymbol, FactFile, FactRoute, FactDatabaseObject

logger = logging.getLogger(__name__)

class HybridRetriever:
    """
    Unified Hybrid Retrieval Engine for GitOnboard:
    1. Lexical BM25 Search (using CodeTokenizer on Fact Store symbols & docs)
    2. Dense Semantic Vector Search (ChromaDB)
    3. Exact Fact Store direct lookups (Routes, DB tables, exact symbols)
    4. Reciprocal Rank Fusion (RRF)
    5. Limited Fact Store Structural Expansion
    """

    def __init__(
        self,
        db: Session,
        analysis_id: Optional[int] = None,
        chroma_collection: Any = None,
        rrf_k: int = 60,
        lexical_weight: float = 1.0,
        semantic_weight: float = 1.0,
        exact_weight: float = 1.2,
    ):
        self.db = db
        self.analysis_id = analysis_id
        self.chroma_collection = chroma_collection
        self.rrf_k = rrf_k
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight
        self.exact_weight = exact_weight
        self.bm25_index: Optional[BM25Index] = None
        self._build_lexical_index()

    def _build_lexical_index(self):
        """Constructs an in-memory BM25 index of the codebase entities from the Fact Store."""
        if not self.analysis_id:
            return

        docs: List[Dict[str, Any]] = []

        # 1. Index Symbols
        symbols = self.db.query(FactSymbol).filter(FactSymbol.analysis_id == self.analysis_id).all()
        for sym in symbols:
            fpath = sym.file.path if sym.file else ""
            meta = sym.metadata_json or {}
            docstring = meta.get("docstring", "")
            signature = meta.get("signature", "")
            
            # Form rich searchable document
            search_text = f"{sym.name} {sym.qualified_name or ''} {sym.symbol_type} {fpath} {signature} {docstring}"
            docs.append({
                "id": sym.id,
                "name": sym.name,
                "qualified_name": sym.qualified_name or sym.name,
                "type": sym.symbol_type,
                "file_path": fpath,
                "search_text": search_text,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
                "match_type": sym.symbol_type,
                "match_name": sym.name,
            })

        # 2. Index Routes
        routes = self.db.query(FactRoute).filter(FactRoute.analysis_id == self.analysis_id).all()
        for r in routes:
            search_text = f"route {r.method} {r.path}"
            docs.append({
                "id": r.id,
                "name": f"{r.method} {r.path}",
                "qualified_name": f"{r.method} {r.path}",
                "type": "route",
                "file_path": "",
                "search_text": search_text,
                "match_type": "route",
                "match_name": f"{r.method} {r.path}",
                "symbol_id": r.symbol_id,
            })

        # 3. Index DB Objects
        db_objs = self.db.query(FactDatabaseObject).filter(FactDatabaseObject.analysis_id == self.analysis_id).all()
        for d in db_objs:
            search_text = f"database table {d.name} {d.object_type}"
            docs.append({
                "id": d.id,
                "name": d.name,
                "qualified_name": d.name,
                "type": "database_table",
                "file_path": "",
                "search_text": search_text,
                "match_type": "database_table",
                "match_name": d.name,
                "symbol_id": d.symbol_id,
            })

        self.bm25_index = BM25Index()
        self.bm25_index.index(docs, text_key="search_text")

    def _search_exact_facts(self, query: str) -> List[Dict[str, Any]]:
        """Finds direct, exact matches in the Fact Store (symbols, routes, database tables)."""
        if not self.analysis_id:
            return []

        results = []
        q_clean = query.strip()
        q_lower = q_clean.lower()

        # Check exact symbol match
        exact_syms = self.db.query(FactSymbol).filter(
            FactSymbol.analysis_id == self.analysis_id,
            (FactSymbol.name == q_clean) | (FactSymbol.name.ilike(q_clean))
        ).all()
        for s in exact_syms:
            results.append({
                "id": s.id,
                "symbol_id": s.id,
                "name": s.name,
                "match_name": s.name,
                "type": s.symbol_type,
                "match_type": s.symbol_type,
                "file_path": s.file.path if s.file else "",
                "line_start": s.line_start,
                "line_end": s.line_end,
                "score_type": "exact_fact"
            })

        # Check exact route path
        routes = self.db.query(FactRoute).filter(
            FactRoute.analysis_id == self.analysis_id,
            (FactRoute.path.ilike(f"%{q_clean}%")) | (FactRoute.path == q_clean)
        ).all()
        for r in routes:
            results.append({
                "id": r.id,
                "symbol_id": r.symbol_id,
                "name": f"{r.method} {r.path}",
                "match_name": f"{r.method} {r.path}",
                "type": "route",
                "match_type": "route",
                "file_path": "",
                "score_type": "exact_fact"
            })

        # Check exact DB table
        db_objs = self.db.query(FactDatabaseObject).filter(
            FactDatabaseObject.analysis_id == self.analysis_id,
            (FactDatabaseObject.name.ilike(q_clean)) | (FactDatabaseObject.name == q_clean)
        ).all()
        for d in db_objs:
            results.append({
                "id": d.id,
                "symbol_id": d.symbol_id,
                "name": d.name,
                "match_name": d.name,
                "type": "database_table",
                "match_type": "database_table",
                "file_path": "",
                "score_type": "exact_fact"
            })

        return results

    def _search_semantic(self, query: str, top_k: int = 30) -> List[Dict[str, Any]]:
        """Queries ChromaDB vector collection."""
        if not self.chroma_collection:
            return []

        try:
            query_results = self.chroma_collection.query(query_texts=[query], n_results=top_k)
            semantic_candidates = []
            if query_results and query_results.get("metadatas") and len(query_results["metadatas"]) > 0:
                for idx, meta in enumerate(query_results["metadatas"][0]):
                    dist = query_results["distances"][0][idx] if query_results.get("distances") else 0.0
                    fp = meta.get("file_path", "")
                    name = meta.get("name", "")
                    typ = meta.get("type", "symbol")
                    cid = f"{fp}:{name}:{typ}"
                    semantic_candidates.append({
                        "id": cid,
                        "file_path": fp,
                        "match_type": typ,
                        "match_name": name,
                        "name": name,
                        "type": typ,
                        "distance": dist,
                    })
            return semantic_candidates
        except Exception as e:
            logger.warning(f"ChromaDB query failed: {e}")
            return []

    def _search_lexical(self, query: str, top_k: int = 30) -> List[Dict[str, Any]]:
        """Queries in-memory BM25 index."""
        if not self.bm25_index:
            return []

        scored_docs = self.bm25_index.search(query, top_k=top_k)
        lexical_candidates = []
        for doc, score in scored_docs:
            c = dict(doc)
            c["bm25_score"] = score
            lexical_candidates.append(c)
        return lexical_candidates

    def retrieve(
        self,
        query: str,
        top_k: int = 15,
        expand_with_fact_store: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Executes end-to-end hybrid retrieval:
        1. Exact Fact Search
        2. Lexical BM25 Search
        3. Semantic Chroma Search
        4. Reciprocal Rank Fusion
        5. Graph/Fact Store Expansion
        """
        if not query or not query.strip():
            return []

        q = query.strip()

        # Step 1-3: Parallel retrieval streams
        exact_results = self._search_exact_facts(q)
        lexical_results = self._search_lexical(q, top_k=30)
        semantic_results = self._search_semantic(q, top_k=30)

        # Step 4: RRF Fusion
        ranked_lists = []
        weights = []

        if exact_results:
            ranked_lists.append(exact_results)
            weights.append(self.exact_weight)

        if lexical_results:
            ranked_lists.append(lexical_results)
            weights.append(self.lexical_weight)

        if semantic_results:
            ranked_lists.append(semantic_results)
            weights.append(self.semantic_weight)

        if not ranked_lists:
            return []

        fused = reciprocal_rank_fusion(
            ranked_lists=ranked_lists,
            weights=weights,
            rrf_k=self.rrf_k,
            key_field="id",
            top_k=top_k * 2
        )

        # Step 5: Fact Store expansion
        if expand_with_fact_store and self.analysis_id:
            expander = FactStoreExpander(self.db, self.analysis_id, max_expansions_per_seed=2, max_total_context=top_k)
            return expander.expand_candidates(fused)

        return fused[:top_k]
