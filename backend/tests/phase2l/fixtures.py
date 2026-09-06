"""
Test fixtures and utilities for Phase 2L tests.

Provides:
- Sample evidence data
- Mock repositories
- Test queries
- Helper functions
"""

from typing import List, Dict, Any
from backend.agent.context.contracts import ContextEvidence


class SampleEvidenceFactory:
    """Factory for creating sample evidence items."""

    @staticmethod
    def retrieval_match() -> ContextEvidence:
        """Create sample retrieval match evidence."""
        return ContextEvidence(
            source_type="retrieval",
            source_id="retrieval_001",
            relevance=0.82,
            confidence=0.88,
            summary="Retrieved function definition",
            data={
                "file": "src/analyzer.py",
                "symbol": "analyze_code",
                "lines": [10, 25],
                "snippet": "def analyze_code(path: str) -> Dict[str, Any]: ..."
            },
            metadata={
                "retrieval_rank": 1,
                "search_query": "code analysis",
            }
        )

    @staticmethod
    def rim_symbol() -> ContextEvidence:
        """Create sample RIM symbol evidence."""
        return ContextEvidence(
            source_type="rim_symbol",
            source_id="rim_sym_001",
            relevance=0.95,
            confidence=0.96,
            summary="Core repository symbol from RIM",
            data={
                "symbol": "main.py::execute_analysis",
                "qualified_name": "execute_analysis",
                "type": "function",
                "language": "python",
                "imports": ["logging", "pathlib"],
            },
            metadata={
                "rim_score": 0.95,
                "critical_for_query": True,
            }
        )

    @staticmethod
    def rim_route() -> ContextEvidence:
        """Create sample RIM route evidence."""
        return ContextEvidence(
            source_type="rim_route",
            source_id="rim_route_001",
            relevance=0.90,
            confidence=0.92,
            summary="Control flow route through repository",
            data={
                "route": ["main.py::main", "analyzer.py::analyze", "parser.py::parse"],
                "edge_weights": [0.9, 0.85, 0.88],
            },
            metadata={
                "route_length": 3,
                "average_edge_weight": 0.87,
            }
        )

    @staticmethod
    def user_requirement() -> ContextEvidence:
        """Create sample user requirement evidence."""
        return ContextEvidence(
            source_type="requirement_analysis",
            source_id="req_001",
            relevance=1.0,
            confidence=1.0,
            summary="User requirement extracted from query",
            data={
                "requirement": "Analyze Python repository structure",
                "specific_needs": ["symbol extraction", "call graph", "dependency analysis"],
            },
            metadata={
                "from_user_query": True,
                "priority": "critical",
            }
        )

    @staticmethod
    def expansion_evidence() -> ContextEvidence:
        """Create sample expansion evidence (lower priority)."""
        return ContextEvidence(
            source_type="retrieval",
            source_id="expansion_001",
            relevance=0.35,
            confidence=0.52,
            summary="Peripheral context from expansion",
            data={
                "content": "Tangentially related information",
                "relevance_reason": "mentioned in related symbol",
            },
            metadata={
                "expansion_depth": 2,
                "might_be_useful": False,
            }
        )

    @staticmethod
    def batch_evidence(count: int = 5) -> List[ContextEvidence]:
        """Create batch of varied evidence items."""
        items = [
            SampleEvidenceFactory.user_requirement(),
            SampleEvidenceFactory.rim_symbol(),
            SampleEvidenceFactory.rim_route(),
        ]

        # Add retrieval matches
        for i in range(count - 3):
            items.append(ContextEvidence(
                source_type="retrieval",
                source_id=f"retrieval_{i:03d}",
                relevance=0.6 + (i * 0.05),
                confidence=0.65 + (i * 0.03),
                summary=f"Retrieval match {i}",
                data={"index": i, "content": f"Match {i}"},
                metadata={"rank": i},
            ))

        return items


class TestQueries:
    """Sample queries for testing."""

    SIMPLE_QUERIES = [
        "What is the main entry point?",
        "List all classes in the repository",
        "Find functions that parse files",
    ]

    COMPLEX_QUERIES = [
        "How does the data flow from input to output?",
        "Which modules are most critical for the analysis pipeline?",
        "What are the dependencies between these components?",
    ]

    SPECIFIC_QUERIES = [
        "Find the implementation of analyze_repository",
        "Show all call sites of the parse function",
        "List imports in main.py",
    ]

    ALL = SIMPLE_QUERIES + COMPLEX_QUERIES + SPECIFIC_QUERIES


class MockRepositories:
    """Mock repository structures for testing."""

    SAMPLE_PYTHON_FILES = {
        "main.py": '''"""Main entry point."""
import sys
from analyzer import Analyzer

def main():
    """Run analysis."""
    analyzer = Analyzer()
    return analyzer.run()

if __name__ == "__main__":
    sys.exit(main())
''',
        "analyzer.py": '''"""Code analyzer."""
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class Analyzer:
    """Analyzes code repositories."""

    def __init__(self):
        """Initialize analyzer."""
        self.results = []

    def run(self) -> Dict[str, any]:
        """Run analysis."""
        logger.info("Starting analysis")
        return {"status": "complete"}

    def analyze_file(self, path: str) -> Dict:
        """Analyze single file."""
        return {"file": path, "symbols": []}
''',
        "parser.py": '''"""Parser for source code."""
import ast
from pathlib import Path

class Parser:
    """Parses Python source code."""

    @staticmethod
    def parse(source: str) -> ast.AST:
        """Parse source code."""
        return ast.parse(source)

    @staticmethod
    def extract_symbols(tree: ast.AST) -> List[str]:
        """Extract symbols from AST."""
        return []
''',
    }

    @staticmethod
    def get_sample_files() -> Dict[str, str]:
        """Get sample Python files."""
        return MockRepositories.SAMPLE_PYTHON_FILES.copy()


class ExperimentScenarios:
    """Pre-defined experiment scenarios for testing."""

    SCENARIO_SIMPLE = {
        "query": "What is the main entry point?",
        "expected_files": ["main.py"],
        "expected_symbols": ["main"],
    }

    SCENARIO_DEPENDENCY = {
        "query": "How do main.py and analyzer.py interact?",
        "expected_files": ["main.py", "analyzer.py"],
        "expected_symbols": ["main", "Analyzer"],
    }

    SCENARIO_COMPLETE = {
        "query": "Explain the complete analysis pipeline",
        "expected_files": ["main.py", "analyzer.py", "parser.py"],
        "expected_symbols": ["main", "Analyzer", "Parser"],
    }


def create_test_evidence_set() -> Dict[str, List[ContextEvidence]]:
    """Create a comprehensive set of test evidence for integration tests."""
    return {
        "protected": [
            SampleEvidenceFactory.user_requirement(),
            SampleEvidenceFactory.rim_symbol(),
            SampleEvidenceFactory.rim_route(),
        ],
        "active": [
            SampleEvidenceFactory.retrieval_match(),
        ],
        "compressible": [
            ContextEvidence(
                source_type="retrieval",
                source_id="comp_001",
                relevance=0.65,
                confidence=0.70,
                summary="Secondary evidence",
                data={"detail": "Supporting information"},
                metadata={},
            ),
        ],
        "disposable": [
            SampleEvidenceFactory.expansion_evidence(),
        ],
    }


def assert_evidence_equals(
    actual: ContextEvidence,
    expected: ContextEvidence,
    ignore_timestamps: bool = True,
) -> None:
    """
    Assert two evidence items are equal.

    Args:
        actual: Actual evidence
        expected: Expected evidence
        ignore_timestamps: Whether to ignore timestamp fields
    """
    assert actual.source_type == expected.source_type
    assert actual.source_id == expected.source_id
    assert abs(actual.relevance - expected.relevance) < 0.01
    assert abs(actual.confidence - expected.confidence) < 0.01
    assert actual.summary == expected.summary
    assert actual.data == expected.data


def create_mock_retriever(results: List[ContextEvidence]):
    """
    Create a mock retriever that returns fixed results.

    Useful for deterministic testing.
    """
    class MockRetriever:
        def retrieve(self, query: str, limit: int = 10):
            return results[:limit]

    return MockRetriever()


def create_mock_llm_service(response: str = "Mock response"):
    """
    Create a mock LLM service.

    Useful for testing without actual LLM calls.
    """
    class MockLLMService:
        def query(self, prompt: str, context: str = "") -> str:
            return response

        def count_tokens(self, text: str) -> int:
            return len(text) // 4

    return MockLLMService()
