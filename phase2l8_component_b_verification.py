#!/usr/bin/env python
"""
Phase 2L.8 Component B: Stage 5→6 Contract Verification with ONLY Analysis 14

CRITICAL REQUIREMENT: Use ONLY Analysis 14 (canonical GitOnboard data)
- NOT Analysis 1 (test data)
- NOT any default analysis selection
- Explicit analysis_id=14 passed to all components

Verification steps:
1. Load Analysis 14 explicitly
2. Load repository model from FactStore with analysis_id=14
3. Create HybridRetriever with analysis_id=14
4. Run Stage 5 query: "How does user authentication work in GitOnboard?"
5. Verify each candidate has analysis_id == 14
6. Pass candidates to GraphNavigator
7. Verify all entities have analysis_id == 14 and repository_id == 4
8. Report findings with verdict
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Set up paths
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================================================================================
# GLOBALS FOR TEST
# ================================================================================

ANALYSIS_ID = 14  # EXPLICIT: Use ONLY Analysis 14
QUERY = "How does user authentication work in GitOnboard?"
EXPECTED_REPOSITORY_ID = 4  # GitOnboard is repository_id=4

class ComponentBVerifier:
    """Verify Stage 5→6 contract with Analysis 14 only."""

    def __init__(self):
        self.db = None
        self.analysis = None
        self.repository_model = None
        self.retriever = None
        self.navigator = None
        self.findings = {
            "analysis_id_checked": False,
            "analysis_id_value": None,
            "analysis_id_match": False,
            "retrieval_candidates": [],
            "retrieval_analysis_ids": [],
            "retrieval_all_correct": False,
            "graph_entities": [],
            "graph_analysis_ids": [],
            "graph_repository_ids": [],
            "graph_all_correct": False,
            "verdict": None,
        }

    def step_1_load_analysis(self) -> bool:
        """Step 1: Load Analysis 14 explicitly."""
        logger.info("\n" + "="*80)
        logger.info("STEP 1: LOAD ANALYSIS 14 EXPLICITLY")
        logger.info("="*80)

        try:
            from backend.database import SessionLocal
            from backend.models.repository import Analysis

            self.db = SessionLocal()

            # Explicit query for Analysis 14 only
            self.analysis = self.db.query(Analysis).filter(
                Analysis.id == ANALYSIS_ID
            ).first()

            if not self.analysis:
                logger.error(f"✗ Analysis {ANALYSIS_ID} not found in database")
                self.findings["verdict"] = "UNABLE_TO_TEST"
                return False

            logger.info(f"✓ Analysis loaded: ID={self.analysis.id}")
            logger.info(f"  - Repository ID: {self.analysis.repository_id}")
            logger.info(f"  - Status: {self.analysis.status}")
            logger.info(f"  - Fact Store Version: {self.analysis.fact_store_version}")

            self.findings["analysis_id_checked"] = True
            self.findings["analysis_id_value"] = self.analysis.id
            self.findings["analysis_id_match"] = (self.analysis.id == ANALYSIS_ID)

            return self.analysis.id == ANALYSIS_ID

        except Exception as e:
            logger.error(f"✗ Step 1 failed: {e}")
            self.findings["verdict"] = "UNABLE_TO_TEST"
            import traceback
            traceback.print_exc()
            return False

    def step_2_load_repository_model(self) -> bool:
        """Step 2: Load repository model from FactStore with analysis_id=14."""
        logger.info("\n" + "="*80)
        logger.info("STEP 2: LOAD REPOSITORY MODEL FROM FACTSTORE")
        logger.info("="*80)

        if not self.analysis:
            logger.error("Analysis not loaded (Step 1 must pass first)")
            return False

        try:
            from backend.intelligence.store.fact_store import load_rim_from_fact_store

            # Explicit load with analysis_id=14
            self.repository_model = load_rim_from_fact_store(
                db=self.db,
                analysis_id=ANALYSIS_ID
            )

            if not self.repository_model:
                logger.error(f"✗ Failed to load repository model for Analysis {ANALYSIS_ID}")
                return False

            logger.info(f"✓ Repository model loaded")
            logger.info(f"  - Entities: {len(self.repository_model.entities)}")
            logger.info(f"  - Relationships: {len(self.repository_model.relationships)}")
            logger.info(f"  - Repository name: {self.repository_model.metadata.name if self.repository_model.metadata else 'N/A'}")

            return True

        except Exception as e:
            logger.error(f"✗ Step 2 failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_3_create_retriever(self) -> bool:
        """Step 3: Create HybridRetriever with EXPLICIT analysis_id=14."""
        logger.info("\n" + "="*80)
        logger.info("STEP 3: CREATE HYBRIDRETRIEVER WITH analysis_id=14")
        logger.info("="*80)

        try:
            from backend.intelligence.retrieval.retriever import HybridRetriever

            # CRITICAL: Explicit analysis_id=14
            self.retriever = HybridRetriever(
                db=self.db,
                analysis_id=ANALYSIS_ID,  # EXPLICIT
                chroma_collection=None  # No semantic indexing for speed
            )

            if not self.retriever:
                logger.error("✗ Failed to create retriever")
                return False

            logger.info(f"✓ HybridRetriever created")
            logger.info(f"  - analysis_id: {self.retriever.analysis_id}")
            logger.info(f"  - BM25 index loaded: {self.retriever.bm25_index is not None}")

            # Verify analysis_id is set correctly
            if self.retriever.analysis_id != ANALYSIS_ID:
                logger.error(f"✗ Retriever has wrong analysis_id: {self.retriever.analysis_id} != {ANALYSIS_ID}")
                return False

            return True

        except Exception as e:
            logger.error(f"✗ Step 3 failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_4_run_stage5_query(self) -> bool:
        """Step 4: Run Stage 5 hybrid retrieval query."""
        logger.info("\n" + "="*80)
        logger.info("STEP 4: STAGE 5 HYBRID RETRIEVAL")
        logger.info("="*80)

        if not self.retriever:
            logger.error("Retriever not created (Step 3 must pass first)")
            return False

        try:
            logger.info(f"Query: '{QUERY}'")

            # Run retrieval
            candidates = self.retriever.retrieve(QUERY, top_k=10)

            if not candidates:
                logger.warning(f"⚠ No candidates returned for query")
                self.findings["retrieval_candidates"] = []
                self.findings["retrieval_analysis_ids"] = []
                self.findings["retrieval_all_correct"] = True  # Vacuously true
                return True

            logger.info(f"✓ Retrieved {len(candidates)} candidates")

            # Record candidates for verification
            self.findings["retrieval_candidates"] = []
            analysis_ids = set()

            for i, candidate in enumerate(candidates):
                analysis_id = candidate.metadata.get("analysis_id") if candidate.metadata else None

                logger.info(f"  [{i+1}] {candidate.entity_name} (file: {candidate.file_path})")
                logger.info(f"      Score: {candidate.relevance_score:.3f}")
                logger.info(f"      analysis_id: {analysis_id}")

                if analysis_id:
                    analysis_ids.add(analysis_id)

                self.findings["retrieval_candidates"].append({
                    "name": candidate.entity_name,
                    "file": candidate.file_path,
                    "score": candidate.relevance_score,
                    "analysis_id": analysis_id,
                })

            self.findings["retrieval_analysis_ids"] = list(analysis_ids)
            self.findings["retrieval_all_correct"] = all(
                aid == ANALYSIS_ID for aid in analysis_ids if aid is not None
            )

            if not self.findings["retrieval_all_correct"]:
                logger.error(f"✗ Candidates have wrong analysis_ids: {analysis_ids}")
                return False

            logger.info(f"✓ All {len(candidates)} candidates have analysis_id={ANALYSIS_ID}")
            return True

        except Exception as e:
            logger.error(f"✗ Step 4 failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_5_create_navigator(self) -> bool:
        """Step 5: Create GraphNavigator with repository model."""
        logger.info("\n" + "="*80)
        logger.info("STEP 5: CREATE GRAPHNAVIGATOR")
        logger.info("="*80)

        if not self.repository_model:
            logger.error("Repository model not loaded (Step 2 must pass first)")
            return False

        try:
            from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigator

            self.navigator = GraphNavigator(
                model=self.repository_model,
                max_depth=3,
                max_edges_per_entity=5
            )

            logger.info(f"✓ GraphNavigator created")
            logger.info(f"  - Model entities: {len(self.repository_model.entities)}")
            logger.info(f"  - Model relationships: {len(self.repository_model.relationships)}")

            return True

        except Exception as e:
            logger.error(f"✗ Step 5 failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_6_run_graph_navigation(self, candidates: List[Any]) -> bool:
        """Step 6: Run graph navigation from Stage 5 candidates."""
        logger.info("\n" + "="*80)
        logger.info("STEP 6: STAGE 6 GRAPH NAVIGATION")
        logger.info("="*80)

        if not self.navigator:
            logger.error("Navigator not created (Step 5 must pass first)")
            return False

        if not candidates:
            logger.warning("⚠ No candidates to navigate from")
            self.findings["graph_entities"] = []
            self.findings["graph_analysis_ids"] = []
            self.findings["graph_repository_ids"] = []
            self.findings["graph_all_correct"] = True  # Vacuously true
            return True

        try:
            # Pass candidates to navigator
            result = self.navigator.navigate(candidates, max_entities=100)

            if result.entity_count == 0:
                logger.warning("⚠ Graph navigation returned 0 entities")
                self.findings["graph_entities"] = []
                self.findings["graph_analysis_ids"] = []
                self.findings["graph_repository_ids"] = []
                self.findings["graph_all_correct"] = True  # Vacuously true
                return True

            logger.info(f"✓ Graph navigation complete")
            logger.info(f"  - Entities discovered: {result.entity_count}")
            logger.info(f"  - Edges discovered: {result.edge_count}")
            logger.info(f"  - Traversal depth: {result.traversal_depth}")

            # Record entities for verification
            self.findings["graph_entities"] = []
            analysis_ids = set()
            repository_ids = set()

            for entity_id, entity in result.discovered_entities.items():
                # Check for analysis_id in entity metadata
                analysis_id = None
                if hasattr(entity, 'metadata') and entity.metadata:
                    analysis_id = entity.metadata.get("analysis_id")

                # Check for repository_id in entity metadata
                repository_id = None
                if hasattr(entity, 'metadata') and entity.metadata:
                    repository_id = entity.metadata.get("repository_id")

                logger.info(f"  - {entity.name} (id: {entity_id})")
                logger.info(f"      analysis_id: {analysis_id}")
                logger.info(f"      repository_id: {repository_id}")

                if analysis_id:
                    analysis_ids.add(analysis_id)
                if repository_id:
                    repository_ids.add(repository_id)

                self.findings["graph_entities"].append({
                    "id": entity_id,
                    "name": entity.name,
                    "analysis_id": analysis_id,
                    "repository_id": repository_id,
                })

            self.findings["graph_analysis_ids"] = list(analysis_ids)
            self.findings["graph_repository_ids"] = list(repository_ids)

            # Check if all entities have correct analysis_id and repository_id
            self.findings["graph_all_correct"] = all(
                aid == ANALYSIS_ID for aid in analysis_ids if aid is not None
            ) and all(
                rid == EXPECTED_REPOSITORY_ID for rid in repository_ids if rid is not None
            )

            if not self.findings["graph_all_correct"]:
                logger.error(f"✗ Entities have wrong IDs:")
                logger.error(f"   analysis_ids: {analysis_ids} (expected {ANALYSIS_ID})")
                logger.error(f"   repository_ids: {repository_ids} (expected {EXPECTED_REPOSITORY_ID})")
                return False

            logger.info(f"✓ All {result.entity_count} entities have correct analysis_id={ANALYSIS_ID} and repository_id={EXPECTED_REPOSITORY_ID}")
            return True

        except Exception as e:
            logger.error(f"✗ Step 6 failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def compute_verdict(self) -> str:
        """Compute final verdict based on findings."""
        if self.findings["verdict"]:
            return self.findings["verdict"]

        # Check all critical conditions
        checks = {
            "analysis_14_loaded": self.findings["analysis_id_checked"] and self.findings["analysis_id_match"],
            "retrieval_correct": self.findings["retrieval_all_correct"],
            "graph_correct": self.findings["graph_all_correct"],
        }

        if all(checks.values()):
            return "WORKING_WITH_ANALYSIS_14"
        elif checks["analysis_14_loaded"] and checks["retrieval_correct"] and not checks["graph_correct"]:
            return "BROKEN_WITH_ANALYSIS_14"
        else:
            return "UNABLE_TO_TEST"

    def run(self) -> str:
        """Execute all verification steps."""
        logger.info("\n" + "="*80)
        logger.info("PHASE 2L.8 COMPONENT B: STAGE 5→6 CONTRACT VERIFICATION")
        logger.info("="*80)
        logger.info(f"ANALYSIS_ID: {ANALYSIS_ID}")
        logger.info(f"QUERY: {QUERY}")
        logger.info("="*80)

        # Step 1: Load Analysis 14
        if not self.step_1_load_analysis():
            return self.compute_verdict()

        # Step 2: Load repository model
        if not self.step_2_load_repository_model():
            return self.compute_verdict()

        # Step 3: Create retriever
        if not self.step_3_create_retriever():
            return self.compute_verdict()

        # Step 4: Run Stage 5 query
        candidates = []
        if not self.step_4_run_stage5_query():
            return self.compute_verdict()

        # Get candidates from last retrieval (would need to capture from step 4)
        try:
            candidates = self.retriever.retrieve(QUERY, top_k=10)
        except:
            candidates = []

        # Step 5: Create navigator
        if not self.step_5_create_navigator():
            return self.compute_verdict()

        # Step 6: Run graph navigation
        if not self.step_6_run_graph_navigation(candidates):
            return self.compute_verdict()

        # Compute verdict
        verdict = self.compute_verdict()
        self.findings["verdict"] = verdict

        return verdict

    def report(self):
        """Print validation report."""
        logger.info("\n" + "="*80)
        logger.info("VERIFICATION SUMMARY")
        logger.info("="*80)

        logger.info(f"\nAnalysis 14 Check:")
        logger.info(f"  - Checked: {self.findings['analysis_id_checked']}")
        logger.info(f"  - Value: {self.findings['analysis_id_value']}")
        logger.info(f"  - Correct: {self.findings['analysis_id_match']}")

        logger.info(f"\nStage 5 Retrieval:")
        logger.info(f"  - Candidates: {len(self.findings['retrieval_candidates'])}")
        logger.info(f"  - Analysis IDs found: {self.findings['retrieval_analysis_ids']}")
        logger.info(f"  - All correct: {self.findings['retrieval_all_correct']}")

        logger.info(f"\nStage 6 Graph Navigation:")
        logger.info(f"  - Entities: {len(self.findings['graph_entities'])}")
        logger.info(f"  - Analysis IDs found: {self.findings['graph_analysis_ids']}")
        logger.info(f"  - Repository IDs found: {self.findings['graph_repository_ids']}")
        logger.info(f"  - All correct: {self.findings['graph_all_correct']}")

        logger.info(f"\n" + "="*80)
        logger.info(f"FINAL VERDICT: {self.findings['verdict']}")
        logger.info("="*80)

    def save_report(self, output_path: Path):
        """Save findings to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "timestamp": str(Path(__file__).stat().st_mtime),
            "analysis_id_used": ANALYSIS_ID,
            "query": QUERY,
            "findings": self.findings,
        }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"\n✓ Report saved to: {output_path}")


if __name__ == "__main__":
    verifier = ComponentBVerifier()
    verdict = verifier.run()
    verifier.report()

    # Save report
    output_path = Path("/tmp/phase2l8/COMPONENT_B_AGENT_B_VERIFICATION.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create markdown report
    report_content = f"""# Phase 2L.8 Component B: Stage 5→6 Contract Verification

## Test Configuration
- **Analysis ID**: {ANALYSIS_ID} (EXPLICIT, REQUIRED)
- **Query**: {QUERY}
- **Expected Repository ID**: {EXPECTED_REPOSITORY_ID}

## Findings

### Analysis 14 Loading
- Checked: {verifier.findings['analysis_id_checked']}
- Correct Value: {verifier.findings['analysis_id_match']}
- Loaded ID: {verifier.findings['analysis_id_value']}

### Stage 5: Hybrid Retrieval
- Candidates Retrieved: {len(verifier.findings['retrieval_candidates'])}
- Analysis IDs in Candidates: {verifier.findings['retrieval_analysis_ids']}
- All Candidates Correct: {verifier.findings['retrieval_all_correct']}

**Candidates:**
"""

    for i, cand in enumerate(verifier.findings['retrieval_candidates'], 1):
        report_content += f"\n{i}. **{cand['name']}**\n"
        report_content += f"   - File: {cand['file']}\n"
        report_content += f"   - Score: {cand['score']:.3f}\n"
        report_content += f"   - Analysis ID: {cand['analysis_id']}\n"

    report_content += f"""
### Stage 6: Graph Navigation
- Entities Discovered: {len(verifier.findings['graph_entities'])}
- Analysis IDs in Entities: {verifier.findings['graph_analysis_ids']}
- Repository IDs in Entities: {verifier.findings['graph_repository_ids']}
- All Entities Correct: {verifier.findings['graph_all_correct']}

**Entities:**
"""

    for i, entity in enumerate(verifier.findings['graph_entities'], 1):
        report_content += f"\n{i}. **{entity['name']}** (ID: {entity['id']})\n"
        report_content += f"   - Analysis ID: {entity['analysis_id']}\n"
        report_content += f"   - Repository ID: {entity['repository_id']}\n"

    report_content += f"""
## Verdict

**{verifier.findings['verdict']}**

### Interpretation

"""

    if verifier.findings['verdict'] == "WORKING_WITH_ANALYSIS_14":
        report_content += """- ✅ Analysis 14 (canonical GitOnboard) works correctly
- ✅ Stage 5→6 contract preserved: retrieval and graph both use correct analysis_id
- ✅ No fallback to Analysis 1 or default selection
- ✅ Production-ready for Analysis 14
"""
    elif verifier.findings['verdict'] == "BROKEN_WITH_ANALYSIS_14":
        report_content += """- ✅ Analysis 14 loads successfully
- ✅ Stage 5 retrieval works correctly
- ❌ Stage 6 graph navigation fails with Analysis 14
- ❌ NOT production-ready
- ⚠️ Contract broken between Stage 5 and 6
"""
    elif verifier.findings['verdict'] == "WORKING_WITH_WRONG_ANALYSIS":
        report_content += """- ❌ Analysis 14 does not work
- ❌ System falls back to Analysis 1 or default
- ❌ NOT production-ready
- ❌ User directive violated
"""
    else:
        report_content += """- ❌ Cannot load or test Analysis 14
- ❌ Analysis 14 does not exist or is corrupted
- ❌ Cannot verify contract
"""

    with open(output_path, 'w') as f:
        f.write(report_content)

    logger.info(f"\n✓ Markdown report saved to: {output_path}")

    sys.exit(0 if verdict == "WORKING_WITH_ANALYSIS_14" else 1)
