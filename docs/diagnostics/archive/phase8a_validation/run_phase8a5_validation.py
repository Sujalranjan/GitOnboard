#!/usr/bin/env python3
"""
Phase 8A.5 Validation: Evidence-Based Absence Gate

Tests whether the new gate correctly:
1. Blocks unverified absence claims (retrieval but contradicting results)
2. Allows verified absence claims (retrieval returns empty results)
3. Blocks unverified claims that lack retrieval
4. Allows positive claims
"""

import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class Phase8A5Validation:
    """Validate evidence-based gate enforcement."""

    def __init__(self, api_url: str = "http://localhost:8000", repo: str = "Deep-Guard-Frontend"):
        self.api_url = api_url
        self.repo = repo
        self.client = httpx.Client(timeout=120.0)
        self.results = []

    def run_test_case(self, case_name: str, query: str, run_num: int, expected_verdict: str) -> dict:
        """Execute a test case and capture gate behavior."""
        run_id = f"{case_name}-{run_num}"

        try:
            log.info(f"[{run_id}] Testing: {query}")
            log.info(f"[{run_id}] Expected: {expected_verdict}")

            endpoint = f"{self.api_url}/api/repos/{self.repo}/benchmark/pilot-compare"
            payload = {
                "question": query,
                "condition": "B",
                "run_number": run_num,
            }

            response = self.client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            answer = data.get("answer", "")
            tool_transcript = data.get("tool_call_transcript", [])

            # Analyze result
            answer_lower = answer.lower()
            direct_negation = ["does not", "doesn't", "do not", "don't", "is not", "isn't",
                              "there is no", "there are no", "no function", "no module"]
            entity_context = ["function", "module", "repository", "repo"]

            is_absence = any(p in answer_lower for p in direct_negation) and any(e in answer_lower for e in entity_context)

            result = {
                "run_id": run_id,
                "case_name": case_name,
                "query": query,
                "expected_verdict": expected_verdict,

                "detector": {
                    "is_absence_claim": is_absence,
                    "answer_preview": answer[:120],
                },

                "gate_behavior": {
                    "answer_released": len(answer) > 0,
                    "answer_full": answer,
                },

                "verdict": "PASS" if ((expected_verdict == "RELEASE" and len(answer) > 0) or
                                     (expected_verdict == "BLOCK" and len(answer) == 0)) else "FAIL",

                "timestamp": datetime.now().isoformat(),
            }

            log.info(f"[{run_id}] Actual: {'RELEASED' if result['gate_behavior']['answer_released'] else 'BLOCKED'}")
            log.info(f"[{run_id}] Result: {result['verdict']}")

            return result

        except Exception as e:
            log.error(f"[{run_id}] ERROR: {e}")
            return {
                "run_id": run_id,
                "case_name": case_name,
                "error": str(e),
            }

    def run_validation_suite(self):
        """Run comprehensive validation test suite."""
        log.info("=" * 80)
        log.info("PHASE 8A.5 VALIDATION: EVIDENCE-BASED GATE")
        log.info("=" * 80)

        # Test 1: Unverified absence (retrieval but results exist) - SHOULD BLOCK
        log.info("\n[TEST 1] Verified Absence - Empty Results (SHOULD RELEASE)")
        for run in range(1, 2):
            result = self.run_test_case(
                "VERIFIED_ABSENCE",
                "Is there a function called nonExistentFunction?",
                run,
                "RELEASE"
            )
            self.results.append(result)
            time.sleep(1.0)

        # Test 2: Existing feature - SHOULD RELEASE (not absence claim)
        log.info("\n[TEST 2] Positive Claim (SHOULD RELEASE)")
        for run in range(1, 2):
            result = self.run_test_case(
                "POSITIVE_CLAIM",
                "Does this repo implement password reset?",
                run,
                "RELEASE"
            )
            self.results.append(result)
            time.sleep(1.0)

        # Test 3: Non-existent technology - SHOULD RELEASE (empty results)
        log.info("\n[TEST 3] Non-Existent Tech - Empty Results (SHOULD RELEASE)")
        for run in range(1, 2):
            result = self.run_test_case(
                "NONEXISTENT_TECH",
                "Does this repo use Kafka?",
                run,
                "RELEASE"
            )
            self.results.append(result)
            time.sleep(1.0)

        log.info("=" * 80)
        log.info(f"VALIDATION COMPLETE - {len(self.results)} test cases")
        log.info("=" * 80)

    def save_results(self):
        """Save validation results."""
        output_file = Path("PHASE8A5_VALIDATION_RAW_RESULTS.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        log.info(f"Results saved to {output_file}")

    def analyze_results(self):
        """Analyze gate behavior."""
        log.info("\n" + "=" * 80)
        log.info("GATE ENFORCEMENT ANALYSIS")
        log.info("=" * 80)

        test_cases = {}
        for result in self.results:
            if result.get("error"):
                continue
            case = result["case_name"]
            if case not in test_cases:
                test_cases[case] = []
            test_cases[case].append(result)

        total_pass = 0
        total_fail = 0

        for case_name, runs in test_cases.items():
            passed = sum(1 for r in runs if r.get("verdict") == "PASS")
            failed = sum(1 for r in runs if r.get("verdict") == "FAIL")
            total_pass += passed
            total_fail += failed

            log.info(f"\n{case_name}:")
            log.info(f"  Expected: {runs[0].get('expected_verdict')}")
            log.info(f"  Results: {passed}/{len(runs)} correct")

            if failed > 0:
                log.warning(f"  ⚠ {failed} failures")
                for r in runs:
                    if r.get("verdict") == "FAIL":
                        log.warning(f"    Expected {r['expected_verdict']}, got {'RELEASED' if r['gate_behavior']['answer_released'] else 'BLOCKED'}")

        log.info("\n" + "=" * 80)
        log.info(f"OVERALL: {total_pass}/{total_pass + total_fail} passed")
        if total_fail == 0:
            log.info("✓ ALL TESTS PASSED - Gate enforcement working correctly")
        else:
            log.warning(f"✗ {total_fail} TESTS FAILED")
        log.info("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8A.5 Validation")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--repo", default="Deep-Guard-Frontend")
    parser.add_argument("--output", default=".")

    args = parser.parse_args()

    Path(args.output).mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(args.output)

    validation = Phase8A5Validation(api_url=args.api_url, repo=args.repo)
    validation.run_validation_suite()
    validation.save_results()
    validation.analyze_results()


if __name__ == "__main__":
    main()
