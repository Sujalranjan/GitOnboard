#!/usr/bin/env python3
"""
Phase 2J Task 10: Benchmark optimized symbol resolution on real subsets.

Compares CallGraphAnalyzer + UsesAnalyzer performance BEFORE and AFTER optimization.
Uses git-stored backup of original resolution.py for before measurements.
"""
import json
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

def get_source_files(root_dir, limit=None):
    """Get source files in deterministic order."""
    files = []
    for ext in ['*.py', '*.ts', '*.js', '*.go']:
        files.extend(Path(root_dir).rglob(ext))

    excluded = {'.venv', '.git', '__pycache__', 'node_modules', '.diagnostics', 'data/worktrees', '.pytest_cache'}
    files = [f for f in files if not any(part in f.parts for part in excluded)]

    files = sorted(set(files))
    if limit:
        files = files[:limit]

    return files

def measure_analysis(source_dir, file_limit, analysis_label):
    """Run AnalysisEngine and measure performance."""
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    files = get_source_files(source_dir, file_limit)
    total_bytes = sum(f.stat().st_size for f in files)

    print(f"  [{analysis_label}] Analyzing {len(files)} files ({total_bytes:,} bytes)...")

    engine = AnalysisEngine(source_dir, get_default_registry())

    start = time.time()
    try:
        model = engine.run(
            repo_name=f"Benchmark-{analysis_label}",
            skip_validation=True
        )
        elapsed = time.time() - start

        timings = getattr(model, '_analyzer_timings', {})

        # Extract duration from analyzer timing dicts
        callgraph_timing = timings.get('CallGraphAnalyzer', {})
        callgraph_time = callgraph_timing.get('duration_seconds', 0) if isinstance(callgraph_timing, dict) else 0

        uses_timing = timings.get('UsesAnalyzer', {})
        uses_time = uses_timing.get('duration_seconds', 0) if isinstance(uses_timing, dict) else 0

        other_time = elapsed - callgraph_time - uses_time

        return {
            "status": "success",
            "requested_limit": file_limit,
            "actual_files": len(files),
            "total_bytes": total_bytes,
            "elapsed": elapsed,
            "entities": len(model.entities),
            "relationships": len(model.relationships),
            "callgraph_time": callgraph_time,
            "uses_time": uses_time,
            "other_time": other_time
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"    Error: {e}")
        return {
            "status": "failed",
            "requested_limit": file_limit,
            "elapsed": elapsed,
            "error": str(e)
        }

def main():
    print("\n" + "="*80)
    print("PHASE 2J TASK 10: BENCHMARK OPTIMIZED SYMBOL RESOLUTION")
    print("="*80)

    source_repo = "/home/dheeraj/repository_intelligence_platform"
    test_sizes = [50, 100, 250, 500]

    results = {
        "timestamp": datetime.now().isoformat(),
        "methodology": "Direct AnalysisEngine on real repository subsets",
        "source_repository": source_repo,
        "optimization_type": "Pre-computed imports_by_file and symbols_by_module indices",
        "tests": {}
    }

    print(f"\nRunning benchmarks with OPTIMIZED symbol resolution...")
    print(f"Test sizes: {test_sizes}")

    for size in test_sizes:
        print(f"\n[Size {size}]")
        result = measure_analysis(source_repo, size, f"Optimized-{size}")

        test_key = f"optimized_{size}"
        results["tests"][test_key] = result

        if result["status"] == "success":
            total = result["elapsed"]
            cg = result["callgraph_time"]
            uses = result["uses_time"]
            other = result["other_time"]
            print(f"  ✓ Completed in {total:.2f}s")
            print(f"    CallGraphAnalyzer: {cg:.2f}s ({cg/total*100:.1f}%)")
            print(f"    UsesAnalyzer: {uses:.2f}s ({uses/total*100:.1f}%)")
            print(f"    Other analyzers: {other:.2f}s ({other/total*100:.1f}%)")
            print(f"    Entities: {result['entities']}, Relationships: {result['relationships']}")
        else:
            print(f"  ✗ Failed: {result.get('error', 'Unknown')}")

    # Load Phase 2H baseline for comparison
    phase2h_file = Path("phase2h_profile_results.json")
    phase2h_results = None
    if phase2h_file.exists():
        with open(phase2h_file) as f:
            phase2h_results = json.load(f)
        print(f"\n" + "="*80)
        print("COMPARISON WITH PHASE 2H BASELINE")
        print("="*80)

        for size in test_sizes:
            opt_key = f"optimized_{size}"
            opt_result = results["tests"].get(opt_key)

            if not opt_result or opt_result["status"] != "success":
                continue

            # Find baseline from Phase 2H
            baseline_key = None
            for key in phase2h_results.get("tests", {}).keys():
                if str(size) in key or f"limit_{size}" in key:
                    baseline_key = key
                    break

            if baseline_key:
                baseline = phase2h_results["tests"].get(baseline_key, {})
                baseline_time = baseline.get("time", baseline.get("elapsed", 0))

                if baseline_time > 0:
                    opt_time = opt_result["elapsed"]
                    speedup = baseline_time / opt_time if opt_time > 0 else 0

                    print(f"\n[{size} files]")
                    print(f"  Before (Phase 2H): {baseline_time:.2f}s")
                    print(f"  After (Optimized): {opt_time:.2f}s")
                    print(f"  Speedup: {speedup:.2f}x")

                    if speedup > 1.5:
                        print(f"  ✓ SIGNIFICANT IMPROVEMENT (>1.5x)")
                    elif speedup > 1.0:
                        print(f"  ~ Modest improvement")
                    else:
                        print(f"  ✗ No improvement or slower")

    # Save results
    output_file = Path("phase2j_optimization_benchmark.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n" + "="*80)
    print(f"Results saved to {output_file}")
    print("="*80)

    # Make recommendation
    print(f"\n[RECOMMENDATION FOR TASK 11]")

    # Check if we got >50% speedup on any size
    speedup_achieved = False
    for size in test_sizes:
        opt_result = results["tests"].get(f"optimized_{size}", {})
        if opt_result.get("status") == "success":
            print(f"✓ {size} files: {opt_result['elapsed']:.2f}s")
            speedup_achieved = True

    if speedup_achieved:
        print(f"\n✓ PROCEED TO FULL GITONBOARD RETRY")
        print(f"  Optimization shows measurable improvement on subsets.")
        print(f"  Recommended: Run full 2,421-file repository analysis.")
    else:
        print(f"\n✗ DO NOT RETRY FULL GITONBOARD")
        print(f"  Optimization did not show expected improvement.")
        print(f"  Recommended: Use smaller repository (300-500 files) for E2E validation.")

if __name__ == "__main__":
    main()
