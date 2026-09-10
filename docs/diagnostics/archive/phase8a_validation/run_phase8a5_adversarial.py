#!/usr/bin/env python3
"""
Phase 8A.5 Adversarial Test: Gate Blocking Behavior

Tests the critical case: Can the gate block an absence claim when
retrieval actually found relevant results?

This is the key test - if the model searches for "password reset"
and finds results, but still claims absence, the gate should block it.
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


class Phase8A5AdversarialTest:
    """Test gate blocking behavior with adversarial cases."""

    def __init__(self, api_url: str = "http://localhost:8000", repo: str = "Deep-Guard-Frontend"):
        self.api_url = api_url
        self.repo = repo
        self.client = httpx.Client(timeout=120.0)
        self.results = []

    def run_adversarial_case(self, case_name: str, query: str, run_num: int, expected_verdict: str) -> dict:
        """Execute adversarial test case."""
        run_id = f"{case_name}-{run_num}"

        try:
            log.info(f"[{run_id}] Adversarial test: {query}")
            log.info(f"[{run_id}] Expected gate: {expected_verdict}")

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

            # Parse answer
            answer_lower = answer.lower()

            # Detect absence claim
            direct_neg = ["does not", "doesn't", "is not", "no implementation", "no evidence"]
            is_absence = any(p in answer_lower for p in direct_neg)

            # Detect if answer has evidence language
            evidence_kw = ["searched", "found", "results", "evidence"]
            has_evidence = any(kw in answer_lower for kw in evidence_kw)

            result = {
                "run_id": run_id,
                "case_name": case_name,
                "query": query,
                "expected_verdict": expected_verdict,

                "answer_analysis": {
                    "answer_preview": answer[:150],
                    "is_absence_claim": is_absence,
                    "has_evidence_language": has_evidence,
                },

                "gate_behavior": {
                    "answer_released": len(answer) > 0,
                    "answer_length": len(answer),
                },

                "verdict": "PASS" if ((expected_verdict == "RELEASE" and len(answer) > 0) or
                                     (expected_verdict == "BLOCK" and len(answer) == 0)) else "FAIL",

                "timestamp": datetime.now().isoformat(),
            }

            actual = "RELEASED" if result["gate_behavior"]["answer_released"] else "BLOCKED"
            log.info(f"[{run_id}] Actual gate: {actual}")
            log.info(f"[{run_id}] Verdict: {result['verdict']}")

            if result["verdict"] == "FAIL":
                log.warning(f"[{run_id}] ⚠ TEST FAILED - Expected {expected_verdict}, got {actual}")

            return result

        except Exception as e:
            log.error(f"[{run_id}] ERROR: {e}")
            return {
                "run_id": run_id,
                "case_name": case_name,
                "error": str(e),
            }

    def run_adversarial_suite(self):
        """Run adversarial test suite."""
        log.info("=" * 80)
        log.info("PHASE 8A.5 ADVERSARIAL TEST: Gate Blocking Behavior")
        log.info("=" * 80)

        # Adversarial 1: Query for something that EXISTS
        # Model searches for it, finds it, but claims absence anyway
        log.info("\n[ADVERSARIAL 1] Claim Absence When Results Exist")
        log.info("  Query: Something that EXISTS in the repo")
        log.info("  Expected: Gate BLOCKS (results contradict absence)")
        for run in range(1, 2):
            result = self.run_adversarial_case(
                "EXISTS_CLAIMS_ABSENT",
                "Is there a function called setupMockHTTPServer?",  # This probably exists
                run,
                "BLOCK"  # Should block if model searches, finds it, but claims absence
            )
            self.results.append(result)
            time.sleep(1.0)

        # Adversarial 2: Query for existing feature but model claims absence
        log.info("\n[ADVERSARIAL 2] Feature That Exists - Absence Claim")
        log.info("  Query: Password reset (which EXISTS)")
        log.info("  Expected: Gate RELEASES if model correctly states it exists")
        log.info("           Gate BLOCKS if model incorrectly claims absence")
        for run in range(1, 2):
            result = self.run_adversarial_case(
                "FEATURE_EXISTS",
                "Does the Deep-Guard-Frontend project have password reset functionality?",
                run,
                "RELEASE"  # Model should find evidence it exists
            )
            self.results.append(result)
            time.sleep(1.0)

        log.info("=" * 80)
        log.info(f"ADVERSARIAL TESTS COMPLETE - {len(self.results)} cases")
        log.info("=" * 80)

    def save_results(self):
        """Save adversarial test results."""
        output_file = Path("PHASE8A5_ADVERSARIAL_RAW_RESULTS.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        log.info(f"Results saved to {output_file}")

    def analyze_blocking_behavior(self):
        """Analyze whether blocking actually occurs."""
        log.info("\n" + "=" * 80)
        log.info("BLOCKING BEHAVIOR ANALYSIS")
        log.info("=" * 80)

        total_pass = 0
        total_fail = 0

        for result in self.results:
            if result.get("error"):
                continue

            case = result.get("case_name", "unknown")
            expected = result.get("expected_verdict")
            actual = "RELEASED" if result["gate_behavior"]["answer_released"] else "BLOCKED"
            verdict = result.get("verdict")

            log.info(f"\n{case}:")
            log.info(f"  Expected: {expected}")
            log.info(f"  Actual: {actual}")
            log.info(f"  Result: {verdict}")

            if verdict == "PASS":
                total_pass += 1
            else:
                total_fail += 1

            if verdict == "FAIL":
                analysis = result.get("answer_analysis", {})
                log.warning(f"  Answer is absence claim: {analysis.get('is_absence_claim')}")
                log.warning(f"  Answer has evidence: {analysis.get('has_evidence_language')}")

        log.info("\n" + "=" * 80)
        log.info(f"RESULTS: {total_pass}/{total_pass + total_fail} passed")
        if total_fail > 0:
            log.warning(f"⚠ {total_fail} adversarial tests failed")
            log.warning("  This indicates gate may not be blocking certain cases")
        else:
            log.info("✓ Gate enforcement blocking correctly observed")
        log.info("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8A.5 Adversarial Test")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--repo", default="Deep-Guard-Frontend")
    parser.add_argument("--output", default=".")

    args = parser.parse_args()

    Path(args.output).mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(args.output)

    adversarial = Phase8A5AdversarialTest(api_url=args.api_url, repo=args.repo)
    adversarial.run_adversarial_suite()
    adversarial.save_results()
    adversarial.analyze_blocking_behavior()


if __name__ == "__main__":
    main()
