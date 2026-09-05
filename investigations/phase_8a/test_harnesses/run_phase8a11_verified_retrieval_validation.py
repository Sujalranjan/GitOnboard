#!/usr/bin/env python3
"""
Phase 8A.11: Verified-Existing Symbol Retrieval Validation

Objective: Test retrieval for ONLY verified-existing symbols.
Ground truth FIRST, then measure retrieval.

Verified-existing symbols (from Phase 8A.10 audit):
1. resetModal (function)
2. ForgotPasswordModal (class)
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# VERIFIED-EXISTING symbols (confirmed Phase 8A.10)
VERIFIED_SYMBOLS = {
    "function": ["resetModal"],
    "class": ["ForgotPasswordModal"],
}

REPO_PATH = Path("/home/dheeraj/Deep-Guard/Deep-Guard-Frontend")

def verify_symbol_source_exists(symbol_name: str, entity_type: str) -> dict:
    """
    STEP 1: Verify symbol exists in source code.
    This is ground truth. Do not proceed without confirmation.
    """
    result = {
        "symbol": symbol_name,
        "type": entity_type,
        "source_verified": False,
        "source_location": None,
        "error": None,
    }

    try:
        # Grep for the symbol
        grep_patterns = [
            f"function {symbol_name}",
            f"const {symbol_name}",
            f"class {symbol_name}",
        ]

        for pattern in grep_patterns:
            try:
                output = subprocess.check_output(
                    ["grep", "-r", pattern, str(REPO_PATH), "--include=*.ts", "--include=*.tsx", "-n"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                if output:
                    result["source_verified"] = True
                    result["source_location"] = output.strip()
                    return result
            except subprocess.CalledProcessError:
                continue

        result["error"] = f"Symbol {symbol_name} NOT FOUND in source"
        return result

    except Exception as e:
        result["error"] = str(e)
        return result


def test_retrieval_via_search(symbol_name: str, entity_type: str) -> dict:
    """
    STEP 2: Test retrieval using search_repository.
    Only called if source verification passes.
    """
    result = {
        "symbol": symbol_name,
        "type": entity_type,
        "search_executed": False,
        "search_found": False,
        "search_result": None,
        "error": None,
    }

    # TODO: Implement actual API call to search_repository
    # For now, document the intended test
    result["note"] = "TODO: Implement HTTP call to /api/repos/Deep-Guard-Frontend/search with query={symbol_name}, entity_type={entity_type}"

    return result


def main():
    print("=" * 80)
    print("PHASE 8A.11: VERIFIED-EXISTING SYMBOL RETRIEVAL VALIDATION")
    print("=" * 80)
    print()
    print("Objective: Test retrieval for symbols confirmed to exist in source")
    print("Method: Ground truth FIRST (source verification), then retrieval testing")
    print("=" * 80)
    print()

    all_results = {
        "timestamp": datetime.now().isoformat(),
        "repository": str(REPO_PATH),
        "ground_truth_source": "Phase 8A.10 audit",
        "verified_symbols": VERIFIED_SYMBOLS,
        "test_results": {
            "source_verification": [],
            "retrieval_tests": [],
        },
    }

    # STEP 1: Verify ground truth (source existence)
    print("STEP 1: GROUND TRUTH VERIFICATION")
    print("-" * 80)

    source_verified = {}
    for entity_type, symbols in VERIFIED_SYMBOLS.items():
        print(f"\n{entity_type.upper()} symbols:")
        for symbol in symbols:
            result = verify_symbol_source_exists(symbol, entity_type)
            all_results["test_results"]["source_verification"].append(result)
            source_verified[symbol] = result["source_verified"]

            if result["source_verified"]:
                print(f"  ✓ {symbol:30} FOUND IN SOURCE")
                if result["source_location"]:
                    print(f"    Location: {result['source_location'][:80]}")
            else:
                print(f"  ✗ {symbol:30} NOT FOUND IN SOURCE")
                print(f"    ERROR: {result['error']}")

    # STEP 2: Test retrieval (only for verified symbols)
    print("\n" + "=" * 80)
    print("STEP 2: RETRIEVAL TESTING")
    print("-" * 80)

    verified_count = sum(1 for v in source_verified.values() if v)
    print(f"\nSymbols verified in source: {verified_count}/{len(source_verified)}")

    if verified_count == 0:
        print("\n⚠ No verified symbols to test for retrieval")
        print("Cannot proceed without ground truth")
    else:
        print("\nTesting retrieval for verified symbols...")
        for entity_type, symbols in VERIFIED_SYMBOLS.items():
            print(f"\n{entity_type.upper()} symbols:")
            for symbol in symbols:
                if source_verified.get(symbol):
                    print(f"  Testing: {symbol}")
                    result = test_retrieval_via_search(symbol, entity_type)
                    all_results["test_results"]["retrieval_tests"].append(result)
                    print(f"    Status: {result['note']}")

    # Save results
    print("\n" + "=" * 80)
    output_file = Path("PHASE8A11_VERIFIED_RETRIEVAL_RESULTS.json")
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"✓ Results saved to {output_file}")

    print("\n" + "=" * 80)
    print("PHASE 8A.11 STATUS")
    print("=" * 80)

    if verified_count == len(source_verified):
        print(f"\n✓ Ground truth verified for all {verified_count} symbols")
        print("  Ready to measure retrieval")
    else:
        print(f"\n✗ Ground truth failed for {len(source_verified) - verified_count} symbols")
        print("  Cannot trust retrieval tests without valid ground truth")

    print("\nNext: Implement search_repository API calls in retrieval testing")
    print("=" * 80)


if __name__ == "__main__":
    main()
