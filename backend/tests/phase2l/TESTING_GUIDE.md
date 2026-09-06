# Phase 2L Testing Guide

## Overview

The Phase 2L test suite validates the inspection tools, context management system, token accounting, and A/B experiment framework for comparing bulk-context vs. interactive-tools approaches.

## File Structure

```
backend/tests/phase2l/
├── __init__.py                 # Package initialization
├── conftest.py                 # pytest fixtures (shared test setup)
├── test_context_lifecycle.py   # Context manager tests (34 tests)
├── test_inspection_tools.py    # Repository tools tests (31 tests)
├── test_token_accounting.py    # Token accounting tests (30 tests)
├── experiment_framework.py     # A/B experiment framework (core classes)
├── experiment_runner.py        # Experiment orchestration (runner + utilities)
├── fixtures.py                 # Test data and helper factories
└── TESTING_GUIDE.md           # This file
```

## Running Tests

### Run all Phase 2L tests
```bash
uv run pytest backend/tests/phase2l/ -v
```

### Run specific test file
```bash
uv run pytest backend/tests/phase2l/test_context_lifecycle.py -v
```

### Run specific test class
```bash
uv run pytest backend/tests/phase2l/test_token_accounting.py::TestBudgetCheckpoint -v
```

### Run specific test
```bash
uv run pytest backend/tests/phase2l/test_context_lifecycle.py::TestContextManagerAddItem::test_add_item_assigns_unique_id -v
```

### Run with detailed output
```bash
uv run pytest backend/tests/phase2l/ -vv --tb=short
```

### Run with coverage
```bash
uv run pytest backend/tests/phase2l/ --cov=backend.intelligence.context_management --cov=backend.repository_tools
```

## Test Organization

### PART A: Context Lifecycle Tests (`test_context_lifecycle.py`) - 34 tests

Tests ContextManager and context item lifecycle:

**TestContextManagerAddItem** (8 tests)
- Unique ID assignment
- Initial state verification
- Token estimation
- Priority assignment (both override and policy-based)
- Retrieval source recording
- Timestamp tracking

**TestContextManagerListContext** (4 tests)
- Active context filtering
- Dropping and compression state exclusion
- Empty manager handling

**TestContextManagerDrop** (5 tests)
- State transitions
- Protected item preservation
- Content preservation
- Multiple item drops

**TestContextManagerReRequest** (3 tests)
- Dropped item reactivation
- Error handling for nonexistent items

**TestContextManagerSummarize** (6 tests)
- Compression workflow
- Original item marking as REFERENCE
- Protected item protection
- Token savings calculation
- Original accessibility

**TestContextManagerTokenAccounting** (4 tests)
- Token accumulation
- Peak token tracking
- Utilization calculation
- Budget checkpoint thresholds

**TestContextManagerStatistics** (3 tests)
- Statistics structure validation
- Priority-based counting
- State-based counting

### PART B: Inspection Tools Tests (`test_inspection_tools.py`) - 31 tests

Tests repository inspection tools (read_file, find_files, search_code, etc.):

**TestRepositoryToolLayerReadFile** (6 tests)
- Basic file reading
- Partial range reading
- Complete content delivery
- Line numbering
- Line range clamping
- Error handling

**TestRepositoryToolLayerFindFiles** (4 tests)
- Pattern matching
- Limit enforcement
- Metadata inclusion
- Empty result handling

**TestRepositoryToolLayerSearchCode** (6 tests)
- Basic lexical search
- Pattern matching
- Result limiting
- Metadata inclusion
- Case-insensitive search
- Regex support

**TestRepositoryToolLayerGetSymbol** (2 tests)
- Symbol lookup
- Database requirement

**TestRepositoryToolLayerGetFileOutline** (2 tests)
- Outline structure
- Database requirement

**TestRepositoryToolLayerCallGraph** (4 tests)
- Caller lookup
- Callee lookup
- Database requirement

**TestRepositoryToolLayerPathValidation** (3 tests)
- Valid path handling
- Path traversal blocking
- Directory exclusion

### PART C: Token Accounting Tests (`test_token_accounting.py`) - 30 tests

Tests token estimation, budget tracking, and checkpoint calculation:

**TestTokenEstimation** (5 tests)
- Empty data handling
- Small data estimation
- Large data scaling
- Complex structure handling
- Non-serializable fallback

**TestTokenEstimationFromText** (4 tests)
- Empty text handling
- Small text estimation
- Large text scaling
- Multiline text support

**TestBudgetCheckpoint** (14 tests)
- Initialization
- Utilization calculation
- Percentage calculation
- Status levels (normal, moderate, caution, high, critical)
- Boundary testing at each threshold
- Zero budget handling
- String representation

**TestEvaluateBudgetStatus** (5 tests)
- Status evaluation function
- All status level thresholds

**TestTokenBudgetEnforcement** (2 tests)
- Enforcement logic at critical level
- Token addition policies

**TestTokenAccountingIntegration** (2 tests)
- Workflow integration
- Text vs. dict estimation consistency

## Test Framework Components

### Core Classes

#### ExperimentConfig
Specifies experiment parameters:
- Query to analyze
- Workspace path
- Experiment type (BULK_CONTEXT or INTERACTIVE_TOOLS)
- Output directory
- Recording options (tool calls, tokens, files accessed)

#### ExperimentResult
Records results and metrics from a single experiment:
- Query and experiment type
- Files/symbols selected (bulk context)
- Tool calls made (interactive tools)
- Context size metrics
- Token usage
- Answer quality assessment
- Timing information

#### ComparisonReport
Compares results from both experiments:
- Context size advantage analysis
- Tool efficiency metrics
- Quality comparison
- Serialization to dict/JSON

#### ExperimentRecorder
Records detailed execution traces:
- Tool call logging
- File access tracking
- Event recording
- JSON serialization for audit/replay

#### ExperimentHarness
Orchestrates experiments:
- Runs bulk context experiment
- Runs interactive tools experiment
- Compares results

#### ExperimentRunner
High-level experiment orchestration:
- Runs complete A/B experiments
- Runs individual experiment types
- Supports multiple queries
- Aggregates results

### Test Fixtures

Common fixtures available in `conftest.py`:

```python
@pytest.fixture
def context_manager():
    """ContextManager with 100K token budget"""

@pytest.fixture
def sample_evidence():
    """Generic ContextEvidence for testing"""

@pytest.fixture
def high_priority_evidence():
    """User requirement evidence (PROTECTED priority)"""

@pytest.fixture
def low_priority_evidence():
    """Low-relevance evidence (DISPOSABLE priority)"""

@pytest.fixture
def rim_symbol_evidence():
    """Critical RIM symbol evidence"""

@pytest.fixture
def temp_test_file():
    """Temporary Python file for testing"""

@pytest.fixture
def mock_db_session():
    """Mock database session"""
```

### Test Data Factories

Helper classes in `fixtures.py`:

**SampleEvidenceFactory**
- `retrieval_match()`: Retrieval evidence
- `rim_symbol()`: Critical symbol
- `rim_route()`: Control flow route
- `user_requirement()`: User requirement
- `expansion_evidence()`: Low-priority expansion
- `batch_evidence()`: Multiple items

**TestQueries**
- `SIMPLE_QUERIES`: Simple test queries
- `COMPLEX_QUERIES`: Complex queries
- `SPECIFIC_QUERIES`: Specific lookups
- `ALL`: All test queries

**MockRepositories**
- `SAMPLE_PYTHON_FILES`: Sample code files
- `get_sample_files()`: Factory method

**ExperimentScenarios**
- Predefined experiment scenarios
- Expected results per scenario

## Usage Patterns

### Testing Context Management

```python
def test_custom_context_workflow():
    from backend.tests.phase2l.conftest import context_manager, sample_evidence
    
    # Use pytest fixture
    cm = context_manager
    ev = sample_evidence
    
    # Add item
    item = cm.add_item(ev)
    assert item.context_item_id is not None
    
    # Check statistics
    stats = cm.get_context_statistics()
    assert stats["active_items"] == 1
```

### Running Experiments (for Agent 6)

```python
from pathlib import Path
from backend.tests.phase2l.experiment_runner import ExperimentRunner
from backend.tests.phase2l.experiment_framework import ExperimentConfig

runner = ExperimentRunner(output_base_dir=Path("/tmp/phase2l_results"))

config = ExperimentConfig(
    query="What is the main entry point?",
    workspace_path="/path/to/repo",
    experiment_type=ExperimentType.BULK_CONTEXT,
    output_dir=Path("/tmp/phase2l_results"),
)

report = runner.run_complete_experiment(config, retriever, llm_service)

# Access results
print(f"Bulk context tokens: {report.bulk_result.initial_context_tokens}")
print(f"Interactive final tokens: {report.interactive_result.final_context_tokens}")
print(f"Context reduction: {report.interactive_result.context_size_reduction}%")
```

### Creating Custom Test Data

```python
from backend.tests.phase2l.fixtures import SampleEvidenceFactory, create_test_evidence_set

# Create specific evidence
evidence = SampleEvidenceFactory.rim_symbol()

# Create batch
batch = SampleEvidenceFactory.batch_evidence(count=10)

# Get complete test set
evidence_set = create_test_evidence_set()
protected_items = evidence_set["protected"]
active_items = evidence_set["active"]
```

## Key Testing Principles

1. **Deterministic**: Tests are reproducible and order-independent
2. **Isolated**: No shared state between tests
3. **Fast**: Tests complete in <1 second total
4. **Clear**: Test names describe what they verify
5. **Comprehensive**: Cover normal, edge, and error cases

## Budget Checkpoint Thresholds

Tests verify budget status at these thresholds:

| Utilization | Status | Implication |
|--|--|--|
| < 50% | normal | Plenty of room |
| 50-70% | moderate | Comfortable, monitor growth |
| 70-85% | caution | Approaching limit |
| 85-95% | high | Need to compress/drop |
| > 95% | critical | Reject expensive additions |

## Priority Levels

Tests verify priority assignment:

| Priority | Characteristics | Can Drop | Can Compress |
|--|--|--|--|
| PROTECTED | User requirements, critical RIM facts | No | No |
| ACTIVE | Retrieved matches, high confidence | No | No |
| COMPRESSIBLE | Secondary evidence, medium relevance | Yes | Yes |
| DISPOSABLE | Low-relevance expansion | Yes | Yes |

## Next Steps: Agent 6 (Workspace Experiment)

Agent 6 will use this framework to:

1. Configure experiments for specific queries
2. Run Experiment A (bulk context approach)
3. Run Experiment B (interactive tools approach)
4. Compare metrics:
   - Context size reduction
   - Tool call efficiency
   - Answer correctness
   - Grounding quality

The framework is ready. Agent 6 just needs to:
- Provide actual retriever and LLM services
- Define evaluation criteria for answer quality
- Run experiments on real queries
- Analyze and report results

## Extending Tests

To add new tests:

1. Create test function in appropriate file
2. Use fixtures from `conftest.py`
3. Use factories from `fixtures.py`
4. Follow existing naming: `test_<what>_<expected_outcome>`
5. Run `uv run pytest backend/tests/phase2l/` to verify

## Debugging Tests

```bash
# Show print output
uv run pytest backend/tests/phase2l/ -s

# Drop into debugger on failure
uv run pytest backend/tests/phase2l/ --pdb

# Show fixture details
uv run pytest backend/tests/phase2l/ --fixtures

# Verbose with long strings
uv run pytest backend/tests/phase2l/ -vv --tb=long
```

## Performance

All 95 tests complete in ~0.5 seconds.

Test breakdown:
- Context lifecycle: 34 tests
- Inspection tools: 31 tests
- Token accounting: 30 tests

Total coverage: Critical Phase 2L components are fully tested.
