#!/usr/bin/env python3
"""
Phase 8A.7: Retrieval Failure Localization

Objective: Classify each false negative by exact failure point.

Four cases from Phase 8A.6:
1. setupMockHTTPServer (function) - missed
2. handleAuthFlow (function) - missed
3. ForgotPasswordModal (class) - missed
4. LoginComponent (class) - missed

For each, trace complete pipeline and localize failure.
"""

import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import httpx

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class Phase8A7FailureLocalization:
    """Investigate and localize retrieval failures."""

    def __init__(self, api_url: str = "http://localhost:8000", repo: str = "Deep-Guard-Frontend"):
        self.api_url = api_url
        self.repo = repo
        self.client = httpx.Client(timeout=120.0)
        self.results = []

    def investigate_false_negative(self, entity_name: str, entity_type: str,
                                   case_num: int) -> Dict[str, Any]:
        """
        Investigate a single false negative case.

        Traces through pipeline layers:
        1. Tool selection
        2. Tool invocation
        3. Query construction
        4. Search execution
        5. Result matching
        6. Serialization
        """

        case_id = f"FN{case_num}_{entity_type.upper()}_{entity_name}"

        try:
            log.info(f"\n{'='*80}")
            log.info(f"[{case_id}] Investigating false negative")
            log.info(f"Entity: {entity_name} ({entity_type})")
            log.info(f"Ground truth: EXISTS (but search returned empty in Phase 8A.6)")
            log.info(f"{'='*80}")

            # Query through the system to capture complete trace
            log.info(f"\n[{case_id}] Layer 1: Tool Selection")
            query = f"Is there a {entity_type} called {entity_name}?"
            log.info(f"Query to LLM: {query}")

            endpoint = f"{self.api_url}/api/repos/{self.repo}/benchmark/pilot-compare"
            payload = {
                "question": query,
                "condition": "B",
                "run_number": 1,
                "debug_mode": True,  # Request enhanced logging if available
            }

            response = self.client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract trace
            tool_call_transcript = data.get("tool_call_transcript", [])
            answer = data.get("answer", "")

            # Analyze pipeline layers
            trace = {
                "case_id": case_id,
                "entity_name": entity_name,
                "entity_type": entity_type,
                "query": query,
                "timestamp": datetime.now().isoformat(),

                "layers": {},
                "classification": None,
                "evidence": [],
            }

            # Layer 1: Tool Selection
            search_repository_called = False
            search_query = None

            for tc in tool_call_transcript:
                if isinstance(tc, dict) and tc.get("tool") == "search_repository":
                    search_repository_called = True
                    search_query = tc.get("input", {}).get("arguments", {}).get("query")
                    break

            trace["layers"]["tool_selection"] = {
                "search_repository_called": search_repository_called,
                "search_query": search_query,
            }

            log.info(f"[{case_id}] Layer 1 Result: search_repository called = {search_repository_called}")
            if search_query:
                log.info(f"[{case_id}]   Search query: {search_query}")

            # Layer 2: Tool Invocation
            if search_repository_called:
                log.info(f"\n[{case_id}] Layer 2: Tool Invocation")
                search_results = None
                search_success = None

                for tc in tool_call_transcript:
                    if isinstance(tc, dict) and tc.get("tool") == "search_repository":
                        obs = tc.get("observation", {})
                        search_success = obs.get("success", False)
                        search_results = obs.get("data", [])
                        break

                trace["layers"]["tool_invocation"] = {
                    "search_executed": True,
                    "search_success": search_success,
                    "results_returned": len(search_results) if isinstance(search_results, list) else 0,
                    "results_sample": search_results[:2] if isinstance(search_results, list) else None,
                }

                log.info(f"[{case_id}] Layer 2 Result: search executed = True")
                log.info(f"[{case_id}]   Search success = {search_success}")
                log.info(f"[{case_id}]   Results returned = {len(search_results) if isinstance(search_results, list) else 0}")

                if isinstance(search_results, list) and len(search_results) > 0:
                    log.info(f"[{case_id}]   Sample results: {search_results[:2]}")

            else:
                log.info(f"\n[{case_id}] Layer 2: Tool Invocation")
                log.warning(f"[{case_id}] search_repository was NOT called")
                trace["layers"]["tool_invocation"] = {
                    "search_executed": False,
                    "reason": "Tool not selected by LLM",
                }

            # Layer 3: Query Construction
            log.info(f"\n[{case_id}] Layer 3: Query Construction")
            if search_query:
                log.info(f"[{case_id}] Constructed query: '{search_query}'")
                log.info(f"[{case_id}] Expected to contain: '{entity_name}'")

                if entity_name.lower() in search_query.lower():
                    log.info(f"[{case_id}] ✓ Entity name present in query")
                    trace["layers"]["query_construction"] = {"adequate": True}
                else:
                    log.warning(f"[{case_id}] ✗ Entity name MISSING from query")
                    trace["layers"]["query_construction"] = {"adequate": False, "issue": "entity_name_missing"}

            # Layer 4-7: Answer analysis
            log.info(f"\n[{case_id}] Final Answer")
            log.info(f"Answer: {answer[:150]}")

            # Determine classification
            if not search_repository_called:
                trace["classification"] = "TOOL_SELECTION_FAILURE"
                trace["evidence"].append("search_repository was not invoked by LLM")

            elif search_query and entity_name.lower() not in search_query.lower():
                trace["classification"] = "QUERY_CONSTRUCTION_FAILURE"
                trace["evidence"].append(f"Entity '{entity_name}' not in constructed query '{search_query}'")

            elif isinstance(search_results, list) and len(search_results) == 0:
                trace["classification"] = "INDEX_COVERAGE_FAILURE"
                trace["evidence"].append(f"Query '{search_query}' executed but returned no results")
                trace["evidence"].append("Indicates entity not in searchable index or index coverage gap")

            else:
                trace["classification"] = "UNKNOWN_FAILURE"
                trace["evidence"].append("Could not localize failure from available data")

            log.info(f"\n[{case_id}] CLASSIFICATION: {trace['classification']}")
            for evidence in trace["evidence"]:
                log.info(f"  Evidence: {evidence}")

            return trace

        except Exception as e:
            log.error(f"[{case_id}] ERROR: {e}")
            return {
                "case_id": case_id,
                "entity_name": entity_name,
                "entity_type": entity_type,
                "error": str(e),
            }

    def run_localization_investigation(self):
        """Investigate all four false negatives."""
        log.info("=" * 80)
        log.info("PHASE 8A.7: RETRIEVAL FAILURE LOCALIZATION")
        log.info("=" * 80)
        log.info("Objective: Classify each false negative by failure point")
        log.info("=" * 80)

        # The four false negatives from Phase 8A.6
        false_negatives = [
            ("setupMockHTTPServer", "function", 1),
            ("handleAuthFlow", "function", 2),
            ("ForgotPasswordModal", "class", 3),
            ("LoginComponent", "class", 4),
        ]

        for entity_name, entity_type, case_num in false_negatives:
            result = self.investigate_false_negative(entity_name, entity_type, case_num)
            self.results.append(result)
            time.sleep(2.0)

        log.info("\n" + "=" * 80)
        log.info(f"INVESTIGATION COMPLETE - {len(self.results)} false negatives analyzed")
        log.info("=" * 80)

    def save_detailed_traces(self):
        """Save complete traces for each case."""
        output_file = Path("PHASE8A7_FAILURE_LOCALIZATION_RAW_TRACES.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        log.info(f"Traces saved to {output_file}")

    def generate_classification_table(self):
        """Generate summary classification table."""
        log.info("\n" + "=" * 80)
        log.info("FAILURE CLASSIFICATION SUMMARY")
        log.info("=" * 80)

        classifications = {}
        for result in self.results:
            if "error" in result:
                continue

            classification = result.get("classification", "UNKNOWN")
            if classification not in classifications:
                classifications[classification] = []

            classifications[classification].append({
                "entity": result.get("entity_name"),
                "type": result.get("entity_type"),
                "evidence": result.get("evidence", []),
            })

        log.info("\nCLASSIFICATION BREAKDOWN:")
        for classification, cases in sorted(classifications.items()):
            log.info(f"\n{classification}: {len(cases)} case(s)")
            for case in cases:
                log.info(f"  {case['entity']} ({case['type']})")
                for evidence in case["evidence"]:
                    log.info(f"    - {evidence}")

        # Save summary
        summary_file = Path("PHASE8A7_CLASSIFICATION_SUMMARY.json")
        with open(summary_file, "w") as f:
            json.dump(classifications, f, indent=2)
        log.info(f"\nClassification summary saved to {summary_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8A.7 Failure Localization")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--repo", default="Deep-Guard-Frontend")
    parser.add_argument("--output", default=".")

    args = parser.parse_args()

    Path(args.output).mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(args.output)

    investigation = Phase8A7FailureLocalization(api_url=args.api_url, repo=args.repo)
    investigation.run_localization_investigation()
    investigation.save_detailed_traces()
    investigation.generate_classification_table()

    log.info("\nRetrieval failure localization complete.")
    log.info("Do NOT modify code based on these findings.")
    log.info("Phase 8A.7 is INVESTIGATION ONLY.")


if __name__ == "__main__":
    main()
