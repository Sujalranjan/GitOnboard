#!/usr/bin/env python3
"""
Log analysis tool to find and trace failures in comprehensive logging.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import argparse

LOGS_DIR = Path("/home/dheeraj/repository_intelligence_platform/logs")


def find_errors():
    """Find all logged errors"""
    print("=" * 80)
    print("FINDING ALL ERRORS")
    print("=" * 80)

    errors_dir = LOGS_DIR / "errors"
    if not errors_dir.exists():
        print("No errors directory found")
        return

    error_files = sorted(errors_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not error_files:
        print("✓ No errors found!")
        return

    print(f"Found {len(error_files)} error(s):\n")

    for error_file in error_files[:10]:  # Show last 10 errors
        try:
            with open(error_file) as f:
                error_data = json.load(f)

            print(f"📌 {error_file.name}")
            print(f"   Type: {error_data.get('error_type', 'Unknown')}")
            print(f"   Stage: {error_data.get('stage', 'Unknown')}")
            print(f"   Message: {error_data.get('error_message', 'No message')[:100]}")
            print(f"   Time: {error_data.get('timestamp', 'Unknown')}")
            print()
        except Exception as e:
            print(f"   Failed to read {error_file.name}: {e}")


def trace_request(request_id: str):
    """Trace complete flow for a single request"""
    print("=" * 80)
    print(f"TRACING REQUEST: {request_id}")
    print("=" * 80)

    session_dirs = [d for d in LOGS_DIR.glob(f"*") if d.is_dir() and "_" in d.name]
    found_files = []

    for session_dir in session_dirs:
        matching_files = sorted(session_dir.glob(f"*{request_id}*"))
        if matching_files:
            found_files.extend(matching_files)

    if not found_files:
        print(f"No logs found for request {request_id}")
        return

    print(f"Found {len(found_files)} log files\n")

    # Group by stage
    stages = defaultdict(list)
    for f in found_files:
        if f.name.startswith("01_"):
            stages["Query"].append(f)
        elif f.name.startswith("02_"):
            stages["LLM Request"].append(f)
        elif f.name.startswith("03_"):
            stages["LLM Response"].append(f)
        elif f.name.startswith("04_"):
            stages["Tool Calls"].append(f)
        elif f.name.startswith("05_"):
            stages["RIM Contribution"].append(f)
        elif f.name.startswith("06_"):
            stages["Metrics"].append(f)
        elif f.name.startswith("07_"):
            stages["Completion"].append(f)
        elif f.name.startswith("99_"):
            stages["Errors"].append(f)

    # Display in order
    for stage in ["Query", "LLM Request", "LLM Response", "Tool Calls", "RIM Contribution", "Metrics", "Completion", "Errors"]:
        if stage in stages:
            print(f"📌 {stage}:")
            for f in stages[stage]:
                print(f"   - {f.name}")

    print("\nTo view detailed logs:")
    print(f"  find /home/dheeraj/repository_intelligence_platform/logs -name '*{request_id}*' -type f | head -20")


def find_silent_failures():
    """Find requests that completed but may have silent failures"""
    print("=" * 80)
    print("FINDING SILENT FAILURES")
    print("=" * 80)

    metrics_files = sorted(LOGS_DIR.glob("*/06_metrics_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)

    print(f"Analyzing {len(metrics_files)} completed requests...\n")

    issues = []

    for metrics_file in metrics_files[:50]:  # Check last 50
        try:
            with open(metrics_file) as f:
                data = json.load(f)

            request_id = data.get("request_id")
            repo = data.get("repository")
            failure = data.get("failure_detected", False)
            degradation = data.get("semantic_degradation")
            baseline_calls = data.get("baseline_tool_calls", 0)
            rim_calls = data.get("rim_tool_calls", 0)

            # Check for potential issues
            if failure:
                issues.append((request_id, repo, "Failure detected", "CRITICAL"))
            elif degradation:
                issues.append((request_id, repo, f"Semantic degradation: {degradation}", "WARNING"))
            elif baseline_calls == 0 and rim_calls == 0:
                issues.append((request_id, repo, "No tool calls made", "WARNING"))
            elif abs(baseline_calls - rim_calls) > 5:
                issues.append((request_id, repo, f"Large divergence: baseline={baseline_calls}, rim={rim_calls}", "INFO"))

        except Exception as e:
            pass

    if not issues:
        print("✓ No silent failures detected!")
        return

    print(f"Found {len(issues)} potential issue(s):\n")

    for request_id, repo, issue, severity in sorted(issues, key=lambda x: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}[x[3]]):
        icon = "🔴" if severity == "CRITICAL" else "🟡" if severity == "WARNING" else "🔵"
        print(f"{icon} {severity:8} | {request_id:10} | {repo:30} | {issue}")


def main():
    parser = argparse.ArgumentParser(description="Analyze comprehensive logs for failures")
    parser.add_argument("--errors", action="store_true", help="Show all errors")
    parser.add_argument("--trace", metavar="REQUEST_ID", help="Trace specific request")
    parser.add_argument("--silent", action="store_true", help="Find silent failures")
    parser.add_argument("--all", action="store_true", help="Run all analysis")

    args = parser.parse_args()

    if not LOGS_DIR.exists():
        print(f"Logs directory not found: {LOGS_DIR}")
        sys.exit(1)

    if args.all or not any([args.errors, args.trace, args.silent]):
        find_errors()
        print()
        find_silent_failures()

    if args.errors:
        find_errors()

    if args.trace:
        trace_request(args.trace)

    if args.silent:
        find_silent_failures()


if __name__ == "__main__":
    main()
