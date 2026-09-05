#!/usr/bin/env python3
"""
Phase 8A.3 Step 6 - Enforcement Exposure Test

Objective: Create a controlled test case that reaches:
  absence_claim = TRUE
  evidence_verified = FALSE

Then observe whether the existing enforcement gate:
  - Blocks the answer
  - Triggers retry
  - Requests additional retrieval

This is NOT testing whether enforcement is good; it's testing whether
enforcement is actually TRIGGERED when detector identifies an unverified
absence claim.
"""

import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class EnforcementExposureTest:
    """Test whether gate actually blocks unverified absence claims."""

    def __init__(self, api_url: str = "http://localhost:8000", repo: str = "Deep-Guard-Frontend"):
        self.api_url = api_url
        self.repo = repo
        self.client = httpx.Client(timeout=120.0)
        self.results = []

    def run_unverified_absence_test(self, query: str, run_num: int, test_id: str) -> Dict:
        """
        Run a query designed to produce an absence claim without evidence.

        Strategy: Ask about something that does NOT exist in the repo,
        phrased in a way that might not trigger immediate evidence language.
        """
        run_id = f"{test_id}-{run_num}"

        try:
            log.info(f"[{run_id}] Testing enforcement exposure...")
            log.info(f"  Query: {query}")

            endpoint = f"{self.api_url}/api/repos/{self.repo}/benchmark/pilot-compare"
            payload = {
                "question": query,
                "condition": "B",  # RIM metadata enabled
                "run_number": run_num,
            }

            response = self.client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract response
            answer = data.get("answer", "")
            tool_call_count = data.get("tool_call_count", 0)
            tool_transcript = data.get("tool_call_transcript", [])

            # Parse tool execution
            tools_used = []
            search_performed = False
            retrieval_tools = {"search_repository", "read_file", "search_code", "get_symbol"}

            for tc in tool_transcript:
                if isinstance(tc, dict):
                    tool_name = tc.get("tool", "")
                    tools_used.append(tool_name)
                    if tool_name in retrieval_tools:
                        search_performed = True

            # Apply IMPROVED detector from production code
            answer_lower = answer.lower()

            # Direct negation patterns (primary)
            direct_negation = [
                "does not", "doesn't", "do not", "don't",
                "is not", "isn't", "was not", "wasn't",
                "are not", "aren't",
                "no function", "no module", "no package",
                "no component", "no service", "no feature",
                "no implementation", "no code",
                "there is no", "there are no", "there's no",
            ]

            # Soft negation patterns (secondary)
            soft_negation = [
                "does not appear", "doesn't appear",
                "appears not", "appears to not",
                "doesn't seem", "does not seem",
                "seems not",
                "unable to find", "cannot find",
                "could not find", "couldn't find",
                "found no",
                "no evidence", "no mention", "no instances",
                "no references",
                "not found", "not present", "not implemented",
                "not detected", "no results",
            ]

            # Context keywords
            entity_context = [
                "function", "module", "package", "library",
                "component", "service", "feature", "class",
                "interface", "method", "implementation",
                "pattern", "dependency", "tool", "framework",
                "redis", "database", "cache", "authentication",
                "reset", "recovery",
            ]

            repo_context = [
                "repository", "codebase", "project", "code", "repo",
                "this repo", "this project",
            ]

            # Improved detection logic
            has_direct = any(p in answer_lower for p in direct_negation)
            has_soft = any(p in answer_lower for p in soft_negation)
            has_context = (
                any(e in answer_lower for e in entity_context) or
                any(r in answer_lower for r in repo_context)
            )

            is_absence_claim = has_direct or (has_soft and has_context)

            # Evidence language detection
            evidence_keywords = ["searched", "found", "no results", "no matches", "search results"]
            has_evidence_language = any(kw in answer_lower for kw in evidence_keywords)

            # Was the answer blocked? (check for retry instruction)
            contains_retry_instruction = (
                "let me" in answer_lower and "search" in answer_lower
            ) or (
                "i should" in answer_lower and "search" in answer_lower
            ) or (
                "let me re-search" in answer_lower
            ) or (
                "let me search" in answer_lower and "answer" in answer_lower
            )

            result = {
                "run_id": run_id,
                "test_id": test_id,
                "query": query,
                "condition": "B",
                "run_number": run_num,

                # Detector analysis
                "detector_analysis": {
                    "answer_text": answer[:200],
                    "is_absence_claim": is_absence_claim,
                    "has_direct_negation": has_direct,
                    "has_soft_negation": has_soft,
                    "has_context": has_context,
                    "has_evidence_language": has_evidence_language,
                },

                # Execution trace
                "execution": {
                    "tool_count": tool_call_count,
                    "tools_used": tools_used,
                    "search_performed": search_performed,
                    "latency_ms": data.get("latency_ms", 0),
                },

                # Gate behavior
                "gate_behavior": {
                    "should_be_unverified": is_absence_claim and not has_evidence_language,
                    "answer_blocked": contains_retry_instruction,
                    "retry_requested": contains_retry_instruction,
                },

                # Final answer
                "answer_released": len(answer) > 0,
                "answer_full": answer,
                "timestamp": datetime.now().isoformat(),
            }

            # Log key findings
            log.info(f"[{run_id}] Detector: absence_claim={is_absence_claim} evidence={has_evidence_language}")
            log.info(f"[{run_id}] Expected unverified: {result['gate_behavior']['should_be_unverified']}")
            log.info(f"[{run_id}] Retry requested: {result['gate_behavior']['retry_requested']}")
            log.info(f"[{run_id}] Answer released: {result['answer_released']}")

            return result

        except Exception as e:
            log.error(f"[{run_id}] FAILED: {e}")
            return {
                "run_id": run_id,
                "test_id": test_id,
                "error": str(e),
                "query": query,
                "condition": "B",
                "run_number": run_num,
            }

    def run_enforcement_exposure_tests(self):
        """Run enforcement exposure tests."""
        log.info("=" * 80)
        log.info("PHASE 8A.3 ENFORCEMENT EXPOSURE TEST")
        log.info("=" * 80)
        log.info("Objective: Observe gate behavior when absence_claim=TRUE, evidence=FALSE")
        log.info("=" * 80)

        # Test 1: Non-existent feature with minimal context (may lack evidence language)
        log.info("\n[TEST 1] Non-existent Feature Query")
        log.info("Expected: Absence detected, may lack evidence language, observe gate behavior")
        for run in range(1, 3):
            # This feature doesn't exist in the repo
            result = self.run_unverified_absence_test(
                "Does this repo use GraphQL?",  # Deep-Guard-Frontend does NOT use GraphQL
                run,
                "NONEXISTENT_FEATURE"
            )
            self.results.append(result)
            time.sleep(2.0)

        # Test 2: Non-existent symbol
        log.info("\n[TEST 2] Non-existent Symbol Query")
        log.info("Expected: Absence claim detected, observe gate behavior")
        for run in range(1, 3):
            result = self.run_unverified_absence_test(
                "Is there a function called nonExistentFunction?",
                run,
                "NONEXISTENT_SYMBOL"
            )
            self.results.append(result)
            time.sleep(2.0)

        # Test 3: Non-existent technology
        log.info("\n[TEST 3] Non-existent Technology Query")
        log.info("Expected: Absence claim, observe gate behavior")
        for run in range(1, 3):
            result = self.run_unverified_absence_test(
                "Does this repo integrate with Kafka?",
                run,
                "NONEXISTENT_TECH"
            )
            self.results.append(result)
            time.sleep(2.0)

        log.info("=" * 80)
        log.info(f"ENFORCEMENT EXPOSURE TESTS COMPLETE - {len(self.results)} runs")
        log.info("=" * 80)

    def save_results(self):
        """Save test results."""
        output_file = Path("PHASE8A3_ENFORCEMENT_EXPOSURE_RAW_RESULTS.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        log.info(f"Results saved to {output_file}")

    def analyze_enforcement_exposure(self):
        """Analyze whether enforcement was exposed."""
        log.info("\n" + "=" * 80)
        log.info("ENFORCEMENT EXPOSURE ANALYSIS")
        log.info("=" * 80)

        test_cases = {}
        for result in self.results:
            if result.get("error"):
                continue
            test_id = result.get("test_id", "unknown")
            if test_id not in test_cases:
                test_cases[test_id] = []
            test_cases[test_id].append(result)

        for test_id, runs in test_cases.items():
            log.info(f"\n{test_id}:")
            unverified_count = sum(
                1 for r in runs
                if r.get("gate_behavior", {}).get("should_be_unverified")
            )
            blocked_count = sum(
                1 for r in runs
                if r.get("gate_behavior", {}).get("answer_blocked")
            )
            absence_detected = sum(
                1 for r in runs
                if r.get("detector_analysis", {}).get("is_absence_claim")
            )

            log.info(f"  Runs: {len(runs)}")
            log.info(f"  Absence claims detected: {absence_detected}/{len(runs)}")
            log.info(f"  Should be unverified: {unverified_count}/{len(runs)}")
            log.info(f"  Answer blocked: {blocked_count}/{len(runs)}")

            if unverified_count > 0:
                log.info(f"  → Enforcement exposure successful")
                if blocked_count > 0:
                    log.info(f"    Blocking observed: {blocked_count} cases")
                else:
                    log.info(f"    WARNING: Unverified but NOT blocked")

        log.info("\n" + "=" * 80)

        # Summary
        all_unverified = [
            r for r in self.results
            if not r.get("error") and r.get("gate_behavior", {}).get("should_be_unverified")
        ]
        all_blocked = [
            r for r in all_unverified
            if r.get("gate_behavior", {}).get("answer_blocked")
        ]

        log.info(f"\nOVERALL:")
        log.info(f"  Total unverified cases: {len(all_unverified)}")
        log.info(f"  Total blocked: {len(all_blocked)}")

        if len(all_unverified) > 0:
            if len(all_blocked) > 0:
                log.info(f"\n✓ ENFORCEMENT EXPOSURE CONFIRMED")
                log.info(f"  Gate blocks {len(all_blocked)}/{len(all_unverified)} unverified claims")
            else:
                log.info(f"\n⚠ ENFORCEMENT EXPOSURE INCOMPLETE")
                log.info(f"  Unverified claims detected but NOT blocked")
        else:
            log.info(f"\n✗ ENFORCEMENT EXPOSURE FAILED")
            log.info(f"  No unverified absence claims produced")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8A.3 Enforcement Exposure Test")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--repo", default="Deep-Guard-Frontend")
    parser.add_argument("--output", default=".")

    args = parser.parse_args()

    Path(args.output).mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(args.output)

    test = EnforcementExposureTest(api_url=args.api_url, repo=args.repo)
    test.run_enforcement_exposure_tests()
    test.save_results()
    test.analyze_enforcement_exposure()


if __name__ == "__main__":
    main()
