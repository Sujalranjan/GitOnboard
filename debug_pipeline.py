#!/usr/bin/env python
"""
Comprehensive Pipeline Debugging Script

Logs and verifies EVERY step of the 8-stage pipeline with actual data inspection.
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("PIPELINE_DEBUG")

def verify_retrieval_results(results, analysis_id):
    """Verify retrieval results are valid."""
    logger.info(f"\n{'='*80}")
    logger.info("STAGE 5: RETRIEVAL VERIFICATION")
    logger.info(f"{'='*80}")

    if not results:
        logger.error("❌ RETRIEVAL FAILED: Empty results!")
        return False

    logger.info(f"✓ Retrieved {len(results)} results")

    for i, result in enumerate(results[:3]):
        logger.info(f"\nResult {i+1}:")
        logger.info(f"  ID: {result.id}")
        logger.info(f"  Entity Name: {result.entity_name}")
        logger.info(f"  Entity Type: {result.entity_type}")
        logger.info(f"  File Path: {result.file_path}")
        logger.info(f"  Score: {result.score}")

        # Verify file exists
        file_path = Path(result.file_path) if result.file_path else None
        if file_path and file_path.exists():
            size = file_path.stat().st_size
            logger.info(f"  File Size: {size} bytes ✓")
        elif file_path:
            logger.warning(f"  File NOT found at {file_path} ❌")
        else:
            logger.warning(f"  No file path in result ❌")

    return True


def verify_graph_navigation(navigator, retrieval_results, model):
    """Verify graph navigation works with retrieval results."""
    logger.info(f"\n{'='*80}")
    logger.info("STAGE 6: GRAPH NAVIGATION VERIFICATION")
    logger.info(f"{'='*80}")

    if not retrieval_results:
        logger.error("❌ No retrieval results to navigate from")
        return None

    logger.info(f"Input: {len(retrieval_results)} retrieval results")
    logger.info(f"Model: {len(model.entities)} entities, {len(model.relationships)} relationships")

    # Check if retrieval result IDs exist in model
    logger.info("\nMatching retrieval results to model entities:")
    matched = 0
    for ret_result in retrieval_results[:3]:
        if ret_result.id in model.entities:
            entity = model.entities[ret_result.id]
            logger.info(f"  ✓ {ret_result.entity_name} (ID: {ret_result.id}) found in model")
            matched += 1
        else:
            logger.warning(f"  ❌ {ret_result.entity_name} (ID: {ret_result.id}) NOT in model")

    logger.info(f"\nMatched: {matched}/{min(3, len(retrieval_results))}")

    if matched == 0:
        logger.error("❌ GRAPH NAVIGATION WILL FAIL: No retrieval results match model entities!")
        return None

    # Run navigation
    try:
        graph_result = navigator.navigate(retrieval_results, max_entities=100)
        logger.info(f"\n✓ Graph Navigation Result:")
        logger.info(f"  Discovered Entities: {graph_result.entity_count}")
        logger.info(f"  Edges: {graph_result.edge_count}")
        logger.info(f"  Traversal Depth: {graph_result.traversal_depth}")
        logger.info(f"  Validation Errors: {len(graph_result.validation_errors)}")

        if graph_result.validation_errors:
            for err in graph_result.validation_errors[:3]:
                logger.warning(f"    - {err}")

        if graph_result.entity_count == 0:
            logger.error("❌ No entities discovered! Navigation didn't work.")
            return None

        return graph_result
    except Exception as e:
        logger.error(f"❌ Graph navigation failed: {e}", exc_info=True)
        return None


def verify_context_assembly(assembler, retrieval_results, graph_result, query, analysis_id, repo_id):
    """Verify context assembly works and produces relevant files."""
    logger.info(f"\n{'='*80}")
    logger.info("STAGE 7: CONTEXT ASSEMBLY VERIFICATION")
    logger.info(f"{'='*80}")

    if not graph_result:
        logger.error("❌ No graph result to assemble context from")
        return None

    logger.info(f"Query: '{query}'")
    logger.info(f"Input: {len(retrieval_results)} retrieval results + {graph_result.entity_count} graph entities")

    try:
        context, metrics = assembler.assemble(
            query=query,
            retrieval_results=retrieval_results,
            graph_result=graph_result,
            repository_id=str(repo_id),
            analysis_id=analysis_id,
        )

        logger.info(f"\n✓ Context Assembled:")
        logger.info(f"  Files Selected: {len(context.relevant_files or [])}")
        logger.info(f"  Symbols Selected: {len(context.relevant_symbols or [])}")
        logger.info(f"  Context Size: {metrics.context_size_kb:.1f}KB")

        # Verify files exist and have content
        if context.relevant_files:
            logger.info("\nSelected Files (first 3):")
            for i, file in enumerate(context.relevant_files[:3]):
                file_path = Path(file) if file else None
                if file_path and file_path.exists():
                    content_preview = file_path.read_text()[:100]
                    logger.info(f"  {i+1}. {file} ({file_path.stat().st_size} bytes)")
                    logger.info(f"     Preview: {content_preview}...")
                else:
                    logger.warning(f"  {i+1}. {file} - NOT FOUND ❌")

        return context
    except Exception as e:
        logger.error(f"❌ Context assembly failed: {e}", exc_info=True)
        return None


def verify_llm_grounding(context, query):
    """Verify LLM grounding works and answer is grounded."""
    logger.info(f"\n{'='*80}")
    logger.info("STAGE 8: LLM GROUNDING VERIFICATION")
    logger.info(f"{'='*80}")

    if not context:
        logger.error("❌ No context provided to LLM")
        return None

    logger.info(f"Query: '{query}'")
    logger.info(f"Context Files: {len(context.relevant_files or [])}")
    logger.info(f"Context Size: {len(str(context))} characters")

    try:
        from backend.intelligence.engine.orchestration.stage8_grounding import stage8_sync_wrapper

        answer, grounding = stage8_sync_wrapper(context, query)

        logger.info(f"\n✓ LLM Grounding Result:")
        logger.info(f"  Answer: {answer[:200]}...")
        logger.info(f"  Grounding Status: {grounding.grounding_status}")
        logger.info(f"  Grounded Entities: {len(grounding.grounded_entities)}")

        if grounding.grounding_status == "ungrounded":
            logger.error("❌ ANSWER IS UNGROUNDED - Not supported by context")
        elif grounding.grounding_status == "partial":
            logger.warning("⚠️  ANSWER IS PARTIALLY GROUNDED - Some claims not supported")
        else:
            logger.info("✓ Answer is properly grounded")

        return (answer, grounding)
    except Exception as e:
        logger.error(f"❌ LLM grounding failed: {e}", exc_info=True)
        return None


def run_full_debug():
    """Run complete pipeline with full verification."""
    from backend.database import SessionLocal
    from backend.models.repository import Repository, Analysis
    from backend.routers.repo.services.analysis import get_latest_analysis
    from backend.intelligence.retrieval.retriever import HybridRetriever
    from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigator
    from backend.intelligence.engine.orchestration.stage7_context_assembly import ContextAssembler7

    db = SessionLocal()

    try:
        # Get repo and analysis
        logger.info("Fetching repository and analysis...")
        repo = db.query(Repository).first()
        if not repo:
            logger.error("❌ No repository found in database")
            return

        logger.info(f"✓ Repository: {repo.url}")

        analysis = db.query(Analysis).filter(Analysis.repository_id == repo.id).order_by(Analysis.created_at.desc()).first()
        if not analysis:
            logger.error("❌ No analysis found")
            return

        logger.info(f"✓ Analysis ID: {analysis.id}")

        # Check if model exists
        from backend.models.repository import AnalysisArtifact
        art = db.query(AnalysisArtifact).filter(
            AnalysisArtifact.analysis_id == analysis.id,
            AnalysisArtifact.type == "core_model"
        ).first()

        if not art or not art.blob_data:
            logger.error("❌ No model artifact found - need to run Stage 1 first")
            return

        # Load model
        from backend.intelligence.rim.serialization import deserialize_rim
        model = deserialize_rim(art.blob_data.decode("utf-8"))
        logger.info(f"✓ Model loaded: {len(model.entities)} entities, {len(model.relationships)} relationships")

        if len(model.relationships) == 0:
            logger.error("❌ CRITICAL: Model has 0 relationships - analysis incomplete!")
            return

        # Test query
        query = "How does login work?"

        # Stage 5: Retrieval
        logger.info(f"\n{'='*80}")
        logger.info("STAGE 5: HYBRID RETRIEVAL")
        logger.info(f"{'='*80}")

        retriever = HybridRetriever(db=db, analysis_id=analysis.id)
        retrieval_results = retriever.retrieve(query, top_k=5)

        if not verify_retrieval_results(retrieval_results, analysis.id):
            return

        # Stage 6: Graph Navigation
        from backend.intelligence import QueryLayer
        query_layer = QueryLayer(model)
        navigator = GraphNavigator(model=model, max_depth=3, max_edges_per_entity=5)

        graph_result = verify_graph_navigation(navigator, retrieval_results, model)
        if not graph_result:
            return

        # Stage 7: Context Assembly
        assembler = ContextAssembler7(db=db)
        context = verify_context_assembly(assembler, retrieval_results, graph_result, query, analysis.id, repo.id)
        if not context:
            return

        # Stage 8: LLM Grounding
        result = verify_llm_grounding(context, query)
        if not result:
            return

        logger.info(f"\n{'='*80}")
        logger.info("PIPELINE VERIFICATION COMPLETE ✓")
        logger.info(f"{'='*80}")

    finally:
        db.close()


if __name__ == "__main__":
    run_full_debug()
