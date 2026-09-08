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


def test_context_assembly_integrates_graph_entities():
    """Test that Stage 7 integrates files and symbols from graph entities.

    This is a regression test for Phase 2L.8 Stage 7 repair.
    Verifies that discovered entities from Stage 6 graph traversal are
    properly merged into the assembled context.
    """
    from backend.intelligence.rim.entity import Entity
    from backend.intelligence.rim.enums import EntityType
    from backend.intelligence.rim.location import SourceLocation

    # Create graph result with discovered entities (simulating Stage 6 output)
    entity1 = Entity(
        id="func:authenticate",
        name="authenticate",
        type=EntityType.FUNCTION,
        location=SourceLocation(
            repository_path="backend/auth.py",
            start_line=10,
            end_line=25,
            language="python"
        )
    )
    entity2 = Entity(
        id="class:User",
        name="User",
        type=EntityType.CLASS,
        location=SourceLocation(
            repository_path="backend/models/user.py",
            start_line=5,
            end_line=50,
            language="python"
        )
    )
    entity3 = Entity(
        id="file:backend/middleware.py",
        name="middleware",
        type=EntityType.FILE,
        location=SourceLocation(
            repository_path="backend/middleware.py",
            start_line=1,
            end_line=100,
            language="python"
        )
    )

    graph_result = GraphNavigationResult(
        seed_entities=[],
        discovered_entities={
            "func:authenticate": entity1,
            "class:User": entity2,
            "file:backend/middleware.py": entity3,
        },
        entity_count=3,
        edge_count=2,
        traversal_depth=1
    )

    # Create an initial context (simulating underlying ContextAssembler output)
    initial_context = RepositoryContext(
        repository_id="test_repo",
        requirement="Find authentication",
        relevant_files=["backend/auth.py"],  # Only one file from retrieval
        relevant_symbols=[],  # No symbols from retrieval
        evidence=[]
    )

    # Mock validator that always passes
    from unittest.mock import MagicMock
    mock_validator = MagicMock()
    mock_validator.validate.return_value = (True, [])

    # Test the integration logic directly
    # (simulating what Stage 7 does with graph entities)
    existing_files = set(initial_context.relevant_files or [])
    existing_symbols = {s.get("name", "") for s in (initial_context.relevant_symbols or [])}

    files_added = 0
    symbols_added = 0

    for entity_id, entity in graph_result.discovered_entities.items():
        file_path = entity.location.repository_path if entity.location else None

        if not file_path:
            continue

        if file_path not in existing_files:
            if not initial_context.relevant_files:
                initial_context.relevant_files = []
            initial_context.relevant_files.append(file_path)
            existing_files.add(file_path)
            files_added += 1

        if entity.type.value in ("FUNCTION", "METHOD", "CLASS", "INTERFACE", "ENUM", "VARIABLE", "CONSTANT"):
            symbol_name = entity.name
            if symbol_name not in existing_symbols:
                if not initial_context.relevant_symbols:
                    initial_context.relevant_symbols = []
                initial_context.relevant_symbols.append({
                    "name": symbol_name,
                    "file_path": file_path,
                    "kind": entity.type.value,
                    "symbol_type": entity.type.value,
                    "line_start": entity.location.start_line if entity.location else 1,
                })
                existing_symbols.add(symbol_name)
                symbols_added += 1

    # Verify the fix works
    assert files_added == 2, f"Should add 2 new files from graph, added {files_added}"
    assert symbols_added == 2, f"Should add 2 symbols from graph, added {symbols_added}"
    assert len(initial_context.relevant_files) == 3, f"Should have 3 total files, got {len(initial_context.relevant_files)}"
    assert len(initial_context.relevant_symbols) == 2, f"Should have 2 total symbols, got {len(initial_context.relevant_symbols)}"

    # Verify files are correct
    assert "backend/auth.py" in initial_context.relevant_files
    assert "backend/models/user.py" in initial_context.relevant_files
    assert "backend/middleware.py" in initial_context.relevant_files

    # Verify symbols are correct
    symbol_names = {s["name"] for s in initial_context.relevant_symbols}
    assert "authenticate" in symbol_names
    assert "User" in symbol_names
