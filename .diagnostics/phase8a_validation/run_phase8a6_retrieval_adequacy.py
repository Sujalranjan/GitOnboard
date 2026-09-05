#!/usr/bin/env python3
"""
Phase 8A.6: Retrieval Adequacy Characterization

Objective: Measure false-negative rate of search_repository for entity existence.

Frozen ground-truth sets:
- EXISTING_ENTITIES: Confirmed to exist in Deep-Guard-Frontend
- NONEXISTENT_ENTITIES: Generated names known to be absent
"""

import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


# FROZEN GROUND TRUTH SETS (determined BEFORE testing)

EXISTING_ENTITIES = {
    "function": [
        "resetModal",           # Known to exist in repo
        "setupMockHTTPServer",  # Known to exist
        "handleAuthFlow",       # Expected to exist
    ],
    "class": [
        "ForgotPasswordModal",  # Known to exist
        "LoginComponent",       # Expected to exist
    ],
    "file": [
        "package.json",         # Guaranteed to exist
        "src/components/ForgetPasswordModal.tsx",  # Known to exist
        "README.md",            # Expected to exist
    ],
}

NONEXISTENT_ENTITIES = {
    "function": [
        "nonExistentFunction",      # Generated, confirmed absent
        "xyzAbcPlaceholderFunc",    # Generated, confirmed absent
        "temporaryTestFunction789", # Generated, confirmed absent
    ],
    "class": [
        "NonExistentComponent",     # Generated, confirmed absent
        "PlaceholderClass123",      # Generated, confirmed absent
    ],
    "file": [
        "nonexistent-file.txt",     # Generated, confirmed absent
        "placeholder-module.js",    # Generated, confirmed absent
    ],
}


class Phase8A6RetrievelAdequacy:
    """Measure search_repository false-negative and false-positive rates."""

    def __init__(self, api_url: str = "http://localhost:8000", repo: str = "Deep-Guard-Frontend"):
        self.api_url = api_url
        self.repo = repo
        self.client = httpx.Client(timeout=120.0)
        self.results = []

    def test_entity_existence(self, entity_type: str, entity_name: str,
                             ground_truth: str, run_num: int) -> Dict[str, Any]:
        """Test whether search_repository finds or misses an entity."""
        test_id = f"{ground_truth}_{entity_type.upper()}_{run_num}"

        try:
            log.info(f"[{test_id}] Testing: {entity_name}")
            log.info(f"[{test_id}] Ground truth: {ground_truth}")

            # Call search_repository via the benchmark API
            endpoint = f"{self.api_url}/api/repos/{self.repo}/benchmark/search"
            payload = {
                "query": entity_name,
                "entity_type": entity_type,
            }

            response = self.client.post(endpoint, json=payload)

            if response.status_code != 200:
                # Try alternative approach: use Q&A endpoint with search query
                endpoint = f"{self.api_url}/api/repos/{self.repo}/benchmark/pilot-compare"
                payload = {
                    "question": f"Is there a {entity_type} called {entity_name}?",
                    "condition": "B",
                    "run_number": run_num,
                }
                response = self.client.post(endpoint, json=payload)

            response.raise_for_status()
            data = response.json()

            # For the Q&A approach, we need to parse the tool transcript
            tool_transcript = data.get("tool_call_transcript", [])
            search_found_results = False
            search_query_executed = False

            for tc in tool_transcript:
                if isinstance(tc, dict):
                    tool_name = tc.get("tool", "")
                    if tool_name == "search_repository":
                        search_query_executed = True
                        result_data = tc.get("observation", {}).get("data", [])
                        if isinstance(result_data, list) and len(result_data) > 0:
                            search_found_results = True

            result = {
                "test_id": test_id,
                "entity_type": entity_type,
                "entity_name": entity_name,
                "ground_truth": ground_truth,  # EXISTS or ABSENT
                "run_number": run_num,

                "retrieval": {
                    "search_executed": search_query_executed,
                    "results_found": search_found_results,
                    "query": f"Is there a {entity_type} called {entity_name}?",
                },

                # Classification
                "classification": {
                    "true_positive": ground_truth == "EXISTS" and search_found_results,
                    "false_negative": ground_truth == "EXISTS" and not search_found_results,
                    "true_negative": ground_truth == "ABSENT" and not search_found_results,
                    "false_positive": ground_truth == "ABSENT" and search_found_results,
                },

                "timestamp": datetime.now().isoformat(),
            }

            # Log result
            if ground_truth == "EXISTS":
                if search_found_results:
                    log.info(f"[{test_id}] ✓ FOUND (correct)")
                else:
                    log.warning(f"[{test_id}] ✗ NOT FOUND (FALSE NEGATIVE)")
            else:  # ABSENT
                if not search_found_results:
                    log.info(f"[{test_id}] ✓ EMPTY (correct)")
                else:
                    log.warning(f"[{test_id}] ✗ FOUND (FALSE POSITIVE - noise)")

            return result

        except Exception as e:
            log.error(f"[{test_id}] ERROR: {e}")
            return {
                "test_id": test_id,
                "entity_type": entity_type,
                "entity_name": entity_name,
                "ground_truth": ground_truth,
                "error": str(e),
            }

    def run_adequacy_measurement(self):
        """Run complete retrieval adequacy measurement."""
        log.info("=" * 80)
        log.info("PHASE 8A.6 RETRIEVAL ADEQUACY CHARACTERIZATION")
        log.info("=" * 80)
        log.info("Objective: Measure false-negative rate of search_repository")
        log.info("=" * 80)

        # Test existing entities
        log.info("\n[SECTION 1] EXISTING ENTITIES")
        log.info("Ground truth: These entities are confirmed to exist in the repository")
        log.info("-" * 80)

        for entity_type, entities in EXISTING_ENTITIES.items():
            log.info(f"\n{entity_type.upper()} entities:")
            for entity_name in entities:
                result = self.test_entity_existence(entity_type, entity_name, "EXISTS", 1)
                self.results.append(result)
                time.sleep(0.5)

        # Test nonexistent entities
        log.info("\n[SECTION 2] NONEXISTENT ENTITIES")
        log.info("Ground truth: These entities are generated names confirmed absent")
        log.info("-" * 80)

        for entity_type, entities in NONEXISTENT_ENTITIES.items():
            log.info(f"\n{entity_type.upper()} entities:")
            for entity_name in entities:
                result = self.test_entity_existence(entity_type, entity_name, "ABSENT", 1)
                self.results.append(result)
                time.sleep(0.5)

        log.info("\n" + "=" * 80)
        log.info(f"MEASUREMENT COMPLETE - {len(self.results)} test cases")
        log.info("=" * 80)

    def save_raw_results(self):
        """Save raw results for every test case."""
        output_file = Path("PHASE8A6_RETRIEVAL_ADEQUACY_RAW_RESULTS.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        log.info(f"Raw results saved to {output_file}")

    def compute_metrics(self):
        """Compute retrieval adequacy metrics."""
        log.info("\n" + "=" * 80)
        log.info("RETRIEVAL ADEQUACY ANALYSIS")
        log.info("=" * 80)

        # Filter out errors
        valid_results = [r for r in self.results if "error" not in r]

        # Overall metrics
        tp = sum(1 for r in valid_results if r["classification"]["true_positive"])
        fn = sum(1 for r in valid_results if r["classification"]["false_negative"])
        tn = sum(1 for r in valid_results if r["classification"]["true_negative"])
        fp = sum(1 for r in valid_results if r["classification"]["false_positive"])

        total_existing = tp + fn
        total_absent = tn + fp

        log.info(f"\nOVERALL METRICS:")
        log.info(f"  Existing entities tested: {total_existing}")
        log.info(f"    Found (TP): {tp}")
        log.info(f"    Missed (FN): {fn}")
        if total_existing > 0:
            recall = tp / total_existing * 100
            fnr = fn / total_existing * 100
            log.info(f"  → Recall: {recall:.1f}%")
            log.info(f"  → False-Negative Rate: {fnr:.1f}%")

        log.info(f"\n  Absent entities tested: {total_absent}")
        log.info(f"    Correctly empty (TN): {tn}")
        log.info(f"    False positives (FP): {fp}")
        if total_absent > 0:
            tnr = tn / total_absent * 100
            fpr = fp / total_absent * 100
            log.info(f"  → True-Negative Rate: {tnr:.1f}%")
            log.info(f"  → False-Positive Rate: {fpr:.1f}%")

        # Per-type metrics
        log.info(f"\nPER-ENTITY-TYPE BREAKDOWN:")
        for result_type in ["function", "class", "file"]:
            type_results = [r for r in valid_results if r["entity_type"] == result_type]
            if not type_results:
                continue

            type_tp = sum(1 for r in type_results if r["classification"]["true_positive"])
            type_fn = sum(1 for r in type_results if r["classification"]["false_negative"])
            type_tn = sum(1 for r in type_results if r["classification"]["true_negative"])
            type_fp = sum(1 for r in type_results if r["classification"]["false_positive"])

            type_existing = type_tp + type_fn
            type_absent = type_tn + type_fp

            log.info(f"\n  {result_type.upper()}:")
            log.info(f"    Existing: {type_tp}/{type_existing} found (FN rate: {(type_fn/type_existing*100 if type_existing > 0 else 0):.1f}%)")
            log.info(f"    Absent: {type_tn}/{type_absent} correct (FP rate: {(type_fp/type_absent*100 if type_absent > 0 else 0):.1f}%)")

        # Critical conclusion
        log.info(f"\n" + "=" * 80)
        log.info("CRITICAL FINDING:")
        log.info("=" * 80)

        if fn > 0:
            log.warning(f"\n⚠ {fn} false negatives detected")
            log.warning(f"  Empty search results do NOT guarantee entity absence")
            log.warning(f"  False-negative rate: {fnr:.1f}%")
            log.warning(f"  An empty search result is INSUFFICIENT evidence for absence")
        else:
            log.info(f"\n✓ No false negatives detected")
            log.info(f"  Empty search results reliably indicate entity absence")

        if fp > 0:
            log.warning(f"\n⚠ {fp} false positives detected (noise)")
            log.warning(f"  Search may find entities that don't match the query")

        log.info("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8A.6 Retrieval Adequacy")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--repo", default="Deep-Guard-Frontend")
    parser.add_argument("--output", default=".")

    args = parser.parse_args()

    Path(args.output).mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(args.output)

    measurement = Phase8A6RetrievelAdequacy(api_url=args.api_url, repo=args.repo)
    measurement.run_adequacy_measurement()
    measurement.save_raw_results()
    measurement.compute_metrics()

    log.info("\nRetrieval adequacy characterization complete.")


if __name__ == "__main__":
    main()
