"""
Automated unit tests for benchmark evaluation metrics:
- 4-quadrant gapless TrajectoryValidity partition
- Recall@K (K in 1, 3, 5, 10)
- 3-tier relevant evidence precision (supporting files not penalized)
- Binary decoy hit & continuous decoy file rate
- Tool efficiency & redundancy metrics
- Adversarial claim entailment detection (Redis in qa_loop.py)
"""
import pytest
from backend.evaluation.schemas import (
    AnswerMetrics,
    ClaimEntailmentResult,
    FailureCategory,
    QuestionBenchmarkSpec,
    RetrievalMetrics,
    ToolEfficiencyMetrics,
    TrajectoryTurn,
    TrajectoryValidity,
)
from backend.evaluation.evaluator import (
    attribute_primary_failure,
    calculate_retrieval_metrics,
    calculate_tool_efficiency,
    classify_trajectory_validity,
    extract_citations,
)


@pytest.fixture
def mock_benchmark_spec():
    return QuestionBenchmarkSpec(
        id="T01",
        repository="test_repo",
        repository_commit="abc1234",
        question="How does authentication work?",
        category="security",
        answer_type="flow",
        difficulty="L3",
        required_evidence=[
            "src/auth.py",
            "src/tokens.py",
        ],
        supporting_evidence=[
            "src/models.py",
            "src/config.py",
        ],
        decoy_files=[
            "src/unrelated_analytics.py",
        ],
        expected_symbols=["login", "verify_token"],
        expected_concepts=["JWT", "token refresh"],
        expected_tool_capabilities=["search_repository", "read_file", "get_code_relationships"],
        expected_answer_points=[
            "Validates user credentials against database",
            "Generates JWT access and refresh tokens",
        ],
        expected_answer_structure=["validation", "token generation"],
    )


def test_trajectory_validity_exhaustive_partition():
    """Verifies all 4 quadrants of trajectory validity partition at tau = 0.75."""
    # 1. VALID: correctness >= 0.75 and recall >= 0.75
    assert classify_trajectory_validity(correctness=0.90, evidence_recall=0.80) == TrajectoryValidity.VALID
    assert classify_trajectory_validity(correctness=0.75, evidence_recall=0.75) == TrajectoryValidity.VALID

    # 2. LUCKY_CORRECT: correctness >= 0.75 and recall < 0.75 (including the borderline 0.90 / 0.60 case)
    assert classify_trajectory_validity(correctness=0.90, evidence_recall=0.60) == TrajectoryValidity.LUCKY_CORRECT
    assert classify_trajectory_validity(correctness=0.80, evidence_recall=0.20) == TrajectoryValidity.LUCKY_CORRECT
    assert classify_trajectory_validity(correctness=0.75, evidence_recall=0.74) == TrajectoryValidity.LUCKY_CORRECT

    # 3. INSUFFICIENT_EVIDENCE: correctness < 0.75 and recall < 0.75
    assert classify_trajectory_validity(correctness=0.40, evidence_recall=0.30) == TrajectoryValidity.INSUFFICIENT_EVIDENCE
    assert classify_trajectory_validity(correctness=0.70, evidence_recall=0.70) == TrajectoryValidity.INSUFFICIENT_EVIDENCE

    # 4. INCORRECT: correctness < 0.75 and recall >= 0.75 (found evidence but reasoning failed)
    assert classify_trajectory_validity(correctness=0.40, evidence_recall=0.90) == TrajectoryValidity.INCORRECT
    assert classify_trajectory_validity(correctness=0.70, evidence_recall=0.85) == TrajectoryValidity.INCORRECT


def test_retrieval_metrics_precision_recall_and_recall_at_k(mock_benchmark_spec):
    """Verifies 3-tier precision, Recall@K, and decoy metrics."""
    # Retrieved 4 files: 1 required, 2 supporting, 1 decoy
    retrieved = [
        "src/models.py",       # supporting
        "src/auth.py",         # required
        "src/config.py",       # supporting
        "src/unrelated_analytics.py", # decoy
    ]

    metrics = calculate_retrieval_metrics(retrieved, mock_benchmark_spec)

    # Required recall: 1 found out of 2 required ("src/auth.py" found, "src/tokens.py" missed)
    assert metrics.evidence_recall == 0.5
    assert "src/auth.py" in metrics.required_evidence_found
    assert "src/tokens.py" in metrics.required_evidence_missed

    # Relevant precision: 3 relevant files (1 required + 2 supporting) out of 4 retrieved = 3/4 = 0.75
    # Crucial: supporting files are NOT penalized!
    assert metrics.relevant_evidence_precision == 0.75

    # Recall@K:
    # Top 1: ["src/models.py"] -> 0 required found -> Recall@1 = 0.0
    assert metrics.recall_at_1 == 0.0
    # Top 2: ["src/models.py", "src/auth.py"] -> 1 required found -> Recall@2 = 0.5
    # Top 3: ["src/models.py", "src/auth.py", "src/config.py"] -> 1 required found -> Recall@3 = 0.5
    assert metrics.recall_at_3 == 0.5
    # Top 5: all 4 retrieved -> 1 required found -> Recall@5 = 0.5
    assert metrics.recall_at_5 == 0.5

    # Decoy Metrics:
    assert metrics.decoy_hit == 1
    assert metrics.decoy_file_rate == 1.0  # 1 decoy accessed out of 1 available
    assert "src/unrelated_analytics.py" in metrics.decoy_evidence_used


def test_tool_efficiency_and_redundancy():
    """Verifies tool efficiency, redundancy rate, and time to first useful evidence."""
    turns = [
        TrajectoryTurn(
            turn_index=0,
            tool_name="search_repository",
            arguments={"query": "auth"},
            duration_ms=250.0,
            is_success=True,
        ),
        TrajectoryTurn(
            turn_index=1,
            tool_name="read_file",
            arguments={"path": "src/models.py", "start_line": 1, "end_line": 50},
            duration_ms=400.0,
            is_success=True,
        ),
        # Required evidence hit on turn 2
        TrajectoryTurn(
            turn_index=2,
            tool_name="read_file",
            arguments={"path": "src/auth.py", "start_line": 1, "end_line": 50},
            duration_ms=300.0,
            is_success=True,
        ),
        # Redundant duplicate call
        TrajectoryTurn(
            turn_index=3,
            tool_name="read_file",
            arguments={"path": "src/auth.py", "start_line": 1, "end_line": 50},
            duration_ms=100.0,
            is_success=True,
        ),
        # Failed call
        TrajectoryTurn(
            turn_index=4,
            tool_name="read_file",
            arguments={"path": "non_existent.py"},
            duration_ms=50.0,
            is_success=False,
        ),
    ]

    required = ["src/auth.py", "src/tokens.py"]
    eff = calculate_tool_efficiency(turns, required)

    assert eff.tool_calls == 5
    assert eff.successful_tool_calls == 4
    assert eff.failed_tool_calls == 1
    assert eff.redundant_tool_calls == 1
    assert eff.unique_files_read == 2  # src/models.py and src/auth.py
    assert eff.search_iterations == 1
    assert eff.tool_success_rate == 0.8
    assert eff.tool_redundancy_rate == 0.2

    # Time to first useful evidence should be turn 0 (250) + turn 1 (400) + turn 2 (300) = 950ms
    assert eff.time_to_first_useful_evidence_ms == 950.0


def test_citation_extraction(mock_benchmark_spec):
    """Verifies citation extraction requiring presence in retrieved_files."""
    answer = (
        "Authentication is handled in `src/auth.py` where credentials are validated. "
        "Tokens are issued in `src/tokens.py` and saved using `src/models.py`. "
        "A hallucinated file `src/fake_service.py` is also mentioned."
    )

    known_files = {"src/auth.py", "src/tokens.py", "src/models.py", "src/config.py"}
    retrieved = ["src/auth.py", "src/tokens.py", "src/models.py"]

    # When retrieved files are provided
    cit = extract_citations(answer, mock_benchmark_spec, retrieved_files=retrieved, known_repo_files=known_files)
    assert cit.citation_presence is True
    assert "src/auth.py" in cit.valid_citations
    assert "src/tokens.py" in cit.valid_citations
    assert "src/models.py" in cit.valid_citations
    assert "src/fake_service.py" in cit.invalid_citations
    assert cit.citation_correctness == 0.75
    assert cit.citation_completeness == 1.0

    # Model Prior case: zero files retrieved -> citations must have 0.0 correctness
    cit_prior = extract_citations(answer, mock_benchmark_spec, retrieved_files=[], known_repo_files=known_files)
    assert cit_prior.citation_presence is True
    assert cit_prior.citation_correctness == 0.0
    assert len(cit_prior.valid_citations) == 0
    assert len(cit_prior.invalid_citations) == 4


def test_primary_failure_attribution():
    """Verifies failure categorization distinguishing UNNECESSARY_TOOL_USE, INVALID_TOOL_USE, FAILED_TOOL_SELECTION."""
    retrieval_ok = RetrievalMetrics(evidence_recall=1.0, cross_repo_leakage_rate=0.0)
    retrieval_fail = RetrievalMetrics(evidence_recall=0.2, cross_repo_leakage_rate=0.0)
    retrieval_leak = RetrievalMetrics(evidence_recall=1.0, cross_repo_leakage_rate=0.25)

    eff_clean = ToolEfficiencyMetrics(tool_calls=5, failed_tool_calls=0, search_iterations=2)
    eff_invalid = ToolEfficiencyMetrics(tool_calls=5, invalid_tool_calls=2, failed_tool_calls=2, search_iterations=1)
    eff_failed_selection = ToolEfficiencyMetrics(tool_calls=5, failed_tool_selections=1, search_iterations=0)
    eff_unnecessary = ToolEfficiencyMetrics(tool_calls=6, unnecessary_tool_calls=2, search_iterations=2)

    ans_good = AnswerMetrics(groundedness=1.0, completeness=0.9)
    ans_hallu = AnswerMetrics(groundedness=0.2, completeness=0.9)

    # 1. Leakage takes absolute priority
    cat = attribute_primary_failure(TrajectoryValidity.VALID, retrieval_leak, eff_clean, ans_good)
    assert cat == FailureCategory.CROSS_REPO_LEAKAGE

    # 2. Hallucination takes second priority
    cat = attribute_primary_failure(TrajectoryValidity.INCORRECT, retrieval_ok, eff_clean, ans_hallu)
    assert cat == FailureCategory.HALLUCINATION

    # 3. Invalid tool use (tool errored or unsupported)
    cat = attribute_primary_failure(TrajectoryValidity.INSUFFICIENT_EVIDENCE, retrieval_fail, eff_invalid, ans_good)
    assert cat == FailureCategory.INVALID_TOOL_USE

    # 4. Failed tool selection (wrong choice materially prevented retrieval)
    cat = attribute_primary_failure(TrajectoryValidity.INSUFFICIENT_EVIDENCE, retrieval_fail, eff_failed_selection, ans_good)
    assert cat == FailureCategory.FAILED_TOOL_SELECTION

    # 5. Retrieval failure
    cat = attribute_primary_failure(TrajectoryValidity.INSUFFICIENT_EVIDENCE, retrieval_fail, eff_clean, ans_good)
    assert cat == FailureCategory.RETRIEVAL_FAILURE

    # 6. Unnecessary tool use with correct answer does NOT fail trajectory
    validity = classify_trajectory_validity(correctness=0.9, evidence_recall=0.9)
    assert validity == TrajectoryValidity.VALID
    cat_valid = attribute_primary_failure(validity, retrieval_ok, eff_unnecessary, ans_good)
    assert cat_valid == FailureCategory.NONE
    assert eff_unnecessary.unnecessary_tool_calls == 2
