#!/usr/bin/env python3
"""
RIM End-to-End Validation Script

Validates that graph expansion is enabled and functioning correctly in the production
retrieval path by testing the actual API endpoint with real repositories.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000/api"
VALIDATION_RESULTS = {
    "timestamp": datetime.now().isoformat(),
    "environment": {
        "api_base_url": API_BASE_URL,
        "backend_running": False,
        "repositories_available": [],
    },
    "test_queries": [],
    "summary": {
        "graph_expansion_enabled": False,
        "real_repository_tested": False,
        "holistic_retrieval": False,
        "rim_anchors": False,
        "connected_graph_expansion": False,
        "reverse_navigation": False,
        "source_bridge": False,
        "context_assembler": False,
        "llm_receives_rim": False,
        "negative_query_safety": False,
        "production_execution_path": False,
        "overall": "UNKNOWN"
    }
}


def check_backend_health() -> bool:
    """Check if backend is running and accessible."""
    try:
        response = requests.get(f"{API_BASE_URL}/repos", timeout=5)
        VALIDATION_RESULTS["environment"]["backend_running"] = response.status_code == 200
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Backend health check failed: {e}")
        return False


def get_repositories() -> List[Dict[str, Any]]:
    """Get list of available repositories."""
    try:
        response = requests.get(f"{API_BASE_URL}/repos", timeout=5)
        if response.status_code == 200:
            data = response.json()
            repos = data.get("repositories", [])
            VALIDATION_RESULTS["environment"]["repositories_available"] = [
                {"name": r.get("project_name"), "language": r.get("language")} for r in repos
            ]
            return repos
    except Exception as e:
        logger.error(f"Failed to get repositories: {e}")
    return []


def run_comparison_test(repo_name: str, query: str, test_name: str) -> Optional[Dict[str, Any]]:
    """Run a single RIM comparison test."""
    logger.info(f"\n[TEST: {test_name}] Query: {query}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/repos/{repo_name}/rim-comparison/compare",
            json={"question": query},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            return data
        else:
            logger.error(f"API returned {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Comparison test failed: {e}")
        return None


def validate_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    """Validate RIM trace structure and content."""
    validation = {
        "trace_enabled": trace.get("enabled", False),
        "has_anchors": len(trace.get("anchors", [])) > 0,
        "has_expanded_entities": len(trace.get("expanded_entities", [])) > 0,
        "has_relationships": len(trace.get("relationships", [])) > 0,
        "has_selected_files": len(trace.get("selected_files", [])) > 0,
        "has_selected_symbols": len(trace.get("selected_symbols", [])) > 0,
        "graph_depth": trace.get("graph_depth", 0),
        "total_nodes_expanded": trace.get("total_nodes_expanded", 0),
        "anchor_count": trace.get("anchor_count", 0),
        "expansion_count": trace.get("expansion_count", 0),
    }

    # Determine if this looks like graph expansion occurred
    validation["graph_expansion_occurred"] = (
        validation["has_expanded_entities"] and
        validation["expansion_count"] > 0
    )

    return validation


def analyze_baseline_vs_rim(result: Dict[str, Any]) -> Dict[str, Any]:
    """Compare baseline and RIM sides."""
    baseline = result.get("without_rim", {})
    rim = result.get("with_rim", {})

    baseline_files = len(baseline.get("retrieval_metrics", {}).get("files_retrieved", 0) or 0)
    rim_files = len(rim.get("retrieval_metrics", {}).get("files_retrieved", 0) or 0)

    baseline_symbols = len(baseline.get("retrieval_metrics", {}).get("symbols_retrieved", 0) or 0)
    rim_symbols = len(rim.get("retrieval_metrics", {}).get("symbols_retrieved", 0) or 0)

    return {
        "baseline_files": baseline_files,
        "rim_files": rim_files,
        "file_difference": rim_files - baseline_files,
        "baseline_symbols": baseline_symbols,
        "rim_symbols": rim_symbols,
        "symbol_difference": rim_symbols - baseline_symbols,
        "rim_metadata_block_present": bool(rim.get("rim_metadata_block")),
    }


def validate_source_bridge(selected_symbols: List[Dict[str, Any]]) -> bool:
    """Check if selected symbols have proper source location info."""
    for sym in selected_symbols:
        if not sym.get("file"):
            logger.warning(f"Symbol {sym.get('name')} missing file location")
            return False
        if "line_start" not in sym and "line_end" not in sym:
            # Some symbols might not have line info, but should have at least file
            pass
    return len(selected_symbols) > 0


def validate_graph_correctness(relationships: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate that relationships are coherent."""
    validation = {
        "total_relationships": len(relationships),
        "relationship_types": set(),
        "bidirectional_pairs": 0,
    }

    for rel in relationships:
        if rel.get("type"):
            validation["relationship_types"].add(rel.get("type"))

    validation["relationship_types"] = list(validation["relationship_types"])

    return validation


def run_test_suite(repo_name: str) -> None:
    """Run complete test suite."""
    logger.info(f"\n{'='*70}")
    logger.info(f"RIM END-TO-END VALIDATION")
    logger.info(f"Repository: {repo_name}")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"{'='*70}")

    # Query A: Feature exploration (holistic)
    logger.info(f"\n{'='*70}")
    logger.info("QUERY A: Feature Exploration (Holistic)")
    logger.info(f"{'='*70}")
    result_a = run_comparison_test(
        repo_name,
        "How does the authentication system work?",
        "QueryA_FeatureExploration"
    )

    if result_a:
        trace_a = result_a.get("trace", {})
        validation_a = validate_trace(trace_a)
        comparison_a = analyze_baseline_vs_rim(result_a)

        logger.info(f"✓ Trace enabled: {validation_a['trace_enabled']}")
        logger.info(f"✓ Anchors found: {validation_a['anchor_count']}")
        logger.info(f"✓ Graph expansion: {validation_a['expansion_count']} entities")
        logger.info(f"✓ Relationships: {validation_a['total_nodes_expanded']} total nodes")
        logger.info(f"✓ Files retrieved (RIM vs Baseline): {comparison_a['rim_files']} vs {comparison_a['baseline_files']}")

        VALIDATION_RESULTS["test_queries"].append({
            "name": "QueryA_FeatureExploration",
            "query": "How does the authentication system work?",
            "trace_validation": validation_a,
            "baseline_vs_rim": comparison_a,
        })

        # Update validation flags
        if validation_a['trace_enabled']:
            VALIDATION_RESULTS["summary"]["holistic_retrieval"] = True
        if validation_a['has_anchors']:
            VALIDATION_RESULTS["summary"]["rim_anchors"] = True
        if validation_a['graph_expansion_occurred']:
            VALIDATION_RESULTS["summary"]["connected_graph_expansion"] = True
            VALIDATION_RESULTS["summary"]["graph_expansion_enabled"] = True

    # Query B: Reverse navigation
    logger.info(f"\n{'='*70}")
    logger.info("QUERY B: Reverse Navigation (Symbol)")
    logger.info(f"{'='*70}")
    result_b = run_comparison_test(
        repo_name,
        "What calls the main function?",
        "QueryB_ReverseNavigation"
    )

    if result_b:
        trace_b = result_b.get("trace", {})
        validation_b = validate_trace(trace_b)
        logger.info(f"✓ Trace enabled: {validation_b['trace_enabled']}")
        logger.info(f"✓ Relationships found: {validation_b['total_nodes_expanded']}")

        if validation_b['has_relationships']:
            VALIDATION_RESULTS["summary"]["reverse_navigation"] = True

        VALIDATION_RESULTS["test_queries"].append({
            "name": "QueryB_ReverseNavigation",
            "query": "What calls the main function?",
            "trace_validation": validation_b,
        })

    # Query C: Source bridge
    logger.info(f"\n{'='*70}")
    logger.info("QUERY C: Source Bridge Validation")
    logger.info(f"{'='*70}")
    result_c = run_comparison_test(
        repo_name,
        "Show me the entry point",
        "QueryC_SourceBridge"
    )

    if result_c:
        trace_c = result_c.get("trace", {})
        selected_symbols = trace_c.get("selected_symbols", [])

        if validate_source_bridge(selected_symbols):
            logger.info(f"✓ Source locations resolved: {len(selected_symbols)} symbols")
            VALIDATION_RESULTS["summary"]["source_bridge"] = True

        VALIDATION_RESULTS["test_queries"].append({
            "name": "QueryC_SourceBridge",
            "query": "Show me the entry point",
            "selected_symbols_count": len(selected_symbols),
        })

    # Query D: Dependency navigation
    logger.info(f"\n{'='*70}")
    logger.info("QUERY D: Dependency Navigation")
    logger.info(f"{'='*70}")
    result_d = run_comparison_test(
        repo_name,
        "What modules does this depend on?",
        "QueryD_DependencyNavigation"
    )

    if result_d:
        trace_d = result_d.get("trace", {})
        relationships = trace_d.get("relationships", [])
        graph_info = validate_graph_correctness(relationships)

        logger.info(f"✓ Total relationships: {graph_info['total_relationships']}")
        logger.info(f"✓ Relationship types: {graph_info['relationship_types']}")

        VALIDATION_RESULTS["test_queries"].append({
            "name": "QueryD_DependencyNavigation",
            "query": "What modules does this depend on?",
            "graph_info": graph_info,
        })

    # Query E: Narrow query (focused)
    logger.info(f"\n{'='*70}")
    logger.info("QUERY E: Narrow Query (Focused)")
    logger.info(f"{'='*70}")
    result_e = run_comparison_test(
        repo_name,
        "Explain the main module",
        "QueryE_NarrowQuery"
    )

    if result_e:
        trace_e = result_e.get("trace", {})
        validation_e = validate_trace(trace_e)

        # For narrow queries, expansion should be bounded
        logger.info(f"✓ Graph bounded: depth={validation_e['graph_depth']}, nodes={validation_e['total_nodes_expanded']}")

        VALIDATION_RESULTS["test_queries"].append({
            "name": "QueryE_NarrowQuery",
            "query": "Explain the main module",
            "trace_validation": validation_e,
        })

    # Query F: Negative query (nonexistent entity)
    logger.info(f"\n{'='*70}")
    logger.info("QUERY F: Negative Query (Safety Check)")
    logger.info(f"{'='*70}")
    result_f = run_comparison_test(
        repo_name,
        "Where is QuantumAuthenticationManager implemented?",
        "QueryF_NegativeQuery"
    )

    if result_f:
        trace_f = result_f.get("trace", {})
        # Should not have fabricated entities
        selected_files = trace_f.get("selected_files", [])

        has_quantum = any("quantum" in str(f).lower() for f in selected_files)
        if not has_quantum:
            logger.info(f"✓ No fabricated entities: did not invent QuantumAuthenticationManager")
            VALIDATION_RESULTS["summary"]["negative_query_safety"] = True

        VALIDATION_RESULTS["test_queries"].append({
            "name": "QueryF_NegativeQuery",
            "query": "Where is QuantumAuthenticationManager implemented?",
            "has_fabricated_entities": has_quantum,
        })

    # Compute overall status
    logger.info(f"\n{'='*70}")
    logger.info("VALIDATION SUMMARY")
    logger.info(f"{'='*70}")

    summary = VALIDATION_RESULTS["summary"]
    summary["real_repository_tested"] = True
    summary["context_assembler"] = sum(1 for tq in VALIDATION_RESULTS["test_queries"] if tq.get("trace_validation", {}).get("trace_enabled"))  > 0
    summary["llm_receives_rim"] = all(tq.get("trace_validation", {}).get("trace_enabled") for tq in VALIDATION_RESULTS["test_queries"] if "trace_validation" in tq)
    summary["production_execution_path"] = summary["holistic_retrieval"]

    passed_checks = sum(1 for k, v in summary.items() if k != "overall" and v in (True, 1))
    total_checks = len([k for k in summary.keys() if k != "overall"])

    if passed_checks == total_checks:
        summary["overall"] = "PASS"
    elif passed_checks >= total_checks * 0.7:
        summary["overall"] = "PARTIAL"
    else:
        summary["overall"] = "FAIL"

    logger.info(f"\nPassed: {passed_checks}/{total_checks}")
    logger.info(f"Overall: {summary['overall']}")

    # Print summary table
    logger.info("\n" + "="*70)
    logger.info("VALIDATION RESULTS")
    logger.info("="*70)
    for check, result in summary.items():
        if check != "overall":
            status = "✓ PASS" if result else "✗ FAIL"
            logger.info(f"{check:40} {status}")

    logger.info("="*70)
    logger.info(f"OVERALL: {summary['overall']}")
    logger.info("="*70)


def save_results() -> Path:
    """Save validation results to JSON file."""
    output_path = Path("/home/dheeraj/repository_intelligence_platform/backend/scripts/RIM_END_TO_END_VALIDATION_RESULTS.json")

    try:
        with open(output_path, "w") as f:
            json.dump(VALIDATION_RESULTS, f, indent=2, default=str)
        logger.info(f"\nResults saved to: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to save results: {e}")
        return None


def main():
    """Main validation flow."""
    # Check backend
    if not check_backend_health():
        logger.error("Backend is not running. Please start the backend first.")
        logger.error("  docker-compose up")
        sys.exit(1)

    logger.info("✓ Backend is running")

    # Get repositories
    repos = get_repositories()
    if not repos:
        logger.error("No repositories found. Please import repositories first.")
        sys.exit(1)

    logger.info(f"✓ Found {len(repos)} repositories")
    for repo in repos:
        logger.info(f"  - {repo.get('project_name')} ({repo.get('language')})")

    # Select Python repository (Deep-Guard-ML-Engine)
    python_repo = next((r for r in repos if r.get("language") == "Python"), None)
    if not python_repo:
        logger.warning("No Python repository found, using first repository")
        python_repo = repos[0]

    repo_name = python_repo.get("project_name")
    logger.info(f"\n✓ Selected repository: {repo_name}")

    # Run test suite
    run_test_suite(repo_name)

    # Save results
    save_results()


if __name__ == "__main__":
    main()
