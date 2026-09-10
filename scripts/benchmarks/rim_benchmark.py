#!/usr/bin/env python3
"""
RIM Comparison Benchmark Harness
Runs 10 mixed questions against WITHOUT RIM and WITH RIM endpoints.
Records: tool calls, RIM usage, files read, tokens, latency, redundancy.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Dict, Any

# Configuration
REPO_NAME = "Deep-Guard-Integrated-Backend"
BACKEND_URL = "http://localhost:8000"
COMPARISON_ENDPOINT = f"{BACKEND_URL}/api/repos/{REPO_NAME}/rim-comparison/compare-stream"

# Benchmark questions
BENCHMARK_QUESTIONS = [
    # Control group (source-retrieval, should NOT use RIM)
    {
        "id": 1,
        "question": "Which authentication mechanism does this repository use?",
        "category": "control",
        "expected_rim_calls": 0,
    },
    {
        "id": 2,
        "question": "How does `detect_deepfake` process an image and produce its detection result?",
        "category": "control",
        "expected_rim_calls": 0,
    },
    {
        "id": 3,
        "question": "What happens when a user logs in with email and password?",
        "category": "control",
        "expected_rim_calls": 0,
    },
    # Direct RIM tests (should use query_rim)
    {
        "id": 4,
        "question": "What calls `detect_deepfake`?",
        "category": "direct_rim",
        "expected_rim_calls": 1,
    },
    {
        "id": 5,
        "question": "Which components use or depend on `authenticateToken`?",
        "category": "direct_rim",
        "expected_rim_calls": 1,
    },
    {
        "id": 6,
        "question": "Which routes are connected to the deepfake detection functionality, and how do they reach the detection logic?",
        "category": "direct_rim",
        "expected_rim_calls": 1,
    },
    {
        "id": 7,
        "question": "What modules or files import `authenticateToken`?",
        "category": "direct_rim",
        "expected_rim_calls": 1,
    },
    {
        "id": 8,
        "question": "How is the authentication middleware connected to the protected routes?",
        "category": "direct_rim",
        "expected_rim_calls": 1,
    },
    # Multi-hop / architectural (harder RIM tests)
    {
        "id": 9,
        "question": "What components are involved between a deepfake detection API request and `detect_deepfake`?",
        "category": "multi_hop",
        "expected_rim_calls": 2,
    },
    {
        "id": 10,
        "question": "What are the main components responsible for authentication, and how are they connected?",
        "category": "multi_hop",
        "expected_rim_calls": 2,
    },
]


@dataclass
class ToolCallMetrics:
    """Metrics from a single side (WITH RIM or WITHOUT RIM)."""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    total_tool_calls: int = 0
    rim_calls: int = 0
    files_read: int = 0
    symbols_read: int = 0
    files_searched: int = 0
    symbols_searched: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    answer_length: int = 0
    answer: str = ""  # Full answer text
    stop_reason: str = ""

    def has_redundant_calls(self) -> bool:
        """Check if there are repeated identical tool calls."""
        call_hashes = {}
        for call in self.tool_calls:
            call_key = (call.get("tool_name"), json.dumps(call.get("arguments", {}), sort_keys=True))
            call_hashes[call_key] = call_hashes.get(call_key, 0) + 1
        return any(count > 1 for count in call_hashes.values())

    def redundant_call_count(self) -> int:
        """Count how many redundant calls were made."""
        call_hashes = {}
        for call in self.tool_calls:
            call_key = (call.get("tool_name"), json.dumps(call.get("arguments", {}), sort_keys=True))
            call_hashes[call_key] = call_hashes.get(call_key, 0) + 1
        return sum(count - 1 for count in call_hashes.values())


@dataclass
class BenchmarkResult:
    """Result for one question."""
    question_id: int
    question: str
    category: str
    expected_rim_calls: int
    without_rim: ToolCallMetrics = field(default_factory=ToolCallMetrics)
    with_rim: ToolCallMetrics = field(default_factory=ToolCallMetrics)

    def rim_usage_matches_expectation(self) -> bool:
        """Check if WITH RIM's usage matches expected behavior."""
        if self.category == "control":
            return self.with_rim.rim_calls == self.expected_rim_calls
        else:
            # For RIM questions, we expect at least the expected minimum
            return self.with_rim.rim_calls >= self.expected_rim_calls


def stream_comparison(question: str) -> tuple:
    """Stream comparison results and extract metrics."""
    without_rim = ToolCallMetrics()
    with_rim = ToolCallMetrics()
    received_with_rim_complete = False

    try:
        req = urllib.request.Request(
            COMPARISON_ENDPOINT,
            data=json.dumps({"question": question}).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=600) as response:  # 10-minute timeout
            if response.status != 200:
                print(f"  ❌ HTTP {response.status}")
                return without_rim, with_rim

            # Keep reading until we get with_rim_complete or error
            while not received_with_rim_complete:
                line = response.readline().decode('utf-8').strip()

                # Empty line = keep waiting (SSE can have empty lines)
                if not line:
                    continue

                if not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type")

                # WITHOUT RIM complete
                if event_type == "without_rim_complete" and data.get("without_rim"):
                    side = data["without_rim"]
                    without_rim.answer = side.get("answer", "")
                    without_rim.answer_length = len(without_rim.answer)
                    without_rim.stop_reason = side.get("stop_reason", "")
                    without_rim.prompt_tokens = side.get("llm_efficiency_metrics", {}).get("actual_prompt_tokens", 0)
                    without_rim.completion_tokens = side.get("llm_efficiency_metrics", {}).get("actual_completion_tokens", 0)
                    without_rim.total_tokens = side.get("llm_efficiency_metrics", {}).get("actual_total_tokens", 0)
                    without_rim.latency_ms = side.get("llm_efficiency_metrics", {}).get("total_latency_ms", 0)

                    # Extract tool calls from transcript
                    for call in side.get("tool_call_transcript", []):
                        without_rim.tool_calls.append(call)
                        without_rim.total_tool_calls += 1

                    # Extract retrieval metrics
                    retr = side.get("retrieval_metrics", {})
                    without_rim.files_read = retr.get("files_retrieved", 0)
                    without_rim.symbols_read = retr.get("symbols_retrieved", 0)
                    without_rim.rim_calls = retr.get("rim_entities_accessed_count", 0)

                # WITH RIM complete (final event - stop here)
                elif event_type == "with_rim_complete" and data.get("with_rim"):
                    side = data["with_rim"]
                    with_rim.answer = side.get("answer", "")
                    with_rim.answer_length = len(with_rim.answer)
                    with_rim.stop_reason = side.get("stop_reason", "")
                    with_rim.prompt_tokens = side.get("llm_efficiency_metrics", {}).get("actual_prompt_tokens", 0)
                    with_rim.completion_tokens = side.get("llm_efficiency_metrics", {}).get("actual_completion_tokens", 0)
                    with_rim.total_tokens = side.get("llm_efficiency_metrics", {}).get("actual_total_tokens", 0)
                    with_rim.latency_ms = side.get("llm_efficiency_metrics", {}).get("total_latency_ms", 0)

                    # Extract tool calls from transcript
                    for call in side.get("tool_call_transcript", []):
                        with_rim.tool_calls.append(call)
                        with_rim.total_tool_calls += 1

                    # Extract retrieval metrics
                    retr = side.get("retrieval_metrics", {})
                    with_rim.files_read = retr.get("files_retrieved", 0)
                    with_rim.symbols_read = retr.get("symbols_retrieved", 0)
                    with_rim.rim_calls = retr.get("rim_entities_accessed_count", 0)

                    # Mark complete and exit loop
                    received_with_rim_complete = True

                # Error event
                elif event_type == "error":
                    print(f"  ⚠️  Endpoint error: {data.get('content')}")
                    received_with_rim_complete = True  # Exit loop on error

    except urllib.error.URLError as e:
        print(f"  ❌ Connection error: {e}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    return without_rim, with_rim


def run_benchmark():
    """Run all benchmark questions."""
    print(f"\n🧪 RIM Benchmark - {REPO_NAME}")
    print(f"   Backend: {BACKEND_URL}")
    print(f"   Endpoint: {COMPARISON_ENDPOINT}\n")

    results: List[BenchmarkResult] = []

    for q in BENCHMARK_QUESTIONS:
        question_id = q["id"]
        question = q["question"]
        category = q["category"]
        expected_rim = q["expected_rim_calls"]

        print(f"Q{question_id} [{category:10s}] {question[:60]}...")
        start = time.perf_counter()

        without_rim, with_rim = stream_comparison(question)

        elapsed = (time.perf_counter() - start) * 1000
        print(f"   ✓ WITHOUT RIM: {without_rim.total_tool_calls:2d} tools, {without_rim.rim_calls:2d} RIM, {without_rim.total_tokens:4d} tokens ({elapsed:6.0f}ms)")
        print(f"   ✓ WITH RIM:    {with_rim.total_tool_calls:2d} tools, {with_rim.rim_calls:2d} RIM, {with_rim.total_tokens:4d} tokens")

        result = BenchmarkResult(
            question_id=question_id,
            question=question,
            category=category,
            expected_rim_calls=expected_rim,
            without_rim=without_rim,
            with_rim=with_rim,
        )
        results.append(result)

    print("\n" + "=" * 130)
    print("RESULTS SUMMARY")
    print("=" * 130)

    # Format as table
    print(
        f"{'Q':>2} | {'Category':<10} | {'WITHOUT RIM':<45} | {'WITH RIM':<45} | {'Verdict':<12}"
    )
    print(
        f"    | {'':10} | {'Tools':>5} {'RIM':>3} {'Tokens':>8} {'Redundant':>9} {'Answer':>8} | {'Tools':>5} {'RIM':>3} {'Tokens':>8} {'Redundant':>9} {'Answer':>8} | "
    )
    print("-" * 130)

    for r in results:
        wr = r.without_rim
        ir = r.with_rim

        # Verdict
        verdict = "✅" if r.rim_usage_matches_expectation() else "❌"
        if ir.has_redundant_calls():
            verdict += " REDUN"

        print(
            f"{r.question_id:2d} | {r.category:<10} | "
            f"{wr.total_tool_calls:>5} {wr.rim_calls:>3} {wr.total_tokens:>8} {wr.redundant_call_count():>9} {wr.answer_length:>8} | "
            f"{ir.total_tool_calls:>5} {ir.rim_calls:>3} {ir.total_tokens:>8} {ir.redundant_call_count():>9} {ir.answer_length:>8} | "
            f"{verdict:<12}"
        )

    # Group analysis
    print("\n" + "=" * 130)
    print("CATEGORY ANALYSIS")
    print("=" * 130)

    control = [r for r in results if r.category == "control"]
    direct = [r for r in results if r.category == "direct_rim"]
    multi = [r for r in results if r.category == "multi_hop"]

    def analyze_group(name: str, group: List[BenchmarkResult]):
        if not group:
            return
        print(f"\n{name}:")
        print(f"  Expected RIM usage: {group[0].expected_rim_calls}")
        avg_rim_without = sum(r.without_rim.rim_calls for r in group) / len(group)
        avg_rim_with = sum(r.with_rim.rim_calls for r in group) / len(group)
        avg_tokens_without = sum(r.without_rim.total_tokens for r in group) / len(group)
        avg_tokens_with = sum(r.with_rim.total_tokens for r in group) / len(group)
        avg_tools_without = sum(r.without_rim.total_tool_calls for r in group) / len(group)
        avg_tools_with = sum(r.with_rim.total_tool_calls for r in group) / len(group)

        print(f"  WITHOUT RIM: avg {avg_tools_without:.1f} tools, {avg_rim_without:.1f} RIM calls, {avg_tokens_without:.0f} tokens")
        print(f"  WITH RIM:    avg {avg_tools_with:.1f} tools, {avg_rim_with:.1f} RIM calls, {avg_tokens_with:.0f} tokens")

        correct = sum(1 for r in group if r.rim_usage_matches_expectation())
        print(f"  Correct behavior: {correct}/{len(group)} questions")

    analyze_group("🎛️  Control (no RIM expected)", control)
    analyze_group("🔗 Direct RIM (relationship expected)", direct)
    analyze_group("🏗️  Multi-hop (architectural, RIM beneficial)", multi)

    print("\n" + "=" * 130)
    print("SAVING DETAILED RESULTS...")
    print("=" * 130)

    # Save detailed results to JSON
    output_file = "rim_benchmark_results.json"
    detailed_results = []

    for r in results:
        detailed_results.append({
            "question_id": r.question_id,
            "question": r.question,
            "category": r.category,
            "expected_rim_calls": r.expected_rim_calls,
            "verdict": "✅" if r.rim_usage_matches_expectation() else "❌",
            "without_rim": {
                "answer": r.without_rim.answer,
                "answer_length": r.without_rim.answer_length,
                "total_tool_calls": r.without_rim.total_tool_calls,
                "tool_calls": r.without_rim.tool_calls,
                "rim_calls": r.without_rim.rim_calls,
                "files_read": r.without_rim.files_read,
                "prompt_tokens": r.without_rim.prompt_tokens,
                "completion_tokens": r.without_rim.completion_tokens,
                "total_tokens": r.without_rim.total_tokens,
                "latency_ms": r.without_rim.latency_ms,
                "redundant_calls": r.without_rim.redundant_call_count(),
                "stop_reason": r.without_rim.stop_reason,
            },
            "with_rim": {
                "answer": r.with_rim.answer,
                "answer_length": r.with_rim.answer_length,
                "total_tool_calls": r.with_rim.total_tool_calls,
                "tool_calls": r.with_rim.tool_calls,
                "rim_calls": r.with_rim.rim_calls,
                "files_read": r.with_rim.files_read,
                "prompt_tokens": r.with_rim.prompt_tokens,
                "completion_tokens": r.with_rim.completion_tokens,
                "total_tokens": r.with_rim.total_tokens,
                "latency_ms": r.with_rim.latency_ms,
                "redundant_calls": r.with_rim.redundant_call_count(),
                "stop_reason": r.with_rim.stop_reason,
            },
        })

    with open(output_file, "w") as f:
        json.dump(detailed_results, f, indent=2)

    print(f"\n✓ Detailed results saved to: {output_file}")
    print(f"  - Full answers for each question")
    print(f"  - Complete tool call transcripts")
    print(f"  - All metrics broken down by side")
    print("\nTo view results:")
    print(f"  cat {output_file} | python3 -m json.tool | less")


if __name__ == "__main__":
    run_benchmark()
