#!/usr/bin/env python3
"""
SUBAGENT C: RIM Product Value Evaluation

Systematically evaluates whether RIM provides meaningful product value
beyond basic retrieval across 7 representative use cases.

Core Question: Does RIM actually improve repository understanding, or just add complexity?
"""

import json
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Setup path
import sys
sys.path.insert(0, '/home/dheeraj/repository_intelligence_platform')

from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.repository import Analysis, Repository
from backend.intelligence.retrieval.retriever import HybridRetriever
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

class RetrieverMode(Enum):
    """Comparison modes."""
    BASELINE = "baseline"  # BM25 + Semantic + Exact, no graph expansion
    RIM = "rim"            # BM25 + Semantic + Exact + graph expansion


@dataclass
class UseCase:
    """Represents a use case category."""
    id: str
    name: str
    description: str
    queries: List[str]


@dataclass
class QueryResult:
    """Result from a single query retrieval."""
    mode: RetrieverMode
    query: str
    files_found: List[str]
    symbols_found: List[str]
    relationships_found: int
    total_entities: int
    context_size_tokens_approx: int
    latency_ms: float
    expansion_nodes_added: int  # Only for RIM


@dataclass
class QueryComparison:
    """Comparison between baseline and RIM for one query."""
    query: str
    baseline: QueryResult
    rim: QueryResult

    # Analysis
    baseline_sufficient: bool  # Could baseline already answer this?
    rim_adds_value: bool       # Does RIM provide additional useful context?
    rim_essential: bool        # Was RIM necessary to find the answer?

    # Efficiency impact
    latency_increase_pct: float
    context_increase_pct: float

    # Quality judgment: poor, fair, good, excellent
    baseline_quality: str
    rim_quality: str
    quality_improved: bool


# ============================================================================
# USE CASE DEFINITIONS
# ============================================================================

USE_CASES = [
    UseCase(
        id="feature_understanding",
        name="Feature Understanding",
        description="User asks 'How does X work?' - Should identify all symbols involved in the feature",
        queries=[
            "How does authentication work?",
            "How does the repository analysis pipeline work?",
            "How does the symbol extraction system work?",
        ]
    ),
    UseCase(
        id="symbol_navigation",
        name="Symbol Navigation",
        description="User asks 'Who calls X?' - Should find all callers/callees",
        queries=[
            "Who calls the retrieve function?",
            "What does the symbol expander call?",
            "Who uses the graph traverser?",
        ]
    ),
    UseCase(
        id="dependency_navigation",
        name="Dependency Navigation",
        description="User asks 'What does X depend on?' - Should trace imports/uses",
        queries=[
            "What imports does the retriever use?",
            "What database models are used by the service?",
            "What external dependencies does the analysis module have?",
        ]
    ),
    UseCase(
        id="call_chain_navigation",
        name="Call-Chain Navigation",
        description="User asks about data flow - Should follow the chain",
        queries=[
            "What's the flow from user input to database query?",
            "How does data flow through the retrieval pipeline?",
            "What are all the steps in the analysis pipeline?",
        ]
    ),
    UseCase(
        id="action_location",
        name="Action Location",
        description="User asks 'Where do I modify X?' - Should find the right file/symbol",
        queries=[
            "Where should I add a new relationship type?",
            "Where is the lexical search ranking implemented?",
            "Where is the graph expansion depth limit defined?",
        ]
    ),
    UseCase(
        id="file_navigation",
        name="File Navigation",
        description="User asks 'Which files handle X?' - Should identify them",
        queries=[
            "Which files handle retrieval?",
            "Which files define the schema?",
            "Which files implement the expansion logic?",
        ]
    ),
    UseCase(
        id="negative_queries",
        name="Negative Queries (Absence)",
        description="User asks about absent features - Should not fabricate",
        queries=[
            "Does the system have a caching layer?",
            "Is there machine learning in the retrieval?",
            "Does the system use GraphQL?",
        ]
    ),
]


# ============================================================================
# EVALUATION ENGINE
# ============================================================================

class RIMProductEvaluator:
    """Evaluates RIM product value."""

    def __init__(self, analysis_id: int, db: Session):
        self.analysis_id = analysis_id
        self.db = db
        self.baseline_retriever = HybridRetriever(
            db=db,
            analysis_id=analysis_id,
            enable_graph_expansion=False,  # Baseline: no graph expansion
        )
        self.rim_retriever = HybridRetriever(
            db=db,
            analysis_id=analysis_id,
            enable_graph_expansion=True,   # RIM: with graph expansion
            graph_expansion_depth=2,
            graph_expansion_nodes_per_hop=3,
            graph_expansion_max_total=30,
        )

    def evaluate_query(self, query: str) -> Tuple[QueryResult, QueryResult]:
        """Execute query in both baseline and RIM modes."""

        # Baseline retrieval
        logger.info(f"[BASELINE] Retrieving: {query}")
        baseline_start = time.perf_counter()
        baseline_results = self.baseline_retriever.retrieve(
            query=query,
            top_k=15,
            expand_with_fact_store=False,
            enable_graph_expansion=False,
        )
        baseline_latency = (time.perf_counter() - baseline_start) * 1000

        baseline_result = self._process_results(
            results=baseline_results,
            mode=RetrieverMode.BASELINE,
            query=query,
            latency_ms=baseline_latency,
        )

        # RIM retrieval
        logger.info(f"[RIM] Retrieving: {query}")
        rim_start = time.perf_counter()
        rim_results = self.rim_retriever.retrieve(
            query=query,
            top_k=15,
            expand_with_fact_store=False,
            enable_graph_expansion=True,
        )
        rim_latency = (time.perf_counter() - rim_start) * 1000

        rim_result = self._process_results(
            results=rim_results,
            mode=RetrieverMode.RIM,
            query=query,
            latency_ms=rim_latency,
            baseline_count=len(baseline_results),
        )

        return baseline_result, rim_result

    def _process_results(
        self,
        results: List[Any],
        mode: RetrieverMode,
        query: str,
        latency_ms: float,
        baseline_count: int = 0,
    ) -> QueryResult:
        """Convert retriever results to QueryResult."""
        files_found = []
        symbols_found = []
        relationships = 0

        for result in results:
            # Extract file path
            if hasattr(result, 'file_path') and result.file_path:
                if result.file_path not in files_found:
                    files_found.append(result.file_path)

            # Extract symbol info
            if hasattr(result, 'name'):
                if result.name not in symbols_found:
                    symbols_found.append(result.name)

            # Count relationships in metadata
            if hasattr(result, 'metadata') and result.metadata:
                if 'relationship_role' in result.metadata:
                    relationships += 1

        # Approximate context size
        avg_symbol_tokens = 50
        avg_file_tokens = 100
        relationships_tokens = relationships * 20
        total_tokens = (len(symbols_found) * avg_symbol_tokens +
                       len(files_found) * avg_file_tokens +
                       relationships_tokens)

        expansion_nodes = len(results) - baseline_count if mode == RetrieverMode.RIM else 0

        return QueryResult(
            mode=mode,
            query=query,
            files_found=files_found,
            symbols_found=symbols_found,
            relationships_found=relationships,
            total_entities=len(results),
            context_size_tokens_approx=total_tokens,
            latency_ms=latency_ms,
            expansion_nodes_added=expansion_nodes,
        )

    def compare_queries(self, queries: List[str]) -> List[QueryComparison]:
        """Compare baseline vs RIM for a set of queries."""
        comparisons = []

        for query in queries:
            baseline, rim = self.evaluate_query(query)

            # Compute metrics
            latency_increase = (
                ((rim.latency_ms - baseline.latency_ms) / baseline.latency_ms * 100)
                if baseline.latency_ms > 0 else 0
            )
            context_increase = (
                ((rim.context_size_tokens_approx - baseline.context_size_tokens_approx) /
                 baseline.context_size_tokens_approx * 100)
                if baseline.context_size_tokens_approx > 0 else 0
            )

            # Judge quality (simplistic heuristic)
            baseline_quality = self._judge_quality(baseline)
            rim_quality = self._judge_quality(rim)
            quality_improved = rim_quality > baseline_quality

            # Apply evaluation rules
            baseline_sufficient = len(baseline.symbols_found) > 3
            rim_adds_value = (
                len(rim.symbols_found) > len(baseline.symbols_found) and
                rim.relationships_found > baseline.relationships_found
            )
            rim_essential = (
                not baseline_sufficient and len(rim.symbols_found) >= len(baseline.symbols_found)
            )

            comparison = QueryComparison(
                query=query,
                baseline=baseline,
                rim=rim,
                baseline_sufficient=baseline_sufficient,
                rim_adds_value=rim_adds_value,
                rim_essential=rim_essential,
                latency_increase_pct=latency_increase,
                context_increase_pct=context_increase,
                baseline_quality=baseline_quality,
                rim_quality=rim_quality,
                quality_improved=quality_improved,
            )
            comparisons.append(comparison)

            logger.info(f"Query: {query}")
            logger.info(f"  Baseline: {len(baseline.symbols_found)} symbols, {baseline.latency_ms:.1f}ms")
            logger.info(f"  RIM: {len(rim.symbols_found)} symbols, {rim.latency_ms:.1f}ms (+{latency_increase:.1f}%)")
            logger.info(f"  RIM Adds Value: {rim_adds_value}, Essential: {rim_essential}")
            logger.info("")

        return comparisons

    def _judge_quality(self, result: QueryResult) -> str:
        """Judge result quality: poor, fair, good, excellent."""
        score = (len(result.symbols_found) * 1 +
                result.relationships_found * 2 +
                len(result.files_found) * 0.5)

        if score < 2:
            return "poor"
        elif score < 5:
            return "fair"
        elif score < 10:
            return "good"
        else:
            return "excellent"


# ============================================================================
# ANALYSIS HELPERS
# ============================================================================

def get_default_analysis(db: Session) -> Optional[Analysis]:
    """Get first available analysis for evaluation."""
    analysis = db.query(Analysis).first()
    if analysis:
        logger.info(f"Using analysis: {analysis.id} ({analysis.repository.name})")
    else:
        logger.warning("No analysis found in database")
    return analysis


def count_graph_stats(db: Session, analysis_id: int) -> Dict[str, Any]:
    """Get graph statistics."""
    symbol_count = db.query(FactSymbol).filter(
        FactSymbol.analysis_id == analysis_id
    ).count()

    relationship_count = db.query(FactRelationship).filter(
        FactRelationship.analysis_id == analysis_id
    ).count()

    file_count = db.query(FactFile).filter(
        FactFile.analysis_id == analysis_id
    ).count()

    return {
        "symbols": symbol_count,
        "relationships": relationship_count,
        "files": file_count,
    }


# ============================================================================
# MAIN EVALUATION
# ============================================================================

def run_evaluation():
    """Execute full evaluation."""
    logger.info("=" * 80)
    logger.info("RIM PRODUCT VALUE EVALUATION")
    logger.info("=" * 80)

    db = SessionLocal()

    try:
        # Get analysis
        analysis = get_default_analysis(db)
        if not analysis:
            logger.error("No analysis available for evaluation")
            return

        # Log graph stats
        stats = count_graph_stats(db, analysis.id)
        logger.info(f"Graph Statistics: {json.dumps(stats, indent=2)}")
        logger.info("")

        # Create evaluator
        evaluator = RIMProductEvaluator(analysis.id, db)

        # Evaluate all use cases
        all_comparisons = []
        use_case_results = {}

        for use_case in USE_CASES:
            logger.info(f"\n{'='*80}")
            logger.info(f"USE CASE: {use_case.name}")
            logger.info(f"Description: {use_case.description}")
            logger.info(f"{'='*80}\n")

            # Evaluate queries in this use case (sample first 2)
            sample_queries = use_case.queries[:2]
            comparisons = evaluator.compare_queries(sample_queries)
            all_comparisons.extend(comparisons)

            # Summarize use case
            rim_adds_value_count = sum(1 for c in comparisons if c.rim_adds_value)
            rim_essential_count = sum(1 for c in comparisons if c.rim_essential)

            use_case_results[use_case.id] = {
                "name": use_case.name,
                "queries_tested": len(sample_queries),
                "rim_adds_value": rim_adds_value_count,
                "rim_essential": rim_essential_count,
                "avg_latency_increase_pct": (
                    sum(c.latency_increase_pct for c in comparisons) / len(comparisons)
                    if comparisons else 0
                ),
                "avg_context_increase_pct": (
                    sum(c.context_increase_pct for c in comparisons) / len(comparisons)
                    if comparisons else 0
                ),
            }

        # Generate report
        generate_report(all_comparisons, use_case_results, stats)

    finally:
        db.close()


def generate_report(
    comparisons: List[QueryComparison],
    use_case_results: Dict[str, Any],
    graph_stats: Dict[str, Any],
):
    """Generate evaluation report."""

    logger.info("\n" + "=" * 80)
    logger.info("RIM PRODUCT VALUE EVALUATION - REPORT")
    logger.info("=" * 80)

    # Summary table
    logger.info("\nCOMPARISON TABLE (Baseline vs RIM):")
    logger.info("-" * 120)
    logger.info(f"{'Query':<50} {'Baseline Sufficient':<20} {'RIM Adds Value':<20} {'RIM Essential':<15}")
    logger.info("-" * 120)

    for comp in comparisons:
        logger.info(f"{comp.query[:49]:<50} {str(comp.baseline_sufficient):<20} {str(comp.rim_adds_value):<20} {str(comp.rim_essential):<15}")

    logger.info("-" * 120)

    # Per-use-case analysis
    logger.info("\nPER-USE-CASE ANALYSIS:")
    logger.info("-" * 100)
    for use_case_id, results in use_case_results.items():
        logger.info(f"\n{results['name']}:")
        logger.info(f"  Queries Tested: {results['queries_tested']}")
        logger.info(f"  RIM Adds Value: {results['rim_adds_value']}/{results['queries_tested']}")
        logger.info(f"  RIM Essential: {results['rim_essential']}/{results['queries_tested']}")
        logger.info(f"  Avg Latency Increase: {results['avg_latency_increase_pct']:.1f}%")
        logger.info(f"  Avg Context Increase: {results['avg_context_increase_pct']:.1f}%")

    # Efficiency analysis
    logger.info("\nEFFICIENCY ANALYSIS:")
    logger.info("-" * 80)

    avg_latency_increase = (
        sum(c.latency_increase_pct for c in comparisons) / len(comparisons)
        if comparisons else 0
    )
    avg_context_increase = (
        sum(c.context_increase_pct for c in comparisons) / len(comparisons)
        if comparisons else 0
    )

    logger.info(f"Average Latency Increase: {avg_latency_increase:.1f}%")
    logger.info(f"Average Context Size Increase: {avg_context_increase:.1f}%")
    logger.info(f"Total Queries Evaluated: {len(comparisons)}")

    # Value summary
    value_count = sum(1 for c in comparisons if c.rim_adds_value)
    essential_count = sum(1 for c in comparisons if c.rim_essential)
    quality_improved_count = sum(1 for c in comparisons if c.quality_improved)

    logger.info(f"\nRIM VALUE SUMMARY:")
    logger.info(f"  Queries where RIM adds value: {value_count}/{len(comparisons)}")
    logger.info(f"  Queries where RIM is essential: {essential_count}/{len(comparisons)}")
    logger.info(f"  Queries with improved quality: {quality_improved_count}/{len(comparisons)}")

    # Product verdict
    logger.info("\n" + "=" * 80)
    logger.info("PRODUCT VERDICT")
    logger.info("=" * 80)

    if value_count >= len(comparisons) * 0.7 and avg_latency_increase < 30:
        verdict = "STRONG"
        justification = "RIM demonstrates clear value across most use cases with acceptable latency cost."
    elif value_count >= len(comparisons) * 0.4 and avg_latency_increase < 50:
        verdict = "PROMISING"
        justification = "RIM adds value in several scenarios; targeted improvements recommended before frontend."
    elif value_count > 0 and avg_latency_increase < 100:
        verdict = "WEAK"
        justification = "RIM works technically but provides limited value; complexity cost not justified."
    else:
        verdict = "NOT READY"
        justification = "RIM shows insufficient value or critical issues; requires fixes before further development."

    logger.info(f"\nVerdict: {verdict}")
    logger.info(f"Justification: {justification}")

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)

    logger.info(f"""
Graph Statistics:
  - Symbols: {graph_stats['symbols']}
  - Relationships: {graph_stats['relationships']}
  - Files: {graph_stats['files']}

Evaluation Results:
  - Use Cases Tested: {len(use_case_results)}
  - Total Queries: {len(comparisons)}
  - RIM Adds Value: {value_count}/{len(comparisons)} ({value_count*100//len(comparisons) if comparisons else 0}%)
  - RIM Essential: {essential_count}/{len(comparisons)} ({essential_count*100//len(comparisons) if comparisons else 0}%)
  - Quality Improved: {quality_improved_count}/{len(comparisons)} ({quality_improved_count*100//len(comparisons) if comparisons else 0}%)

Performance Impact:
  - Avg Latency Increase: {avg_latency_increase:.1f}%
  - Avg Context Increase: {avg_context_increase:.1f}%

Recommendation: {verdict}
""")


if __name__ == "__main__":
    run_evaluation()
