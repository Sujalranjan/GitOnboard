#!/usr/bin/env python3
"""
Phase 8A.4 Control-Flow Audit

Objective: Trace the exact code path from gate decision to answer release
for an unverified absence claim.

Uses NONEXISTENT_SYMBOL test case that produces:
  absence_claim = TRUE
  retrieval_performed = TRUE
  evidence_language = FALSE
  current_gate_result = TRUE (EXPECTED: FALSE)
"""

import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
import httpx

logging.basicConfig(
    level=logging.DEBUG,  # Capture all logs including diagnostic
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


class Phase8A4ControlFlowAudit:
    """Audit the control flow of the verification gate."""

    def __init__(self, api_url: str = "http://localhost:8000", repo: str = "Deep-Guard-Frontend"):
        self.api_url = api_url
        self.repo = repo
        self.client = httpx.Client(timeout=120.0)
        self.results = []

    def run_unverified_absence_case(self, run_num: int) -> dict:
        """Execute NONEXISTENT_SYMBOL case that should trigger gate."""
        query = "Is there a function called nonExistentFunction?"
        run_id = f"AUDIT_NONEXIST_SYM-{run_num}"

        try:
            log.info(f"[{run_id}] Starting control-flow audit...")
            log.info(f"[{run_id}] Query: {query}")

            endpoint = f"{self.api_url}/api/repos/{self.repo}/benchmark/pilot-compare"
            payload = {
                "question": query,
                "condition": "B",
                "run_number": run_num,
            }

            response = self.client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract full response
            answer = data.get("answer", "")
            tool_call_transcript = data.get("tool_call_transcript", [])
            tool_call_count = data.get("tool_call_count", 0)
            raw_logs = data.get("debug_logs", "")

            # Parse tools used
            tools_used = []
            for tc in tool_call_transcript:
                if isinstance(tc, dict):
                    tools_used.append(tc.get("tool", "unknown"))

            # Analyze answer
            answer_lower = answer.lower()

            # Detector check
            direct_negation = [
                "does not", "doesn't", "do not", "don't",
                "is not", "isn't", "was not", "wasn't",
                "are not", "aren't",
                "there is no", "there are no", "there's no",
                "no function", "no module", "no package",
            ]
            soft_negation = ["does not appear", "doesn't appear", "unable to find"]
            entity_context = ["function", "module", "repository", "code", "repo"]

            has_direct = any(p in answer_lower for p in direct_negation)
            has_soft = any(p in answer_lower for p in soft_negation)
            has_context = any(e in answer_lower for e in entity_context)
            is_absence_claim = has_direct or (has_soft and has_context)

            # Evidence check
            evidence_keywords = ["searched", "found", "no results", "no matches", "search results"]
            has_evidence = any(kw in answer_lower for kw in evidence_keywords)

            # Retrieval check
            retrieval_tools = {"search_repository", "read_file", "search_code", "get_symbol"}
            retrieval_performed = any(t in retrieval_tools for t in tools_used)

            result = {
                "run_id": run_id,
                "query": query,
                "run_number": run_num,

                "detector_analysis": {
                    "answer_text": answer[:200],
                    "is_absence_claim": is_absence_claim,
                    "has_direct_negation": has_direct,
                    "has_soft_negation": has_soft,
                    "has_context": has_context,
                },

                "execution": {
                    "tool_count": tool_call_count,
                    "tools_used": tools_used,
                    "retrieval_performed": retrieval_performed,
                },

                "gate_state": {
                    "is_absence_claim": is_absence_claim,
                    "retrieval_performed": retrieval_performed,
                    "has_evidence_language": has_evidence,
                    "should_gate_block": is_absence_claim and not has_evidence,
                },

                "answer": {
                    "released": len(answer) > 0,
                    "full_text": answer,
                },

                "timestamp": datetime.now().isoformat(),
            }

            log.info(f"[{run_id}] Analysis:")
            log.info(f"[{run_id}]   absence_claim={is_absence_claim}")
            log.info(f"[{run_id}]   retrieval_performed={retrieval_performed}")
            log.info(f"[{run_id}]   has_evidence_language={has_evidence}")
            log.info(f"[{run_id}]   should_gate_block={result['gate_state']['should_gate_block']}")
            log.info(f"[{run_id}]   answer_released={result['answer']['released']}")

            return result

        except Exception as e:
            log.error(f"[{run_id}] FAILED: {e}")
            return {
                "run_id": run_id,
                "error": str(e),
                "query": query,
            }

    def run_audit(self):
        """Run the control-flow audit."""
        log.info("=" * 80)
        log.info("PHASE 8A.4 CONTROL-FLOW AUDIT")
        log.info("=" * 80)
        log.info("Objective: Trace gate decision for unverified absence claim")
        log.info("Test case: NONEXISTENT_SYMBOL (absence=TRUE, evidence=FALSE)")
        log.info("=" * 80)

        for run_num in range(1, 3):
            result = self.run_unverified_absence_case(run_num)
            self.results.append(result)
            time.sleep(2.0)

        log.info("=" * 80)
        log.info(f"AUDIT COMPLETE - {len(self.results)} runs")
        log.info("=" * 80)

    def save_results(self):
        """Save audit results."""
        output_file = Path("PHASE8A4_CONTROL_FLOW_RAW_RESULTS.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        log.info(f"Results saved to {output_file}")

    def analyze_gate_behavior(self):
        """Analyze gate behavior from results."""
        log.info("\n" + "=" * 80)
        log.info("GATE BEHAVIOR ANALYSIS")
        log.info("=" * 80)

        for result in self.results:
            if result.get("error"):
                log.info(f"\n{result['run_id']}: ERROR")
                continue

            run_id = result["run_id"]
            gate_state = result.get("gate_state", {})
            answer = result.get("answer", {})

            log.info(f"\n{run_id}:")
            log.info(f"  Detector state:")
            log.info(f"    is_absence_claim: {gate_state.get('is_absence_claim')}")
            log.info(f"    retrieval_performed: {gate_state.get('retrieval_performed')}")
            log.info(f"    has_evidence_language: {gate_state.get('has_evidence_language')}")
            log.info(f"  Expected gate behavior:")
            log.info(f"    should_gate_block: {gate_state.get('should_gate_block')}")
            log.info(f"  Actual gate behavior:")
            log.info(f"    answer_released: {answer.get('released')}")

            # Check for the control-flow defect
            if (gate_state.get("is_absence_claim") and
                gate_state.get("retrieval_performed") and
                not gate_state.get("has_evidence_language") and
                answer.get("released")):
                log.warning(f"\n  ⚠ CONTROL-FLOW DEFECT OBSERVED")
                log.warning(f"    absence=TRUE, retrieval=TRUE, evidence=FALSE, but answer released")
                log.warning(f"    This indicates gate only checks retrieval, not evidence language")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8A.4 Control-Flow Audit")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--repo", default="Deep-Guard-Frontend")
    parser.add_argument("--output", default=".")

    args = parser.parse_args()

    Path(args.output).mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(args.output)

    audit = Phase8A4ControlFlowAudit(api_url=args.api_url, repo=args.repo)
    audit.run_audit()
    audit.save_results()
    audit.analyze_gate_behavior()

    log.info("\nControl-flow audit complete. Check logs above for diagnostic output.")


if __name__ == "__main__":
    main()
