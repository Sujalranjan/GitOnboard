#!/usr/bin/env python3
"""
Phase 2I: Root-Cause Performance Profiling

Corrects the subset selection issue and performs function-level profiling.
"""
import json
import time
import shutil
import cProfile
import pstats
import io
from pathlib import Path
from datetime import datetime

def get_sorted_files(directory, limit=None):
    """Get files in deterministic order (sorted by path) to ensure reproducibility."""
    files = []
    for ext in ['*.py', '*.ts', '*.js', '*.go']:
        files.extend(Path(directory).rglob(ext))

    # Sort by path to ensure deterministic selection
    files = sorted(set(files))  # Remove duplicates, then sort

    if limit:
        files = files[:limit]

    return files

def create_subset(source_dir, target_dir, file_count):
    """Create a subset with explicit diagnostics."""
    Path(target_dir).mkdir(parents=True, exist_ok=True)

    # Get deterministic file selection
    files = get_sorted_files(source_dir, limit=file_count)

    # Copy files maintaining directory structure
    total_bytes = 0
    for src_file in files:
        rel_path = src_file.relative_to(source_dir)
        dst_file = Path(target_dir) / rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        total_bytes += src_file.stat().st_size

    return {
        "requested_count": file_count,
        "actual_count": len(files),
        "total_bytes": total_bytes,
        "files": [str(f.relative_to(source_dir)) for f in files[:5]]  # Sample
    }

def profile_analysis(subset_dir):
    """Run analysis with function-level profiling."""
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    engine = AnalysisEngine(subset_dir, get_default_registry())

    # Profile the run
    pr = cProfile.Profile()
    pr.enable()

    start = time.time()
    model = engine.run(
        repo_name="Phase2I-Profile",
        skip_validation=True
    )
    elapsed = time.time() - start

    pr.disable()

    # Get top functions by cumulative time
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30)  # Top 30

    timings = getattr(model, '_analyzer_timings', {})

    return {
        "elapsed": elapsed,
        "entities": len(model.entities),
        "relationships": len(model.relationships),
        "analyzer_timings": timings,
        "profile_top_functions": s.getvalue()
    }

def main():
    print("\n" + "=" * 80)
    print("PHASE 2I: ROOT-CAUSE PERFORMANCE PROFILING")
    print("=" * 80)

    source_repo = "/home/dheeraj/repository_intelligence_platform"
    work_dir = Path("/tmp/phase2i_profile")

    # Test sizes - corrected to ensure distinct subsets
    test_sizes = [50, 100, 250, 500]
    results = {
        "timestamp": datetime.now().isoformat(),
        "source_repository": source_repo,
        "tests": {}
    }

    for size in test_sizes:
        print(f"\n[Test] Running analysis on {size} files...")

        subset_dir = work_dir / f"subset_{size}"
        subset_info = create_subset(source_repo, str(subset_dir), size)

        actual_count = subset_info["actual_count"]
        total_bytes = subset_info["total_bytes"]

        print(f"  Requested: {size}, Actual: {actual_count}, Bytes: {total_bytes:,}")

        # Verify we're getting different subsets
        if size > 50:
            prev_size = test_sizes[test_sizes.index(size)-1]
            if actual_count <= test_sizes[test_sizes.index(size)-2]:
                print(f"  ⚠️  WARNING: Actual count ({actual_count}) not greater than previous ({prev_size})")

        print(f"  Running analysis...")

        try:
            result = profile_analysis(str(subset_dir))

            test_key = f"{actual_count}_files"
            results["tests"][test_key] = {
                "requested_count": size,
                "actual_count": actual_count,
                "total_bytes": total_bytes,
                "elapsed": result["elapsed"],
                "entities": result["entities"],
                "relationships": result["relationships"],
                "analyzer_timings": result["analyzer_timings"],
                "profile_summary": result["profile_top_functions"][:1000]  # First 1000 chars
            }

            print(f"  ✓ Completed in {result['elapsed']:.2f}s")
            print(f"    Entities: {result['entities']}, Relationships: {result['relationships']}")

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results["tests"][f"{size}_files"] = {"status": "failed", "error": str(e)}

    # Save results
    output_file = Path(".") / "phase2i_profile_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n" + "=" * 80)
    print(f"Results saved to {output_file}")
    print(f"=" * 80)

    # Analysis
    print(f"\n[SCALING ANALYSIS]")
    test_results = []
    for test_key, result in results["tests"].items():
        if "elapsed" in result:
            actual_count = result["actual_count"]
            elapsed = result["elapsed"]
            test_results.append((actual_count, elapsed, result))

    test_results.sort()

    print(f"\nCorrected scaling analysis:")
    for files, duration, result in test_results:
        print(f"  {files:4d} files ({result['total_bytes']:12,} bytes): {duration:6.2f}s")

    if len(test_results) >= 2:
        print(f"\nScaling ratios:")
        for i in range(1, len(test_results)):
            f1, t1, r1 = test_results[i-1]
            f2, t2, r2 = test_results[i]

            ratio_files = f2 / f1
            ratio_time = t2 / t1
            ratio_bytes = r2['total_bytes'] / r1['total_bytes']

            print(f"  {f1:4d} → {f2:4d} files ({ratio_files:.2f}x), " +
                  f"{t1:.1f}s → {t2:.1f}s ({ratio_time:.2f}x), " +
                  f"bytes {r1['total_bytes']:,} → {r2['total_bytes']:,} ({ratio_bytes:.2f}x)")

if __name__ == "__main__":
    main()
