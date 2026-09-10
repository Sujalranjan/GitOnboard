#!/usr/bin/env python3
"""
Phase 8A.10: Ground-Truth Integrity Audit

Objective: Verify every entity from Phase 8A.6 against actual repository.
Recalculate false-negative rate using only verified-existing symbols.
"""

import json
import subprocess
from pathlib import Path

# Ground truth from Phase 8A.6
GROUND_TRUTH_8A6 = {
    "function": [
        "resetModal",
        "setupMockHTTPServer",
        "handleAuthFlow",
    ],
    "class": [
        "ForgotPasswordModal",
        "LoginComponent",
    ],
    "file": [
        "package.json",
        "src/components/ForgetPasswordModal.tsx",
        "README.md",
    ],
}

REPO_PATH = Path("/home/dheeraj/Deep-Guard/Deep-Guard-Frontend")

def verify_symbol_exists(symbol_name: str, entity_type: str) -> dict:
    """Verify if a symbol actually exists in the repository."""

    result = {
        "symbol": symbol_name,
        "type": entity_type,
        "status": None,
        "evidence": [],
        "notes": "",
    }

    if entity_type == "file":
        # Check if file exists
        file_path = REPO_PATH / symbol_name
        if file_path.exists():
            result["status"] = "EXISTS"
            result["evidence"].append(f"File found: {file_path}")
        else:
            result["status"] = "DOES_NOT_EXIST"
            result["evidence"].append(f"File not found: {file_path}")
        return result

    # For functions and classes, grep the repository
    try:
        # Grep for the symbol (function or class declaration)
        grep_patterns = [
            f"function {symbol_name}",  # function declaration
            f"const {symbol_name}",      # const function/component
            f"class {symbol_name}",      # class declaration
            f"export.*{symbol_name}",    # any export
        ]

        for pattern in grep_patterns:
            try:
                output = subprocess.check_output(
                    ["grep", "-r", pattern, str(REPO_PATH), "--include=*.ts", "--include=*.tsx"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                if output:
                    result["status"] = "EXISTS"
                    result["evidence"].append(f"Grep match (pattern '{pattern}'): {output.strip()[:100]}")
                    break
            except subprocess.CalledProcessError:
                continue

        if result["status"] is None:
            result["status"] = "DOES_NOT_EXIST"
            result["evidence"].append(f"No grep matches found for patterns: {', '.join(grep_patterns)}")

    except Exception as e:
        result["status"] = "ERROR"
        result["notes"] = str(e)

    return result

def main():
    print("=" * 80)
    print("PHASE 8A.10: GROUND-TRUTH INTEGRITY AUDIT")
    print("=" * 80)
    print()

    audit_results = {
        "timestamp": str(Path.cwd()),
        "ground_truth_source": "Phase 8A.6 (run_phase8a6_retrieval_adequacy.py)",
        "repository": str(REPO_PATH),
        "audit_results": {},
        "summary": {},
    }

    # Verify each entity
    all_results = []
    for entity_type, symbols in GROUND_TRUTH_8A6.items():
        print(f"\n{entity_type.upper()} ENTITIES:")
        print("-" * 80)

        audit_results["audit_results"][entity_type] = []

        for symbol in symbols:
            result = verify_symbol_exists(symbol, entity_type)
            all_results.append(result)
            audit_results["audit_results"][entity_type].append(result)

            status_symbol = "✓" if result["status"] == "EXISTS" else "✗"
            print(f"{status_symbol} {symbol:30} {result['status']:20}")
            if result["evidence"]:
                print(f"    Evidence: {result['evidence'][0][:70]}")

    # Calculate summary
    print("\n" + "=" * 80)
    print("AUDIT SUMMARY")
    print("=" * 80)

    exists_count = sum(1 for r in all_results if r["status"] == "EXISTS")
    does_not_exist_count = sum(1 for r in all_results if r["status"] == "DOES_NOT_EXIST")
    error_count = sum(1 for r in all_results if r["status"] == "ERROR")
    total_count = len(all_results)

    audit_results["summary"] = {
        "total_entities": total_count,
        "exists": exists_count,
        "does_not_exist": does_not_exist_count,
        "error": error_count,
        "error_rate": f"{error_count/total_count*100:.1f}%",
        "ground_truth_error_rate": f"{does_not_exist_count/total_count*100:.1f}%",
    }

    print(f"\nTotal entities tested: {total_count}")
    print(f"  ✓ EXISTS:            {exists_count} ({exists_count/total_count*100:.1f}%)")
    print(f"  ✗ DOES_NOT_EXIST:    {does_not_exist_count} ({does_not_exist_count/total_count*100:.1f}%)")
    print(f"  ? ERROR:             {error_count} ({error_count/total_count*100:.1f}%)")

    print(f"\n⚠ GROUND TRUTH ERROR RATE: {does_not_exist_count/total_count*100:.1f}%")
    print(f"  ({does_not_exist_count} out of {total_count} entities in Phase 8A.6 ground truth do not actually exist)")

    # Recalculate Phase 8A.6 false-negative rate
    print("\n" + "=" * 80)
    print("PHASE 8A.6 FALSE-NEGATIVE RATE RECALCULATION")
    print("=" * 80)

    # Load Phase 8A.6 results if available
    results_file = Path("PHASE8A6_RETRIEVAL_ADEQUACY_RAW_RESULTS.json")
    if results_file.exists():
        with open(results_file, "r") as f:
            phase8a6_results = json.load(f)

        # Filter to only verified-existing entities
        verified_existing = {r["symbol"] for r in all_results if r["status"] == "EXISTS"}

        print(f"\nVerified existing entities: {len(verified_existing)}")
        print(f"  {', '.join(sorted(verified_existing))}")

        # Recalculate metrics
        existing_tests = [
            r for r in phase8a6_results
            if r.get("ground_truth") == "EXISTS" and r.get("entity_name") in verified_existing
        ]

        if existing_tests:
            found = sum(1 for r in existing_tests if r.get("retrieval", {}).get("results_found"))
            not_found = sum(1 for r in existing_tests if not r.get("retrieval", {}).get("results_found"))

            print(f"\nResults for verified-existing entities only:")
            print(f"  Found by search:     {found}/{len(existing_tests)}")
            print(f"  Not found (FN):      {not_found}/{len(existing_tests)}")
            print(f"  Recall:              {found/len(existing_tests)*100:.1f}%")
            print(f"  False-Negative Rate: {not_found/len(existing_tests)*100:.1f}%")

            audit_results["summary"]["8a6_recalculated_metrics"] = {
                "verified_existing_entities": len(verified_existing),
                "tests_found": found,
                "tests_not_found": not_found,
                "recall": f"{found/len(existing_tests)*100:.1f}%",
                "false_negative_rate": f"{not_found/len(existing_tests)*100:.1f}%",
            }
        else:
            print("\nNo verified-existing entities to recalculate from Phase 8A.6 results")
    else:
        print("\nPhase 8A.6 results file not found - cannot recalculate metrics")

    # Save audit results
    output_file = Path("PHASE8A10_GROUND_TRUTH_AUDIT.json")
    with open(output_file, "w") as f:
        json.dump(audit_results, f, indent=2)
    print(f"\n✓ Audit results saved to {output_file}")

    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)

    if does_not_exist_count > 0:
        print(f"\n⚠ CRITICAL: Phase 8A.6 ground truth contains {does_not_exist_count} incorrect entities")
        print(f"  This invalidates the Phase 8A.6-8A.8 evidence chain")
        print(f"  Phase 8A.9 investigation was correct to be inconclusive")

    if exists_count > 0:
        print(f"\n✓ {exists_count} verified-existing entities can be used for re-analysis")
        print(f"  If any of these show retrieval failures, it confirms index/retrieval issues")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
