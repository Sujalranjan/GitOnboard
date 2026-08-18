import pytest

try:
    from evaluation.evaluate_phase2_recall import run_phase2_benchmark
    HAS_PHASE2_RECALL = True
except ImportError:
    HAS_PHASE2_RECALL = False


@pytest.mark.asyncio
async def test_phase2_retrieval_and_summary_recall():
    """
    Evaluates that Retrieval Recall is >= 95% and End-to-End Recall is >= 90%
    across all 50 curated ground-truth facts.
    """
    if not HAS_PHASE2_RECALL:
        pytest.skip("evaluation.evaluate_phase2_recall not available")
    await run_phase2_benchmark()

