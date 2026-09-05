#!/usr/bin/env python3
"""
Phase 2H: Profile Analyzers with Progressive Subset Sizing

Tests on 50, 100, 250, 500, 1000+ files to measure scaling behavior.
Identifies which analyzer is slow and by how much.
"""
import json
import time
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

def count_files_in_directory(directory, limit=None):
    """Count Python/TypeScript files, optionally limiting to first N."""
    files = []
    for ext in ['*.py', '*.ts', '*.js', '*.go']:
        files.extend(Path(directory).rglob(ext))
        if limit and len(files) >= limit:
            break
    return files[:limit] if limit else files

def create_subset(source_dir, target_dir, file_count):
    """Create a subset of the repository with specified file count."""
    Path(target_dir).mkdir(parents=True, exist_ok=True)

    files = count_files_in_directory(source_dir, limit=file_count)

    # Copy files maintaining directory structure
    for src_file in files:
        rel_path = src_file.relative_to(source_dir)
        dst_file = Path(target_dir) / rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)

    return len(files)

def run_analysis_on_subset(subset_dir):
    """Run AnalysisEngine on a subset and extract timing data."""
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry
    from pathlib import Path
    import time

    start = time.time()

    try:
        engine = AnalysisEngine(subset_dir, get_default_registry())
        model = engine.run(
            repo_name=f"Phase2H-Profile",
            skip_validation=True  # Skip validation to isolate analyzer timing
        )

        elapsed = time.time() - start

        # Get timing data from model
        timings = getattr(model, '_analyzer_timings', {})

        return {
            "status": "success",
            "total_time": elapsed,
            "entities": len(model.entities),
            "relationships": len(model.relationships),
            "analyzer_timings": timings
        }

    except Exception as e:
        elapsed = time.time() - start
        return {
            "status": "failed",
            "total_time": elapsed,
            "error": str(e)
        }

def main():
    print("\n" + "=" * 80)
    print("PHASE 2H: ANALYZER PERFORMANCE PROFILING")
    print("=" * 80)

    source_repo = "/home/dheeraj/repository_intelligence_platform"
    work_dir = Path("/tmp/phase2h_profile")

    # Test sizes
    test_sizes = [50, 100, 250, 500]
    results = {
        "timestamp": datetime.now().isoformat(),
        "source_repository": source_repo,
        "tests": {}
    }

    for size in test_sizes:
        print(f"\n[Test] Running analysis on ~{size} files...")

        subset_dir = work_dir / f"subset_{size}"
        actual_count = create_subset(source_repo, str(subset_dir), size)

        print(f"  Created subset with {actual_count} files")
        print(f"  Running analysis...")

        result = run_analysis_on_subset(str(subset_dir))

        test_key = f"{actual_count}_files"
        results["tests"][test_key] = result

        if result["status"] == "success":
            print(f"  ✓ Completed in {result['total_time']:.2f}s")
            print(f"    Entities: {result['entities']}")
            print(f"    Relationships: {result['relationships']}")

            # Show top 3 slowest analyzers
            timings = result["analyzer_timings"]
            if timings:
                sorted_analyzers = sorted(
                    timings.items(),
                    key=lambda x: x[1]["duration_seconds"],
                    reverse=True
                )
                print(f"  Top analyzers:")
                for analyzer_name, timing in sorted_analyzers[:3]:
                    print(f"    - {analyzer_name}: {timing['duration_seconds']:.2f}s")
        else:
            print(f"  ✗ Failed: {result.get('error', 'Unknown error')}")

    # Save results
    output_file = Path(".") / "phase2h_profile_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n" + "=" * 80)
    print(f"Results saved to {output_file}")
    print(f"=" * 80)

    # Analysis
    print(f"\n[ANALYSIS]")

    # Look for scaling pattern
    test_results = []
    for test_key, result in results["tests"].items():
        if result["status"] == "success":
            files = int(test_key.split("_")[0])
            test_results.append((files, result["total_time"]))

    if len(test_results) >= 2:
        test_results.sort()
        print(f"\nScaling analysis:")
        for files, duration in test_results:
            print(f"  {files:4d} files: {duration:6.2f}s")

        # Check for quadratic scaling
        if len(test_results) >= 3:
            r1_files, r1_time = test_results[0]
            r2_files, r2_time = test_results[1]
            r3_files, r3_time = test_results[2]

            # Expected time if O(n²): time ~ n²
            ratio1_files = r2_files / r1_files
            ratio1_time = r2_time / r1_time

            ratio2_files = r3_files / r2_files
            ratio2_time = r3_time / r2_time

            print(f"\nFile ratio: {ratio1_files:.2f}x → Time ratio: {ratio1_time:.2f}x")
            print(f"File ratio: {ratio2_files:.2f}x → Time ratio: {ratio2_time:.2f}x")

            if ratio1_time > ratio1_files ** 1.5:
                print(f"⚠️  Possible super-linear scaling (> O(n))")
            elif ratio1_time > ratio1_files:
                print(f"⚠️  Possible quadratic scaling (O(n²) or worse)")
            else:
                print(f"✓ Linear or sub-linear scaling")

if __name__ == "__main__":
    main()
