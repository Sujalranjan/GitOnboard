"""
Pytest configuration for Phase 2L tests.
Provides common fixtures for inspection tools, context management, and experiments.
"""

import pytest
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from unittest.mock import MagicMock

from backend.agent.context.contracts import ContextEvidence, ContextBudget
from backend.intelligence.context_management.manager import ContextManager
from backend.intelligence.context_management.models import (
    ContextItemPriority,
    ContextItemState,
)


@pytest.fixture
def mock_context_budget() -> ContextBudget:
    """Create a mock ContextBudget for testing."""
    budget = MagicMock(spec=ContextBudget)
    budget.total_allocated = 100000
    budget.total_used = 0
    budget.items = []
    return budget


@pytest.fixture
def context_manager(mock_context_budget) -> ContextManager:
    """Create a ContextManager with default 100K token budget."""
    return ContextManager(
        budget=mock_context_budget,
        configured_context_budget_tokens=100000,
    )


@pytest.fixture
def sample_evidence() -> ContextEvidence:
    """Create sample ContextEvidence for testing."""
    return ContextEvidence(
        source_type="retrieval",
        source_id="test_source_1",
        relevance=0.85,
        confidence=0.9,
        summary="Test evidence summary",
        data={"content": "This is test evidence data", "lines": [1, 10]},
        metadata={"file": "test.py", "type": "symbol"},
    )


@pytest.fixture
def high_priority_evidence() -> ContextEvidence:
    """Create high-priority evidence (user requirement)."""
    return ContextEvidence(
        source_type="requirement_analysis",
        source_id="req_001",
        relevance=0.95,
        confidence=0.95,
        summary="User requirement",
        data={"requirement": "System must support Python analysis"},
        metadata={"priority": "critical"},
    )


@pytest.fixture
def low_priority_evidence() -> ContextEvidence:
    """Create low-priority evidence for testing compression/dropping."""
    return ContextEvidence(
        source_type="retrieval",
        source_id="expansion_001",
        relevance=0.45,
        confidence=0.6,
        summary="Peripheral context",
        data={"expansion": "Tangentially related information"},
        metadata={"priority": "low"},
    )


@pytest.fixture
def rim_symbol_evidence() -> ContextEvidence:
    """Create RIM symbol evidence (critical fact)."""
    return ContextEvidence(
        source_type="rim_symbol",
        source_id="rim_sym_001",
        relevance=0.9,
        confidence=0.95,
        summary="Core repository symbol",
        data={"symbol": "main.py::analyze_repository", "qualname": "analyze_repository"},
        metadata={"type": "critical_rim"},
    )


@pytest.fixture
def temp_test_file(tmp_path) -> Path:
    """Create a temporary test file with sample Python code."""
    test_file = tmp_path / "test_sample.py"
    content = '''"""Sample module for testing."""

def simple_function(x: int) -> int:
    """Simple function that doubles input."""
    return x * 2

class SimpleClass:
    """A simple test class."""

    def __init__(self, value: int):
        """Initialize with value."""
        self.value = value

    def get_value(self) -> int:
        """Return the value."""
        return self.value

async def async_function(data: str) -> str:
    """Async function for testing."""
    return f"processed: {data}"
'''
    test_file.write_text(content)
    return test_file


@pytest.fixture
def mock_db_session() -> Session:
    """Create a mock database session."""
    return MagicMock(spec=Session)
