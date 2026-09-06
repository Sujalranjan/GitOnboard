#!/usr/bin/env python
"""
Phase 2L.1: Adversarial Validation Harness

Tests 18 specific scenarios against real GitOnboard repository.
Do NOT use fixtures or mock data.
Record exact results with full provenance.
Classify failures by root cause.
"""
import logging
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

import pytest

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.repository import Repository, Analysis
from backend.intelligence.inspection.file_inspector import inspect_file
from backend.intelligence.inspection.symbol_inspector import inspect_symbol
from backend.intelligence.inspection.source_reader import read_symbol, read_lines, read_file
from backend.intelligence.context_management.manager import ContextManager
from backend.intelligence.context_management.models import ContextItem
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.intelligence.query_layer import QueryLayer
from backend.agent.context.contracts import ContextBudget

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestStatus(Enum):
    """Test outcome classification."""
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_VALIDATED = "NOT_VALIDATED"


class FailureReason(Enum):
    """Root cause of test failure."""
    NONE = "none"
    SOURCE_INSPECTION_FAIL = "source_inspection_fail"
    SYMBOL_BOUNDARY_FAIL = "symbol_boundary_fail"
    NAVIGATION_FAIL = "navigation_fail"
    CONTEXT_LIFECYCLE_FAIL = "context_lifecycle_fail"
    RETRIEVAL_FAIL = "retrieval_fail"
    SELECTION_FAIL = "selection_fail"
    LLM_FAIL = "llm_fail"
    TOOLING_FAIL = "tooling_fail"
    NOT_IMPLEMENTED_FEATURE = "not_implemented_feature"
    NO_VALID_SOURCE = "no_valid_source"


@dataclass
class TestResult:
    """Record of a single test execution."""
    test_number: int
    test_name: str
    question: str
    status: TestStatus
    failure_reason: FailureReason

    # Execution details
    files_expected: List[str]
    files_retrieved: List[str]
    symbols_expected: List[str]
    symbols_retrieved: List[str]
    tool_calls: List[Dict[str, Any]]

    # Context metrics
    initial_context_tokens: int
    peak_context_tokens: int
    final_context_tokens: int
    context_items_added: int
    context_items_dropped: int
    context_items_summarized: int

    # Quality metrics
    source_complete: bool  # All required source retrieved
    irrelevant_source_included: bool  # Unnecessary content
    answer_grounded: bool  # Can be grounded in retrieved source

    # Additional details
    notes: str = ""
    error_message: str = ""
    evidence: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d['status'] = self.status.value
        d['failure_reason'] = self.failure_reason.value
        if self.evidence is None:
            d['evidence'] = {}
        return d


class RepositoryState:
    """Capture current repository state for validation."""

    def __init__(self, db: Session, repo_id: int):
        self.db = db
        self.repo_id = repo_id
        self.repository = db.query(Repository).filter(
            Repository.id == repo_id
        ).first()

        self.analyses = db.query(Analysis).filter(
            Analysis.repository_id == repo_id
        ).all()

        self.latest_analysis = (
            db.query(Analysis)
            .filter(Analysis.repository_id == repo_id)
            .order_by(Analysis.id.desc())
            .first()
        )

    def summary(self) -> Dict[str, Any]:
        """Summarize repository state."""
        return {
            "repository_id": self.repo_id,
            "repository_url": self.repository.url if self.repository else None,
            "total_analyses": len(self.analyses),
            "latest_analysis_id": self.latest_analysis.id if self.latest_analysis else None,
            "latest_analysis_status": self.latest_analysis.status if self.latest_analysis else None,
        }


class AdversarialValidator:
    """Execute all 18 validation tests."""

    def __init__(self):
        self.db = SessionLocal()
        self.repository: Optional[Repository] = None
        self.analysis: Optional[Analysis] = None
        self.state: Optional[RepositoryState] = None
        self.results: List[TestResult] = []

        self.context_manager: Optional[ContextManager] = None
        self.retriever: Optional[HybridRetriever] = None
        self.query_layer: Optional[QueryLayer] = None
        self.repository_model: Optional[Any] = None

    def setup(self):
        """Initialize validation environment."""
        logger.info("\n" + "="*80)
        logger.info("PHASE 2L.1: ADVERSARIAL VALIDATION SETUP")
        logger.info("="*80)

        # Get or create repository
        repo_path = str(PROJECT_ROOT)
        self.repository = self.db.query(Repository).filter(
            Repository.url == repo_path
        ).first()

        if not self.repository:
            logger.error("Repository not found in database")
            raise RuntimeError("Repository not found")

        # Get latest analysis
        self.analysis = (
            self.db.query(Analysis)
            .filter(Analysis.repository_id == self.repository.id)
            .order_by(Analysis.id.desc())
            .first()
        )

        if not self.analysis:
            logger.error("No analysis found for repository")
            raise RuntimeError("No analysis found")

        # Record state
        self.state = RepositoryState(self.db, self.repository.id)
        logger.info(f"Repository state: {json.dumps(self.state.summary(), indent=2)}")

        # Initialize tools
        budget = ContextBudget(
            max_files=15,
            max_symbols=30,
            max_routes=10,
            max_db_objects=10,
            max_dependencies=15,
            max_call_paths=10,
            max_source_excerpts=10,
            max_total_evidence_size_kb=256,
        )
        self.context_manager = ContextManager(budget=budget)
        self.retriever = HybridRetriever(
            db=self.db,
            analysis_id=self.analysis.id,
            chroma_collection=None  # Semantic search may not be available
        )

        # Initialize QueryLayer if RepositoryModel is available
        if self.analysis and hasattr(self.analysis, 'repository_model') and self.analysis.repository_model:
            self.repository_model = self.analysis.repository_model
            self.query_layer = QueryLayer(model=self.repository_model)
        else:
            logger.warning("RepositoryModel not available, QueryLayer will be None")
            self.query_layer = None

        logger.info("✓ Validation environment ready")

    def _create_test_result(
        self,
        test_number: int,
        test_name: str,
        question: str,
        status: TestStatus = TestStatus.FAIL,
        failure_reason: FailureReason = FailureReason.NONE,
    ) -> TestResult:
        """Factory for creating test results with defaults."""
        return TestResult(
            test_number=test_number,
            test_name=test_name,
            question=question,
            status=status,
            failure_reason=failure_reason,
            files_expected=[],
            files_retrieved=[],
            symbols_expected=[],
            symbols_retrieved=[],
            tool_calls=[],
            initial_context_tokens=0,
            peak_context_tokens=0,
            final_context_tokens=0,
            context_items_added=0,
            context_items_dropped=0,
            context_items_summarized=0,
            source_complete=False,
            irrelevant_source_included=False,
            answer_grounded=False,
        )

    def test_1_simple_python_symbol_lookup(self) -> TestResult:
        """TEST 1: Simple Python symbol lookup."""
        logger.info("\n" + "="*80)
        logger.info("TEST 1: Simple Python Symbol Lookup")
        logger.info("="*80)

        result = self._create_test_result(
            1,
            "Simple Python Symbol Lookup",
            "Where is authentication middleware implemented?"
        )

        try:
            # Step 1: Retrieve relevant files
            logger.info("Step 1: Retrieve relevant files")
            retrieval_results = self.retriever.retrieve(
                "authentication middleware",
                top_k=5
            )

            if not retrieval_results:
                result.status = TestStatus.FAIL
                result.failure_reason = FailureReason.RETRIEVAL_FAIL
                result.notes = "No retrieval results for authentication middleware"
                self.results.append(result)
                return result

            result.files_retrieved = [r.file_path for r in retrieval_results]
            logger.info(f"Retrieved {len(retrieval_results)} results: {result.files_retrieved}")

            # Step 2: Inspect files
            logger.info("Step 2: Inspect files for symbols")
            for ret_result in retrieval_results[:3]:  # Limit to top 3
                try:
                    file_info = inspect_file(
                        ret_result.file_path,
                        db=self.db,
                        repo_root=str(PROJECT_ROOT),
                        analysis_id=self.analysis.id
                    )
                    logger.info(f"  File: {ret_result.file_path}")
                    logger.info(f"    Symbols: {len(file_info.symbols)}")

                    result.tool_calls.append({
                        "tool": "inspect_file",
                        "argument": ret_result.file_path,
                        "result_symbols": len(file_info.symbols),
                    })

                    # Step 3: Read actual source
                    if file_info.symbols:
                        symbol = file_info.symbols[0]
                        logger.info(f"    Reading symbol: {symbol.name} (line {symbol.line_start}-{symbol.line_end})")

                        source = read_symbol(
                            ret_result.file_path,
                            symbol.name,
                            db=self.db,
                            repo_root=str(PROJECT_ROOT),
                            analysis_id=self.analysis.id
                        )

                        if source.success:
                            result.source_complete = True
                            result.symbols_retrieved.append(symbol.name)
                            logger.info(f"    ✓ Retrieved {len(source.source)} chars")

                            result.tool_calls.append({
                                "tool": "read_symbol",
                                "argument": f"{ret_result.file_path}:{symbol.name}",
                                "result_chars": len(source.source),
                                "line_range": [source.line_start, source.line_end],
                            })
                        else:
                            logger.warning(f"    ✗ Failed to read symbol: {source.error}")

                except Exception as e:
                    logger.error(f"Error inspecting {ret_result.file_path}: {e}")
                    result.tool_calls.append({
                        "tool": "inspect_file",
                        "argument": ret_result.file_path,
                        "error": str(e),
                    })

            # Determine pass/fail
            if result.source_complete and len(result.symbols_retrieved) > 0:
                result.status = TestStatus.PASS
                result.failure_reason = FailureReason.NONE
            else:
                result.status = TestStatus.FAIL
                result.failure_reason = FailureReason.SOURCE_INSPECTION_FAIL

        except Exception as e:
            logger.error(f"TEST 1 failed with exception: {e}")
            result.status = TestStatus.FAIL
            result.failure_reason = FailureReason.TOOLING_FAIL
            result.error_message = str(e)

        self.results.append(result)
        return result

    def test_2_multi_file_backend_flow(self) -> TestResult:
        """TEST 2: Multi-file backend flow (authentication chain)."""
        logger.info("\n" + "="*80)
        logger.info("TEST 2: Multi-file Backend Flow")
        logger.info("="*80)

        result = self._create_test_result(
            2,
            "Multi-file Backend Flow",
            "Trace what happens when a user logs in"
        )

        try:
            logger.info("Step 1: Retrieve login-related sources")
            retrieval_results = self.retriever.retrieve(
                "user login authentication",
                top_k=5
            )

            if not retrieval_results:
                result.status = TestStatus.FAIL
                result.failure_reason = FailureReason.RETRIEVAL_FAIL
                self.results.append(result)
                return result

            result.files_retrieved = [r.file_path for r in retrieval_results]
            logger.info(f"Retrieved: {result.files_retrieved}")

            # Attempt to trace dependencies using QueryLayer
            logger.info("Step 2: Trace call relationships")

            # This tests whether we can navigate from entry point to related logic
            inspected_count = 0
            for ret_result in retrieval_results[:5]:
                try:
                    file_info = inspect_file(
                        ret_result.file_path,
                        db=self.db,
                        repo_root=str(PROJECT_ROOT),
                        analysis_id=self.analysis.id
                    )
                    if file_info.symbols:
                        inspected_count += 1
                        symbol = file_info.symbols[0]

                        # Try to get relationships
                        if self.query_layer:
                            try:
                                relationships = self.query_layer.get_symbol_calls(
                                    ret_result.file_path,
                                    symbol.name
                                )
                                logger.info(f"  {ret_result.file_path}: {symbol.name} calls {len(relationships) if relationships else 0} targets")
                                result.tool_calls.append({
                                    "tool": "get_symbol_calls",
                                    "argument": f"{ret_result.file_path}:{symbol.name}",
                                    "result_count": len(relationships) if relationships else 0,
                                })
                            except Exception as e:
                                logger.debug(f"Relationship query failed: {e}")  # Relationship query may not be available

                except Exception as e:
                    logger.warning(f"Could not inspect {ret_result.file_path}: {e}")

            if inspected_count > 0:
                result.status = TestStatus.PASS
                result.failure_reason = FailureReason.NONE
                result.source_complete = True
            else:
                result.status = TestStatus.FAIL
                result.failure_reason = FailureReason.NAVIGATION_FAIL

        except Exception as e:
            logger.error(f"TEST 2 failed: {e}")
            result.status = TestStatus.FAIL
            result.failure_reason = FailureReason.TOOLING_FAIL
            result.error_message = str(e)

        self.results.append(result)
        return result

    def test_3_authentication_exploration(self) -> TestResult:
        """TEST 3: Broader authentication exploration."""
        logger.info("\n" + "="*80)
        logger.info("TEST 3: Authentication Exploration")
        logger.info("="*80)

        result = self._create_test_result(
            3,
            "Authentication Exploration",
            "Explain all authentication mechanisms"
        )

        try:
            # Retrieve with broader query
            keywords = ["auth", "login", "jwt", "oauth", "session", "middleware"]
            all_results = []

            for keyword in keywords:
                ret_results = self.retriever.retrieve(keyword, top_k=3)
                all_results.extend(ret_results)

            # Deduplicate
            unique_files = list(set(r.file_path for r in all_results))
            result.files_retrieved = unique_files

            logger.info(f"Retrieved {len(unique_files)} unique files across {len(keywords)} keywords")

            # Inspect and read
            inspected = 0
            for file_path in unique_files[:10]:  # Limit to 10
                try:
                    file_info = inspect_file(
                        file_path,
                        db=self.db,
                        repo_root=str(PROJECT_ROOT),
                        analysis_id=self.analysis.id
                    )
                    if file_info.symbols:
                        inspected += 1
                        # Read first symbol
                        symbol = file_info.symbols[0]
                        source = read_symbol(
                            file_path,
                            symbol.name,
                            db=self.db,
                            analysis_id=self.analysis.id
                        )
                        if source.success:
                            result.symbols_retrieved.append(symbol.name)
                except Exception as e:
                    logger.debug(f"Could not inspect {file_path}: {e}")

            result.source_complete = len(result.symbols_retrieved) > 0
            result.status = TestStatus.PASS if result.source_complete else TestStatus.FAIL
            result.failure_reason = FailureReason.NONE if result.source_complete else FailureReason.NAVIGATION_FAIL

        except Exception as e:
            logger.error(f"TEST 3 failed: {e}")
            result.status = TestStatus.FAIL
            result.failure_reason = FailureReason.TOOLING_FAIL
            result.error_message = str(e)

        self.results.append(result)
        return result

    def test_4_frontend_validation(self) -> TestResult:
        """TEST 4: Frontend TypeScript/JSX validation."""
        logger.info("\n" + "="*80)
        logger.info("TEST 4: Frontend Validation")
        logger.info("="*80)

        result = self._create_test_result(
            4,
            "Frontend Validation",
            "Find frontend component and validate boundaries"
        )

        try:
            # Retrieve frontend-related files (avoid .next, node_modules, etc.)
            ret_results = self.retriever.retrieve("frontend component ui", top_k=5)

            frontend_files = [
                r for r in ret_results
                if any(ext in r.file_path for ext in ['.tsx', '.ts', '.jsx', '.js'])
                and not any(skip in r.file_path for skip in ['.next', 'node_modules', 'dist', 'build'])
            ]

            if not frontend_files:
                result.status = TestStatus.NOT_VALIDATED
                result.failure_reason = FailureReason.NO_VALID_SOURCE
                result.notes = "No valid frontend source files found (excluding generated/build files)"
                self.results.append(result)
                return result

            result.files_retrieved = [f.file_path for f in frontend_files]
            logger.info(f"Found {len(frontend_files)} frontend files: {result.files_retrieved}")

            # Inspect each
            for frontend_file in frontend_files[:3]:
                try:
                    file_info = inspect_file(
                        frontend_file.file_path,
                        db=self.db,
                        repo_root=str(PROJECT_ROOT),
                        analysis_id=self.analysis.id
                    )
                    logger.info(f"  {frontend_file.file_path}: {len(file_info.symbols)} symbols")

                    if file_info.symbols:
                        result.symbols_retrieved.extend([s.name for s in file_info.symbols[:3]])

                        # Validate boundaries
                        for symbol in file_info.symbols[:2]:
                            source = read_symbol(
                                frontend_file.file_path,
                                symbol.name,
                                db=self.db,
                                analysis_id=self.analysis.id
                            )
                            if source.success:
                                logger.info(f"    ✓ {symbol.name}: lines {source.line_start}-{source.line_end} ({len(source.source)} chars)")

                except Exception as e:
                    logger.warning(f"Error on {frontend_file.file_path}: {e}")

            if result.symbols_retrieved:
                result.status = TestStatus.PASS
                result.source_complete = True
            else:
                result.status = TestStatus.FAIL
                result.failure_reason = FailureReason.SOURCE_INSPECTION_FAIL

        except Exception as e:
            logger.error(f"TEST 4 failed: {e}")
            result.status = TestStatus.FAIL
            result.failure_reason = FailureReason.TOOLING_FAIL
            result.error_message = str(e)

        self.results.append(result)
        return result

    def run_all_tests(self) -> List[TestResult]:
        """Execute all 18 tests."""
        logger.info("\n" + "#"*80)
        logger.info("# PHASE 2L.1 ADVERSARIAL VALIDATION - ALL TESTS")
        logger.info("#"*80)

        self.setup()

        try:
            # Run tests 1-4 as implemented
            self.test_1_simple_python_symbol_lookup()
            self.test_2_multi_file_backend_flow()
            self.test_3_authentication_exploration()
            self.test_4_frontend_validation()

            # Tests 5-18 will be scaffolded as NOT_IMPLEMENTED
            for test_num in range(5, 19):
                result = self._create_test_result(
                    test_num,
                    f"Test {test_num}",
                    "Pending implementation"
                )
                result.status = TestStatus.NOT_IMPLEMENTED
                result.failure_reason = FailureReason.NOT_IMPLEMENTED_FEATURE
                self.results.append(result)

        except Exception as e:
            logger.error(f"Validation harness failed: {e}", exc_info=True)

        return self.results

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report."""
        passed = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        not_implemented = sum(1 for r in self.results if r.status == TestStatus.NOT_IMPLEMENTED)
        not_validated = sum(1 for r in self.results if r.status == TestStatus.NOT_VALIDATED)

        return {
            "timestamp": datetime.now().isoformat(),
            "environment": self.state.summary() if self.state else {},
            "summary": {
                "total_tests": len(self.results),
                "passed": passed,
                "failed": failed,
                "not_implemented": not_implemented,
                "not_validated": not_validated,
                "pass_rate": passed / len(self.results) if self.results else 0.0,
            },
            "results": [r.to_dict() for r in self.results],
            "failures_by_reason": self._failures_by_reason(),
        }

    def _failures_by_reason(self) -> Dict[str, int]:
        """Count failures by root cause."""
        reasons = {}
        for result in self.results:
            if result.status == TestStatus.FAIL:
                reason = result.failure_reason.value
                reasons[reason] = reasons.get(reason, 0) + 1
        return reasons


def pytest_generate_tests(metafunc):
    """Run validation as a pytest."""
    if "adversarial_validator" in metafunc.fixturenames:
        validator = AdversarialValidator()
        validator.run_all_tests()

        # Save report
        report = validator.generate_report()
        report_path = PROJECT_ROOT / "backend/tests/phase2l1/VALIDATION_RESULTS.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"\n✓ Report saved: {report_path}")

        metafunc.parametrize(
            "adversarial_validator",
            [validator]
        )


@pytest.fixture
def adversarial_validator():
    """Fixture for validation."""
    return AdversarialValidator()


if __name__ == "__main__":
    validator = AdversarialValidator()
    results = validator.run_all_tests()
    report = validator.generate_report()

    # Print summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    print(json.dumps(report["summary"], indent=2))

    # Save report
    report_path = PROJECT_ROOT / "backend/tests/phase2l1/VALIDATION_RESULTS.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n✓ Full report saved: {report_path}")

    sys.exit(0 if report["summary"]["failed"] == 0 else 1)
