"""
Unit tests for Stage 7: Context Assembly

Tests context assembly, validation, and budget enforcement.
"""
import pytest
from backend.agent.context.contracts import ContextBudget, RepositoryContext, ContextEvidence
from backend.intelligence.engine.orchestration.stage7_context_assembly import ContextAssemblyValidator, ContextAssemblyMetrics
from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigationResult


@pytest.fixture
def valid_context():
    """Create a valid RepositoryContext."""
    return RepositoryContext(
        repository_id="test_repo",
        requirement="Find authentication",
        relevant_files=["src/auth.py", "src/middleware.py"],
        relevant_symbols=[
            {"name": "authenticate", "full_name": "auth.authenticate"},
            {"name": "login", "full_name": "auth.login"},
        ],
        evidence=[
            ContextEvidence(
                source_type="rim_symbol",
                source_id="func:authenticate",
                summary="authenticate function in auth module",
                data={"file": "src/auth.py"}
            ),
            ContextEvidence(
                source_type="rim_file",
                source_id="file:src/auth.py",
                summary="Authentication module",
                data={"path": "src/auth.py"}
            ),
        ]
    )


@pytest.fixture
def empty_context():
    """Create an empty RepositoryContext."""
    return RepositoryContext(
        repository_id="test_repo",
        requirement="Find something"
    )


@pytest.fixture
def graph_result():
    """Create a sample GraphNavigationResult."""
    return GraphNavigationResult(
        seed_entities=[],
        entity_count=5,
        edge_count=8,
        traversal_depth=2
    )


def test_context_assembly_validator_valid_context(valid_context, graph_result):
    """Test validator accepts valid context."""
    passed, errors = ContextAssemblyValidator.validate(valid_context, graph_result, "test query")

    assert passed, f"Should validate: {errors}"
    assert len(errors) == 0


def test_context_assembly_validator_empty_context(empty_context, graph_result):
    """Test validator rejects empty context."""
    passed, errors = ContextAssemblyValidator.validate(empty_context, graph_result, "test query")

    assert not passed, "Should reject empty context"
    assert len(errors) > 0
    assert any("files" in e.lower() for e in errors), "Should note missing files"


def test_context_assembly_validator_missing_requirement(valid_context, graph_result):
    """Test validator checks requirement field."""
    valid_context.requirement = None
    passed, errors = ContextAssemblyValidator.validate(valid_context, graph_result, "test query")

    assert not passed, "Should reject missing requirement"


def test_context_assembly_validator_too_many_files(valid_context, graph_result):
    """Test validator enforces file count limits."""
    # Add many files to exceed limit
    valid_context.relevant_files = [f"file_{i}.py" for i in range(100)]
    passed, errors = ContextAssemblyValidator.validate(valid_context, graph_result, "test query")

    assert not passed, "Should reject too many files"
    assert any("too many" in e.lower() for e in errors)


def test_context_assembly_validator_too_many_symbols(valid_context, graph_result):
    """Test validator enforces symbol count limits."""
    # Add many symbols
    valid_context.relevant_symbols = [{"name": f"sym_{i}"} for i in range(150)]
    passed, errors = ContextAssemblyValidator.validate(valid_context, graph_result, "test query")

    assert not passed, "Should reject too many symbols"
    assert any("symbol" in e.lower() for e in errors)


def test_context_assembly_validator_evidence_validation(valid_context, graph_result):
    """Test validator checks evidence structure."""
    # Create evidence with missing fields
    valid_context.evidence[0].source_type = None
    passed, errors = ContextAssemblyValidator.validate(valid_context, graph_result, "test query")

    assert not passed, "Should reject invalid evidence"


def test_context_assembly_budget_constraints():
    """Test ContextBudget constraints."""
    budget = ContextBudget(
        max_files=10,
        max_symbols=20,
        max_routes=5,
        max_total_evidence_size_kb=100
    )

    assert budget.max_files == 10
    assert budget.max_symbols == 20
    assert budget.max_total_evidence_size_kb == 100


def test_context_assembly_metrics_creation():
    """Test ContextAssemblyMetrics creation."""
    metrics = ContextAssemblyMetrics(
        query="test query",
        retrieval_anchors=3,
        graph_entities=10,
        graph_edges=15,
        selected_files=["a.py", "b.py"],
        selected_symbols=["func1", "func2"],
        context_size_kb=42.5,
        evidence_count=5,
        configured_budgets={"max_files": 15, "max_symbols": 30},
        assembly_time=0.25,
        validation_passed=True,
        validation_errors=[]
    )

    assert metrics.query == "test query"
    assert metrics.retrieval_anchors == 3
    assert metrics.validation_passed is True
    assert len(metrics.validation_errors) == 0


def test_context_assembly_metrics_with_errors():
    """Test ContextAssemblyMetrics with validation errors."""
    metrics = ContextAssemblyMetrics(
        query="test query",
        retrieval_anchors=0,
        graph_entities=0,
        graph_edges=0,
        selected_files=[],
        selected_symbols=[],
        context_size_kb=0.0,
        evidence_count=0,
        configured_budgets={},
        assembly_time=0.1,
        validation_passed=False,
        validation_errors=["No files selected", "No evidence"]
    )

    assert metrics.validation_passed is False
    assert len(metrics.validation_errors) == 2
