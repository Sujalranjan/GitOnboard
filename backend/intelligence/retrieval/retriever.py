import logging
from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from backend.models.user import User
from backend.intelligence.retrieval.lexical import BM25Index, CodeTokenizer
from backend.intelligence.retrieval.fusion import reciprocal_rank_fusion
from backend.intelligence.retrieval.expansion import FactStoreExpander
from backend.intelligence.retrieval.schema import (
    RetrieverResult,
    convert_lexical_result_to_schema,
    convert_semantic_result_to_schema,
    convert_exact_result_to_schema,
)
from backend.models.fact_store import FactSymbol, FactFile, FactRoute, FactDatabaseObject, FactCapability

logger = logging.getLogger(__name__)

def _extract_symbol_file_path(sym: Optional[FactSymbol]) -> str:
    if not sym:
        return ""
    if sym.file and sym.file.path:
        return sym.file.path
    if sym.id:
        import re
        match = re.search(r":urn:[^:]+:(.+?)#", sym.id)
        if match:
            return match.group(1)
    return ""


class HybridRetriever:
    """
    Unified Hybrid Retrieval Engine for GitOnboard:
    1. Lexical BM25 Search (using CodeTokenizer on Fact Store symbols, files, routes & docs)
    2. Dense Semantic Vector Search (ChromaDB)
    3. Exact Fact Store direct lookups (Routes, DB tables, exact symbols, files)
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
        self.semantic_degradation: Optional[str] = None  # Track why semantic search failed
        self._load_or_build_lexical_index()
        self._load_semantic_index_from_artifact()

    def _load_or_build_lexical_index(self):
        """Load pre-built BM25 index from analysis artifact, or build from FactStore."""
        if not self.analysis_id:
            return

        # Try to load pre-built index from analysis artifact
        try:
            from backend.models.repository import Analysis, AnalysisArtifact
            from backend.intelligence.retrieval.artifact_persistence import persist_rebuilt_bm25

            # Get current fact_store_version for staleness check
            analysis = self.db.query(Analysis).filter(Analysis.id == self.analysis_id).first()
            current_fact_store_version = analysis.fact_store_version if analysis else None

            artifact = self.db.query(AnalysisArtifact).filter(
                AnalysisArtifact.analysis_id == self.analysis_id,
                AnalysisArtifact.type == "bm25_index"
            ).first()

            if artifact and artifact.data:
                bm25_data = artifact.data
                artifact_fact_store_version = bm25_data.get("fact_store_version")

                # Check if BM25 corresponds to current FactStore (Phase 4-C staleness detection)
                if artifact_fact_store_version and current_fact_store_version:
                    if artifact_fact_store_version != current_fact_store_version:
                        logger.warning(
                            f"BM25 artifact is stale: built for version {artifact_fact_store_version[:8]}... "
                            f"but FactStore is now {current_fact_store_version[:8]}... "
                            f"Rebuilding from current FactStore."
                        )
                        # BM25 is stale — rebuild from FactStore and persist fresh version
                        self._build_and_persist_lexical_index()
                        return

                # Rebuild BM25 index from stored metadata
                try:
                    index = BM25Index()
                    index.documents = bm25_data.get("documents", [])
                    index.idf = bm25_data.get("idf", {})
                    index.doc_len = bm25_data.get("doc_len", [])
                    index.corpus_size = bm25_data.get("corpus_size", 0)
                    index.avg_doc_len = bm25_data.get("avg_doc_len", 0.0)
                    self.bm25_index = index
                    logger.info(f"Loaded fresh BM25 index for analysis {self.analysis_id} (version={current_fact_store_version[:8] if current_fact_store_version else 'unknown'}...)")
                    return
                except Exception as e:
                    logger.warning(f"Failed to rebuild BM25 from artifact: {e}")
        except Exception as e:
            logger.debug(f"Could not load BM25 artifact: {e}")

        # Fallback: build from FactStore
        self._build_lexical_index()

    def _build_and_persist_lexical_index(self):
        """
        Rebuild BM25 from FactStore and persist the fresh artifact.

        Used when stale BM25 is detected to ensure fresh index is available for future retrievals.
        """
        if not self.analysis_id:
            return

        # Build fresh BM25 in-memory
        self._build_lexical_index()

        # If build succeeded, persist the fresh artifact
        if self.bm25_index:
            try:
                from backend.models.repository import Analysis
                from backend.intelligence.retrieval.artifact_persistence import persist_rebuilt_bm25

                analysis = self.db.query(Analysis).filter(Analysis.id == self.analysis_id).first()
                if not analysis:
                    logger.error(f"Cannot persist BM25: analysis {self.analysis_id} not found")
                    return

                # Prepare BM25 data for persistence
                bm25_data = {
                    "documents": self.bm25_index.documents,
                    "idf": dict(self.bm25_index.idf),
                    "doc_len": self.bm25_index.doc_len,
                    "corpus_size": self.bm25_index.corpus_size,
                    "avg_doc_len": self.bm25_index.avg_doc_len,
                    "fact_store_version": analysis.fact_store_version,  # Include current version
                }

                # Persist to artifact store
                success = persist_rebuilt_bm25(
                    db=self.db,
                    analysis_id=self.analysis_id,
                    bm25_data=bm25_data,
                    current_fact_store_version=analysis.fact_store_version,
                )

                if success:
                    logger.info(
                        f"[BM25_LIFECYCLE_COMPLETE] Rebuilt and persisted BM25 for analysis {self.analysis_id} "
                        f"version {analysis.fact_store_version[:8]}..."
                    )
                else:
                    logger.warning(
                        f"[BM25_PERSIST_FAILED_FALLBACK] BM25 rebuilt but persistence failed for analysis {self.analysis_id}. "
                        f"Will use in-memory BM25 for this retrieval; next initialization may rebuild again."
                    )

            except Exception as e:
                logger.error(
                    f"Exception during BM25 persist after rebuild for analysis {self.analysis_id}: {e}",
                    exc_info=True
                )

    def _build_lexical_index(self):
        """Constructs an in-memory BM25 index of the codebase entities from the Fact Store."""
        if not self.analysis_id:
            return

        docs: List[Dict[str, Any]] = []

        # 1. Index Files
        files = self.db.query(FactFile).filter(FactFile.analysis_id == self.analysis_id).all()
        for f in files:
            search_text = f"file path {f.path} {f.language or ''} {f.content_type or ''}"
            docs.append({
                "id": f.id,
                "name": f.path,
                "qualified_name": f.path,
                "type": "file",
                "file_path": f.path,
                "search_text": search_text,
                "line_start": 1,
                "line_end": 1,
                "match_type": "file",
                "match_name": f.path,
            })

        # 2. Index Symbols
        symbols = self.db.query(FactSymbol).filter(FactSymbol.analysis_id == self.analysis_id).all()
        for sym in symbols:
            fpath = _extract_symbol_file_path(sym)
            meta = sym.metadata_json or {}
            docstring = meta.get("docstring", "")
            signature = meta.get("signature", "")

            # Form rich searchable document
            search_text = f"{sym.name} {sym.qualified_name or ''} {sym.symbol_type} {fpath} {signature} {docstring}"
            docs.append({
                "id": sym.id,
                "symbol_id": sym.id,  # Include symbol_id for proper expansion resolution
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

        # 3. Index Routes
        routes = self.db.query(FactRoute).filter(FactRoute.analysis_id == self.analysis_id).all()
        for r in routes:
            handler_id = r.handler_symbol_id or r.symbol_id
            fpath = ""
            l_start = None
            l_end = None
            if handler_id:
                sym = self.db.query(FactSymbol).filter(FactSymbol.id == handler_id).first()
                if sym:
                    fpath = _extract_symbol_file_path(sym)
                    l_start = sym.line_start
                    l_end = sym.line_end
            search_text = f"route {r.method} {r.path} {fpath}"
            docs.append({
                "id": r.id,
                "name": f"{r.method} {r.path}",
                "qualified_name": f"{r.method} {r.path}",
                "type": "route",
                "file_path": fpath,
                "search_text": search_text,
                "match_type": "route",
                "match_name": f"{r.method} {r.path}",
                "symbol_id": handler_id or r.symbol_id or r.id,
                "line_start": l_start,
                "line_end": l_end,
            })

        # 4. Index DB Objects
        db_objs = self.db.query(FactDatabaseObject).filter(FactDatabaseObject.analysis_id == self.analysis_id).all()
        for d in db_objs:
            fpath = ""
            l_start = None
            l_end = None
            if d.symbol_id:
                sym = self.db.query(FactSymbol).filter(FactSymbol.id == d.symbol_id).first()
                if sym:
                    fpath = _extract_symbol_file_path(sym)
                    l_start = sym.line_start
                    l_end = sym.line_end
            search_text = f"database table {d.name} {d.object_type} {fpath}"
            docs.append({
                "id": d.id,
                "name": d.name,
                "qualified_name": d.name,
                "type": "database_table",
                "file_path": fpath,
                "search_text": search_text,
                "match_type": "database_table",
                "match_name": d.name,
                "symbol_id": d.symbol_id or d.id,
                "line_start": l_start,
                "line_end": l_end,
            })

        # 5. Index Capabilities
        caps = self.db.query(FactCapability).filter(FactCapability.analysis_id == self.analysis_id).all()
        for c in caps:
            search_text = f"capability {c.name} {c.capability_type or ''} {c.evidence_summary or ''}"
            docs.append({
                "id": c.id,
                "name": c.name,
                "qualified_name": c.name,
                "type": "capability",
                "file_path": "",
                "search_text": search_text,
                "match_type": "capability",
                "match_name": c.name,
            })

        self.bm25_index = BM25Index()
        self.bm25_index.index(docs, text_key="search_text")

    def _load_semantic_index_from_artifact(self):
        """Load pre-built Chroma semantic index from analysis artifact."""
        if not self.analysis_id or self.chroma_collection:
            return

        try:
            from backend.models.repository import AnalysisArtifact
            artifact = self.db.query(AnalysisArtifact).filter(
                AnalysisArtifact.analysis_id == self.analysis_id,
                AnalysisArtifact.type == "semantic_index_db"
            ).first()

            if not artifact:
                self.semantic_degradation = "artifact_not_found"
                logger.debug(f"No semantic_index_db artifact for analysis {self.analysis_id}")
                return

            if not artifact.blob_data:
                self.semantic_degradation = "artifact_empty"
                logger.debug(f"semantic_index_db artifact is empty for analysis {self.analysis_id}")
                return

            try:
                import chromadb
                import tempfile
                import zipfile
                import io

                # Extract Chroma database from zip
                temp_dir = tempfile.mkdtemp(prefix="chroma_load_")
                try:
                    with zipfile.ZipFile(io.BytesIO(artifact.blob_data)) as zf:
                        zf.extractall(temp_dir)

                    # Load from extracted directory
                    client = chromadb.PersistentClient(path=temp_dir)
                    self.chroma_collection = client.get_collection(name="semantic_index")
                    logger.info(f"Loaded semantic index for analysis {self.analysis_id}")
                except Exception as e:
                    self.semantic_degradation = f"load_error: {str(e)[:50]}"
                    logger.warning(f"Failed to load semantic index from artifact: {e}")
                    # Keep temp_dir for cleanup - will be handled at end

            except ImportError:
                self.semantic_degradation = "chromadb_unavailable"
                logger.debug("chromadb not available - semantic search disabled")

        except Exception as e:
            self.semantic_degradation = f"artifact_load_error: {str(e)[:50]}"
            logger.debug(f"Failed to load semantic index artifact: {e}")

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
            (FactSymbol.name == q_clean) | (FactSymbol.name.ilike(f"%{q_clean}%"))
        ).limit(10).all()
        for s in exact_syms:
            results.append({
                "id": s.id,
                "symbol_id": s.id,
                "name": s.name,
                "match_name": s.name,
                "type": s.symbol_type,
                "match_type": s.symbol_type,
                "file_path": _extract_symbol_file_path(s),
                "line_start": s.line_start,
                "line_end": s.line_end,
                "score_type": "exact_fact"
            })

        # Check exact file path match
        exact_files = self.db.query(FactFile).filter(
            FactFile.analysis_id == self.analysis_id,
            FactFile.path.ilike(f"%{q_clean}%")
        ).limit(10).all()
        for f in exact_files:
            results.append({
                "id": f.id,
                "symbol_id": f.id,
                "name": f.path,
                "match_name": f.path,
                "type": "file",
                "match_type": "file",
                "file_path": f.path,
                "line_start": 1,
                "line_end": 1,
                "score_type": "exact_fact"
            })

        # Check exact route path
        routes = self.db.query(FactRoute).filter(
            FactRoute.analysis_id == self.analysis_id,
            (FactRoute.path.ilike(f"%{q_clean}%")) | (FactRoute.path == q_clean)
        ).all()
        for r in routes:
            handler_id = r.handler_symbol_id or r.symbol_id
            fpath = ""
            l_start = None
            l_end = None
            if handler_id:
                sym = self.db.query(FactSymbol).filter(FactSymbol.id == handler_id).first()
                if sym:
                    fpath = _extract_symbol_file_path(sym)
                    l_start = sym.line_start
                    l_end = sym.line_end
            results.append({
                "id": r.id,
                "symbol_id": handler_id or r.symbol_id or r.id,
                "name": f"{r.method} {r.path}",
                "match_name": f"{r.method} {r.path}",
                "type": "route",
                "match_type": "route",
                "file_path": fpath,
                "line_start": l_start,
                "line_end": l_end,
                "score_type": "exact_fact"
            })

        # Check exact DB table
        db_objs = self.db.query(FactDatabaseObject).filter(
            FactDatabaseObject.analysis_id == self.analysis_id,
            (FactDatabaseObject.name.ilike(q_clean)) | (FactDatabaseObject.name == q_clean)
        ).all()
        for d in db_objs:
            fpath = ""
            l_start = None
            l_end = None
            if d.symbol_id:
                sym = self.db.query(FactSymbol).filter(FactSymbol.id == d.symbol_id).first()
                if sym:
                    fpath = _extract_symbol_file_path(sym)
                    l_start = sym.line_start
                    l_end = sym.line_end
            results.append({
                "id": d.id,
                "symbol_id": d.symbol_id or d.id,
                "name": d.name,
                "match_name": d.name,
                "type": "database_table",
                "match_type": "database_table",
                "file_path": fpath,
                "line_start": l_start,
                "line_end": l_end,
                "score_type": "exact_fact"
            })

        return results

    def _search_semantic(self, query: str, top_k: int = 30) -> List[Dict[str, Any]]:
        """Queries ChromaDB vector collection, resolving to actual FactSymbol IDs for expansion."""
        if not self.chroma_collection:
            if self.semantic_degradation:
                logger.debug(f"Semantic search skipped for analysis {self.analysis_id}: {self.semantic_degradation}")
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

                    # Try to resolve to actual FactSymbol ID for proper expansion
                    symbol_id = None
                    if typ not in ["file", "route", "database_table", "capability"]:
                        # Query FactSymbol to get the real database ID
                        sym = None
                        if fp and name:
                            sym = self.db.query(FactSymbol).join(FactFile).filter(
                                FactSymbol.analysis_id == self.analysis_id,
                                FactSymbol.name == name,
                                FactFile.path == fp
                            ).first()
                        elif name:
                            sym = self.db.query(FactSymbol).filter(
                                FactSymbol.analysis_id == self.analysis_id,
                                FactSymbol.name == name
                            ).first()
                        if sym:
                            symbol_id = sym.id

                    # Use either database ID or construct metadata for resolution
                    candidate_id = symbol_id or f"{fp}:{name}:{typ}"

                    semantic_candidates.append({
                        "id": candidate_id,
                        "symbol_id": symbol_id,  # Include resolved symbol_id for expansion
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
        expand_with_fact_store: bool = True,
        enable_fallback: bool = True
    ) -> List[RetrieverResult]:
        """
        Executes end-to-end hybrid retrieval:
        1. Exact Fact Search
        2. Lexical BM25 Search
        3. Semantic Chroma Search
        4. Reciprocal Rank Fusion
        5. Graph/Fact Store Expansion

        When primary strategies return empty, optionally applies fallback:
        - Decompose query into key terms
        - Retry with substrings
        - Use semantic search as final fallback

        Returns canonical RetrieverResult objects that all consumers can rely on.

        Args:
            query: User query
            top_k: Number of results to return
            expand_with_fact_store: Whether to expand with graph relationships
            enable_fallback: Whether to auto-fallback when primary strategies fail (default: True)
        """
        if not query or not query.strip():
            return []

        q = query.strip()

        # Try primary retrieval
        results = self._retrieve_primary(q, top_k, expand_with_fact_store)

        if results:
            return results

        # If primary returned empty and fallback enabled, try alternatives
        if enable_fallback:
            logger.info(f"[Retrieval] Primary strategies found nothing for '{q}', attempting fallback...")
            results = self._retrieve_with_fallback(q, top_k, expand_with_fact_store)

        return results

    def _retrieve_primary(
        self,
        query: str,
        top_k: int,
        expand_with_fact_store: bool
    ) -> List[RetrieverResult]:
        """
        Primary retrieval strategy (exact query on all channels).

        Returns results from BM25 + Semantic + Exact, fused via RRF.
        """
        # Step 1-3: Parallel retrieval streams
        exact_results = self._search_exact_facts(query)
        lexical_results = self._search_lexical(query, top_k=30)
        semantic_results = self._search_semantic(query, top_k=30)

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
            fused = expander.expand_candidates(fused)

        # Convert to canonical schema
        return self._convert_to_schema(fused[:top_k])

    def _retrieve_with_fallback(
        self,
        query: str,
        top_k: int,
        expand_with_fact_store: bool
    ) -> List[RetrieverResult]:
        """
        Fallback retrieval when primary returns empty.

        Tries:
        1. Query decomposition (key terms separately)
        2. Substring/prefix matching
        3. Semantic search emphasis
        """
        from backend.intelligence.retrieval.query_expansion import QueryExpander

        primary_terms, fallback_terms = QueryExpander.decompose_query(query)

        # Try key terms individually
        all_results = {}
        for term in primary_terms:
            term_results = self._retrieve_primary(term, top_k, expand_with_fact_store=False)
            for r in term_results:
                rid = r.id
                if rid not in all_results:
                    all_results[rid] = r

        if all_results:
            logger.info(f"[Retrieval] Fallback found {len(all_results)} results via key term decomposition")
            return list(all_results.values())[:top_k]

        # Try substrings
        for term in fallback_terms:
            term_results = self._retrieve_primary(term, top_k, expand_with_fact_store=False)
            for r in term_results:
                rid = r.id
                if rid not in all_results:
                    all_results[rid] = r

        if all_results:
            logger.info(f"[Retrieval] Fallback found {len(all_results)} results via substring matching")
            return list(all_results.values())[:top_k]

        logger.info(f"[Retrieval] All fallback strategies failed for '{query}'")
        return []

    def _convert_to_schema(self, docs: List[dict]) -> List[RetrieverResult]:
        """Convert internal dict representation to canonical schema."""
        results = []
        for doc in docs:
            score_type = doc.get("score_type", "unknown")

            if score_type == "lexical":
                schema_result = convert_lexical_result_to_schema(doc)
            elif score_type == "semantic":
                schema_result = convert_semantic_result_to_schema(doc)
            elif score_type == "exact_fact":
                schema_result = convert_exact_result_to_schema(doc)
            else:
                schema_result = convert_lexical_result_to_schema(doc)

            results.append(schema_result)

        return results
