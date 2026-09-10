#!/usr/bin/env python3
"""
Phase 8A.3 Detector Validation

Objective: Validate improved absence-claim detector against comprehensive test matrix.

Test categories:
1. Direct negations (e.g., "does not", "there is no")
2. Soft negations (e.g., "does not appear", "seems not to")
3. Search-qualified negations (e.g., "based on search results, no results found")
4. Positive claims (must NOT be flagged as absence)
5. Non-claims and generic statements
"""

import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class DetectorValidator:
    """Validate improved absence-claim detector."""

    def __init__(self):
        self.test_cases = []
        self.results = []

    def _is_absence_claim(self, answer: str) -> bool:
        """
        Improved absence claim detector - matching rim_qa_loop.py implementation.
        """
        answer_lower = answer.lower()

        # Direct negation patterns (primary)
        direct_negation = [
            "does not",
            "doesn't",
            "do not",
            "don't",
            "is not",
            "isn't",
            "was not",
            "wasn't",
            "are not",
            "aren't",
            "no function",
            "no module",
            "no package",
            "no component",
            "no service",
            "no feature",
            "no implementation",
            "no code",
            "there is no",
            "there are no",
            "there's no",
        ]

        # Soft/qualified negation (secondary)
        soft_negation = [
            "does not appear",
            "doesn't appear",
            "appears not",
            "appears to not",
            "doesn't seem",
            "does not seem",
            "seems not",
            "unable to find",
            "cannot find",
            "could not find",
            "couldn't find",
            "found no",
            "no evidence",
            "no mention",
            "no instances",
            "no references",
            "not found",
            "not present",
            "not implemented",
            "not detected",
            "no results",
        ]

        # Entity context (broadened)
        entity_context = [
            "function",
            "module",
            "package",
            "library",
            "component",
            "service",
            "feature",
            "class",
            "interface",
            "method",
            "implementation",
            "pattern",
            "dependency",
            "tool",
            "framework",
            "redis",
            "database",
            "cache",
            "authentication",
            "reset",
            "recovery",
        ]

        repo_context = [
            "repository",
            "codebase",
            "project",
            "code",
            "repo",
            "this repo",
            "this project",
        ]

        # Strategy: Detect absence if:
        # 1. Direct negation is present
        # 2. OR soft negation + entity/repo context
        has_direct = any(p in answer_lower for p in direct_negation)

        has_soft = any(p in answer_lower for p in soft_negation)
        has_context = (
            any(e in answer_lower for e in entity_context) or
            any(r in answer_lower for r in repo_context)
        )

        return has_direct or (has_soft and has_context)

    def add_test_case(self, category: str, claim_text: str, expected_is_absence: bool):
        """Add test case to matrix."""
        self.test_cases.append({
            "category": category,
            "claim_text": claim_text,
            "expected_is_absence": expected_is_absence,
        })

    def build_test_matrix(self):
        """Build comprehensive test matrix."""
        # Direct negations - SHOULD be flagged as absence
        self.add_test_case(
            "direct_negation_basic",
            "The repository does not use Redis for authentication.",
            True
        )
        self.add_test_case(
            "direct_negation_basic",
            "This code doesn't implement password reset functionality.",
            True
        )
        self.add_test_case(
            "direct_negation_basic",
            "There is no function called fooBar in the codebase.",
            True
        )
        self.add_test_case(
            "direct_negation_basic",
            "There are no instances of this pattern in the project.",
            True
        )
        self.add_test_case(
            "direct_negation_basic",
            "The service is not implemented in this repository.",
            True
        )

        # Soft negations - SHOULD be flagged if they have entity/repo context
        self.add_test_case(
            "soft_negation",
            "The repository does not appear to use Redis.",
            True
        )
        self.add_test_case(
            "soft_negation",
            "This codebase doesn't seem to implement JWT authentication.",
            True
        )
        self.add_test_case(
            "soft_negation",
            "It appears not to be present in the project.",
            True
        )
        self.add_test_case(
            "soft_negation",
            "Unable to find any references to this module in the repository.",
            True
        )
        self.add_test_case(
            "soft_negation",
            "Could not find evidence of this pattern in the codebase.",
            True
        )

        # Search-qualified negations - SHOULD be flagged
        self.add_test_case(
            "search_qualified",
            "Based on search results, no evidence of Redis authentication in the repository.",
            True
        )
        self.add_test_case(
            "search_qualified",
            "No results found for password reset functionality in the code.",
            True
        )
        self.add_test_case(
            "search_qualified",
            "Found no instances of fooBar in the repository.",
            True
        )
        self.add_test_case(
            "search_qualified",
            "After searching the project, no implementation of this feature was detected.",
            True
        )
        self.add_test_case(
            "search_qualified",
            "Search results show no mention of Redis in the authentication module.",
            True
        )

        # Positive claims - SHOULD NOT be flagged as absence
        self.add_test_case(
            "positive_claim",
            "Yes, the repository uses Redis for authentication.",
            False
        )
        self.add_test_case(
            "positive_claim",
            "The codebase implements password reset functionality.",
            False
        )
        self.add_test_case(
            "positive_claim",
            "There is a function called fooBar in the project.",
            False
        )
        self.add_test_case(
            "positive_claim",
            "This pattern is implemented and used throughout the repository.",
            False
        )
        self.add_test_case(
            "positive_claim",
            "The service is fully implemented in the codebase.",
            False
        )

        # Edge cases - mixed content
        self.add_test_case(
            "mixed_content",
            "Redis is not used, but the repository does implement caching.",
            True  # Contains "does not" + "repository"
        )
        self.add_test_case(
            "mixed_content",
            "The project doesn't use Redis; however, it does implement PostgreSQL caching.",
            True  # Contains "doesn't use" + "project"
        )

        # Non-claims - generic statements - SHOULD NOT be flagged
        self.add_test_case(
            "non_claim",
            "The repository has several modules.",
            False
        )
        self.add_test_case(
            "non_claim",
            "This codebase is written in JavaScript.",
            False
        )
        self.add_test_case(
            "non_claim",
            "The project contains 50 files.",
            False
        )
        self.add_test_case(
            "non_claim",
            "Search results returned multiple matches.",
            False
        )

    def run_validation(self):
        """Run detector against all test cases."""
        log.info("=" * 80)
        log.info("PHASE 8A.3 DETECTOR VALIDATION")
        log.info("=" * 80)
        log.info(f"Test cases: {len(self.test_cases)}")
        log.info("=" * 80)

        for idx, test_case in enumerate(self.test_cases, 1):
            category = test_case["category"]
            claim_text = test_case["claim_text"]
            expected = test_case["expected_is_absence"]

            # Run detector
            detected = self._is_absence_claim(claim_text)

            # Check result
            is_correct = detected == expected
            verdict = "✓ PASS" if is_correct else "✗ FAIL"

            result = {
                "test_number": idx,
                "category": category,
                "claim_text": claim_text,
                "expected_is_absence": expected,
                "detected_is_absence": detected,
                "is_correct": is_correct,
                "verdict": verdict,
                "timestamp": datetime.now().isoformat(),
            }

            self.results.append(result)

            log.info(f"\n[TEST {idx}] {category.upper()}")
            log.info(f"  Claim: {claim_text[:70]}...")
            log.info(f"  Expected: {expected}, Detected: {detected}")
            log.info(f"  {verdict}")

        log.info("\n" + "=" * 80)
        log.info("VALIDATION SUMMARY")
        log.info("=" * 80)

        # Summary by category
        categories = {}
        for result in self.results:
            cat = result["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "passed": 0}
            categories[cat]["total"] += 1
            if result["is_correct"]:
                categories[cat]["passed"] += 1

        total_tests = len(self.results)
        total_passed = sum(1 for r in self.results if r["is_correct"])
        total_failed = total_tests - total_passed
        success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

        log.info(f"\nOverall: {total_passed}/{total_tests} passed ({success_rate:.1f}%)")
        log.info(f"Failures: {total_failed}")

        log.info("\nBy category:")
        for cat_name in sorted(categories.keys()):
            cat_stats = categories[cat_name]
            cat_rate = (cat_stats["passed"] / cat_stats["total"] * 100) if cat_stats["total"] > 0 else 0
            log.info(f"  {cat_name}: {cat_stats['passed']}/{cat_stats['total']} ({cat_rate:.1f}%)")

        # Report failures
        failures = [r for r in self.results if not r["is_correct"]]
        if failures:
            log.info(f"\n✗ FAILURES ({len(failures)}):")
            for failure in failures:
                log.info(f"  [{failure['category']}] Expected {failure['expected_is_absence']}, got {failure['detected_is_absence']}")
                log.info(f"    '{failure['claim_text'][:80]}'")
        else:
            log.info("\n✓ ALL TESTS PASSED")

        return total_passed == total_tests

    def save_results(self):
        """Save validation results."""
        output_file = Path("PHASE8A3_DETECTOR_RAW_RESULTS.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        log.info(f"\nValidation results saved to {output_file}")
        return output_file


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8A.3 Detector Validation")
    parser.add_argument("--output", default=".")
    args = parser.parse_args()

    Path(args.output).mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(args.output)

    # Run validation
    validator = DetectorValidator()
    validator.build_test_matrix()
    all_passed = validator.run_validation()
    validator.save_results()

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
