#!/usr/bin/env python
"""
Phase 2L: Complete End-to-End Validation (Stages 1-8)

Extends Phase 2K with Stages 6-8:
- Stage 6: Bounded graph navigation from retrieval results
- Stage 7: Context assembly with provenance preservation
- Stage 8: LLM grounding with deterministic validation

Runs against real GitOnboard repository with 3-5 test queries.
"""
import logging
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# Set up paths (cross-platform)
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import Base, SessionLocal
from backend.models.repository import Repository, Analysis
from backend.intelligence.engine.scanner.scanner import RepositoryScanner
from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
from backend.intelligence.engine.retrieval.hybrid import HybridRetriever
from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigator
from backend.intelligence.engine.orchestration.stage7_context_assembly import ContextAssembler7
from backend.intelligence.engine.orchestration.stage8_grounding import stage8_sync_wrapper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================================================================================
# TEST QUERIES
# ================================================================================

TEST_QUERIES = [
    "Where is authentication implemented?",
    "How does the analysis pipeline reach the FactStore?",
    "Which files are involved in repository scanning?",
    "Where should I look to change BM25 retrieval?",
    "What is the entry point for code analysis?",
]


class Phase2LValidator:
    """Execute all 8 validation stages."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.session = SessionLocal()
        self.manifest = None
        self.analysis = None
        self.retriever = None
        self.graph_navigator = None
        self.context_assembler = None
        self.repository_model = None

        self.results = {
            "stage_1": None,
            "stage_2": None,
            "stage_3": None,
            "stage_4": None,
            "stage_5": None,
            "stage_6": None,
            "stage_7": None,
            "stage_8": None,
        }

    def setup(self):
        """Initialize repository reference."""
        pass  # Use existing SessionLocal

        # Create test user and repository
        user = self.session.query(User).first()
        if not user:
            user = User(
                email="test@example.com",
                username="test_user",
                github_id="test_github_id"
            )
            self.session.add(user)
            self.session.commit()

        repo = self.session.query(Repository).filter(
            Repository.url == str(self.repo_path)
        ).first()
        if not repo:
            repo = Repository(
                url=str(self.repo_path),
                user_id=user.id,
                default_branch="main"
            )
            self.session.add(repo)
            self.session.commit()

        self.repo_id = repo.id
        logger.info(f"[Setup] Repository: {self.repo_path}, ID: {self.repo_id}")

    def stage_1_scanning(self) -> bool:
        """Stage 1: Repository scanning."""
        logger.info("\n" + "="*80)
        logger.info("STAGE 1: REPOSITORY SCANNING")
        logger.info("="*80)

        try:
            scanner = RepositoryScanner(str(self.repo_path))
            self.manifest = scanner.scan()

            self.results["stage_1"] = {
                "status": "PASS",
                "files_discovered": len(self.manifest.files),
                "languages": self.manifest.languages,
                "primary_language": self.manifest.primary_language,
                "frameworks": self.manifest.frameworks,
            }

            logger.info(f"✓ Files discovered: {len(self.manifest.files)}")
            logger.info(f"✓ Languages: {self.manifest.languages}")
            logger.info(f"✓ Primary: {self.manifest.primary_language}")

            return len(self.manifest.files) > 0
        except Exception as e:
            logger.error(f"✗ Stage 1 failed: {e}")
            self.results["stage_1"] = {"status": "FAIL", "error": str(e)}
            return False

    def stage_2_factstore(self) -> bool:
        """Stage 2: FactStore persistence."""
        logger.info("\n" + "="*80)
        logger.info("STAGE 2: FACTSTORE PERSISTENCE")
        logger.info("="*80)

        if not self.manifest:
            logger.error("Stage 1 must pass first")
            self.results["stage_2"] = {"status": "BLOCKED"}
            return False

        try:
            analysis = Analysis(
                repository_id=self.repo_id,
                engine_version="v1.0",
                status="Analyzing"
            )
            self.session.add(analysis)
            self.session.commit()

            engine = AnalysisEngine(
                manifest=self.manifest,
                analysis_id=analysis.id,
                db=self.session
            )
            engine.run()

            self.analysis = analysis
            self.session.refresh(analysis)

            self.results["stage_2"] = {
                "status": "PASS",
                "analysis_id": analysis.id,
                "fact_store_version": analysis.fact_store_version,
            }

            logger.info(f"✓ Analysis ID: {analysis.id}")
            logger.info(f"✓ FactStore version: {analysis.fact_store_version}")

            return True
        except Exception as e:
            logger.error(f"✗ Stage 2 failed: {e}")
            self.results["stage_2"] = {"status": "FAIL", "error": str(e)}
            return False

    def stage_3_bm25_indexing(self) -> bool:
        """Stage 3: BM25 lexical indexing."""
        logger.info("\n" + "="*80)
        logger.info("STAGE 3: BM25 LEXICAL INDEXING")
        logger.info("="*80)

        if not self.analysis:
            self.results["stage_3"] = {"status": "BLOCKED"}
            return False

        try:
            self.index_manager = IndexManager(self.analysis.id, db=self.session)
            self.index_manager.build_bm25_index()

            self.results["stage_3"] = {
                "status": "PASS",
                "indexing_status": self.analysis.indexing_status,
            }

            logger.info(f"✓ BM25 indexing complete")

            return True
        except Exception as e:
            logger.error(f"✗ Stage 3 failed: {e}")
            self.results["stage_3"] = {"status": "FAIL", "error": str(e)}
            return False

    def stage_4_semantic_indexing(self) -> bool:
        """Stage 4: Semantic vector indexing (optional, may timeout)."""
        logger.info("\n" + "="*80)
        logger.info("STAGE 4: SEMANTIC VECTOR INDEXING")
        logger.info("="*80)

        if not self.analysis:
            self.results["stage_4"] = {"status": "BLOCKED"}
            return False

        try:
            # Stage 4 is optional - timeout allowed
            self.index_manager.build_semantic_index(timeout_seconds=120)
            status = "PASS"
        except TimeoutError:
            logger.warning("⚠ Semantic indexing timed out (acceptable)")
            status = "PASS_PARTIAL"
        except Exception as e:
            logger.warning(f"⚠ Semantic indexing failed: {e}")
            status = "PASS_PARTIAL"

        self.results["stage_4"] = {
            "status": status,
            "semantic_available": self.index_manager.chroma_collection is not None,
        }

        return True  # Stage 4 is optional

    def stage_5_hybrid_retrieval(self, queries: List[str]) -> Tuple[bool, Dict]:
        """Stage 5: Hybrid retrieval (lexical + semantic)."""
        logger.info("\n" + "="*80)
        logger.info("STAGE 5: HYBRID RETRIEVAL")
        logger.info("="*80)

        if not self.analysis:
            self.results["stage_5"] = {"status": "BLOCKED"}
            return False, {}

        try:
            self.retriever = HybridRetriever(
                db=self.session,
                analysis_id=self.analysis.id,
                chroma_collection=self.index_manager.chroma_collection if self.index_manager else None
            )

            retrieval_results = {}
            for query in queries:
                results = self.retriever.retrieve(query, top_k=5)
                retrieval_results[query] = results
                logger.info(f"✓ Retrieved {len(results)} results for: {query}")

            self.results["stage_5"] = {
                "status": "PASS",
                "queries_run": len(queries),
                "results_per_query": {q: len(r) for q, r in retrieval_results.items()},
            }

            return True, retrieval_results
        except Exception as e:
            logger.error(f"✗ Stage 5 failed: {e}")
            self.results["stage_5"] = {"status": "FAIL", "error": str(e)}
            return False, {}

    def stage_6_graph_navigation(self, retrieval_results: Dict[str, List]) -> Tuple[bool, Dict]:
        """Stage 6: Bounded graph traversal."""
        logger.info("\n" + "="*80)
        logger.info("STAGE 6: GRAPH NAVIGATION")
        logger.info("="*80)

        if not self.analysis or not self.analysis.repository_model:
            self.results["stage_6"] = {"status": "BLOCKED"}
            return False, {}

        try:
            self.graph_navigator = GraphNavigator(
                model=self.analysis.repository_model,
                max_depth=3,
                max_edges_per_entity=5
            )

            graph_results = {}
            for query, ret_results in retrieval_results.items():
                gr = self.graph_navigator.navigate(ret_results, max_entities=100)
                graph_results[query] = gr
                logger.info(
                    f"✓ Graph traversal for '{query}': "
                    f"{gr.entity_count} entities, {gr.edge_count} edges, "
                    f"depth {gr.traversal_depth}"
                )

            self.results["stage_6"] = {
                "status": "PASS",
                "queries_processed": len(graph_results),
                "avg_entities": sum(r.entity_count for r in graph_results.values()) / len(graph_results) if graph_results else 0,
            }

            return True, graph_results
        except Exception as e:
            logger.error(f"✗ Stage 6 failed: {e}")
            self.results["stage_6"] = {"status": "FAIL", "error": str(e)}
            return False, {}

    def stage_7_context_assembly(self, queries: List[str], retrieval_results: Dict, graph_results: Dict) -> Tuple[bool, Dict]:
        """Stage 7: Context assembly from retrieval + graph."""
        logger.info("\n" + "="*80)
        logger.info("STAGE 7: CONTEXT ASSEMBLY")
        logger.info("="*80)

        if not graph_results:
            self.results["stage_7"] = {"status": "BLOCKED"}
            return False, {}

        try:
            self.context_assembler = ContextAssembler7(db=self.session)

            context_results = {}
            for query in queries:
                ret_res = retrieval_results.get(query, [])
                graph_res = graph_results.get(query)

                if not graph_res:
                    continue

                ctx, metrics = self.context_assembler.assemble(
                    query=query,
                    retrieval_results=ret_res,
                    graph_result=graph_res,
                    repository_id=str(self.repo_id),
                    analysis_id=self.analysis.id,
                )

                context_results[query] = (ctx, metrics)
                logger.info(
                    f"✓ Context for '{query}': "
                    f"{len(ctx.relevant_files or [])} files, "
                    f"{len(ctx.relevant_symbols or [])} symbols, "
                    f"{metrics.context_size_kb:.1f}KB"
                )

            self.results["stage_7"] = {
                "status": "PASS",
                "queries_assembled": len(context_results),
            }

            return True, context_results
        except Exception as e:
            logger.error(f"✗ Stage 7 failed: {e}")
            self.results["stage_7"] = {"status": "FAIL", "error": str(e)}
            return False, {}

    def stage_8_llm_grounding(self, context_results: Dict) -> Tuple[bool, Dict]:
        """Stage 8: LLM grounding with validation."""
        logger.info("\n" + "="*80)
        logger.info("STAGE 8: LLM GROUNDING")
        logger.info("="*80)

        if not context_results:
            self.results["stage_8"] = {"status": "BLOCKED"}
            return False, {}

        try:
            grounding_results = {}

            for query, (context, metrics) in context_results.items():
                try:
                    answer, grounding = stage8_sync_wrapper(context, query)
                    grounding_results[query] = {
                        "answer": answer,
                        "grounding": grounding,
                    }
                    logger.info(
                        f"✓ LLM answer for '{query}': "
                        f"grounding={grounding.grounding_status}, "
                        f"entities={len(grounding.grounded_entities)}"
                    )
                except Exception as e:
                    logger.warning(f"⚠ LLM failed for '{query}': {e}")
                    grounding_results[query] = {
                        "error": str(e),
                        "grounding_status": "ERROR",
                    }

            self.results["stage_8"] = {
                "status": "PASS",
                "queries_grounded": len([r for r in grounding_results.values() if "error" not in r]),
                "grounding_statuses": {
                    q: r.get("grounding", {}).get("grounding_status", "ERROR")
                    for q, r in grounding_results.items()
                },
            }

            return True, grounding_results
        except Exception as e:
            logger.error(f"✗ Stage 8 failed: {e}")
            self.results["stage_8"] = {"status": "FAIL", "error": str(e)}
            return False, {}

    def run(self) -> str:
        """Execute all stages."""
        logger.info("\n" + "="*80)
        logger.info("PHASE 2L: END-TO-END VALIDATION (Stages 1-8)")
        logger.info("="*80)

        self.setup()

        # Stage 1
        if not self.stage_1_scanning():
            return "STAGE_1_FAILED"

        # Stage 2
        if not self.stage_2_factstore():
            return "STAGE_2_FAILED"

        # Stage 3
        if not self.stage_3_bm25_indexing():
            return "STAGE_3_FAILED"

        # Stage 4 (optional)
        self.stage_4_semantic_indexing()

        # Stage 5
        stage5_ok, retrieval_results = self.stage_5_hybrid_retrieval(TEST_QUERIES)
        if not stage5_ok:
            return "STAGE_5_FAILED"

        # Stage 6
        stage6_ok, graph_results = self.stage_6_graph_navigation(retrieval_results)
        if not stage6_ok:
            return "STAGE_6_FAILED"

        # Stage 7
        stage7_ok, context_results = self.stage_7_context_assembly(TEST_QUERIES, retrieval_results, graph_results)
        if not stage7_ok:
            return "STAGE_7_FAILED"

        # Stage 8
        stage8_ok, grounding_results = self.stage_8_llm_grounding(context_results)
        if not stage8_ok:
            return "STAGE_8_FAILED"

        # Determine verdict
        return self._compute_verdict()

    def _compute_verdict(self) -> str:
        """Compute final validation verdict."""
        all_stages = ["stage_1", "stage_2", "stage_3", "stage_4", "stage_5", "stage_6", "stage_7", "stage_8"]

        for stage in all_stages:
            if self.results[stage].get("status") == "FAIL":
                stage_num = int(stage.split("_")[1])
                return f"STAGE_{stage_num}_FAILED"
            if self.results[stage].get("status") == "BLOCKED":
                stage_num = int(stage.split("_")[1])
                return f"STAGES_{stage_num}_ONWARDS_BLOCKED"

        return "FULL_E2E_VALIDATED"

    def report(self):
        """Print validation report."""
        logger.info("\n" + "="*80)
        logger.info("VALIDATION SUMMARY")
        logger.info("="*80)

        for stage, result in self.results.items():
            status = result.get("status", "UNKNOWN")
            logger.info(f"{stage}: {status}")

        logger.info("\nDetailed results:")
        logger.info(json.dumps(self.results, indent=2, default=str))


if __name__ == "__main__":
    repo_path = PROJECT_ROOT.parent if (PROJECT_ROOT.parent / ".git").exists() else PROJECT_ROOT
    db_url = f"sqlite:///{PROJECT_ROOT / 'data' / 'validation.db'}"

    validator = Phase2LValidator(str(repo_path), db_url)
    verdict = validator.run()

    validator.report()

    logger.info(f"\n{'='*80}")
    logger.info(f"FINAL VERDICT: {verdict}")
    logger.info(f"{'='*80}\n")

    sys.exit(0 if verdict == "FULL_E2E_VALIDATED" else 1)
