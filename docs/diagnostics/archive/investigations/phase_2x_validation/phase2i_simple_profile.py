#!/usr/bin/env python3
"""
Phase 2I Task 1: Simple Direct Profiling

Analyzes the real repository on subsets by running AnalysisEngine
and measuring actual output to understand scaling behavior.
"""
import json
import time
from pathlib import Path
from datetime import datetime

def get_source_files(root_dir, limit=None):
    """Get source files excluding development directories."""
    files = []
    for ext in ['*.py', '*.ts', '*.js', '*.go']:
        files.extend(Path(root_dir).rglob(ext))

    # Filter out development directories
    excluded = {'.venv', '.git', '__pycache__', 'node_modules', '.diagnostics', 'data/worktrees', '.pytest_cache'}
    files = [f for f in files if not any(part in f.parts for part in excluded)]

    files = sorted(set(files))
    if limit:
        files = files[:limit]

    return files

def run_analysis_on_repo(source_dir, file_limit):
    """Run AnalysisEngine and measure results."""
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry
    from backend.intelligence.engine.scanner.scanner import RepositoryScanner

    # Get files that would be analyzed
    all_source_files = get_source_files(source_dir, limit=file_limit)
    total_bytes = sum(f.stat().st_size for f in all_source_files)

    print(f"    Will analyze up to {len(all_source_files)} files ({total_bytes:,} bytes)")

    # Run engine
    engine = AnalysisEngine(source_dir, get_default_registry())

    start = time.time()
    try:
        model = engine.run(
            repo_name="Phase2I-Analysis",
            skip_validation=True
        )
        elapsed = time.time() - start

        timings = getattr(model, '_analyzer_timings', {})

        return {
            "status": "success",
            "requested_limit": file_limit,
            "source_files_available": len(all_source_files),
            "total_bytes_available": total_bytes,
            "elapsed": elapsed,
            "entities": len(model.entities),
            "relationships": len(model.relationships),
            "analyzer_timings": timings
        }

    except Exception as e:
        elapsed = time.time() - start
        print(f"    Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "failed",
            "requested_limit": file_limit,
            "elapsed": elapsed,
            "error": str(e)
        }

def main():
    print("\n" + "=" * 80)
    print("PHASE 2I TASK 1: SIMPLE DIRECT PROFILING")
    print("=" * 80)
    print("Note: Analyzing real repository with AnalysisEngine")
    print("      (file limit parameter affects what we COULD analyze,")
    print("       but AnalysisEngine scans entire directory)")
    print("=" * 80)

    source_repo = "/home/dheeraj/repository_intelligence_platform"

    test_sizes = [50, 100, 250, 500]
    results = {
        "timestamp": datetime.now().isoformat(),
        "methodology": "Direct AnalysisEngine run on real repository",
        "source_repository": source_repo,
        "note": "File limit shown for tracking, but AnalysisEngine scans full directory",
        "tests": {}
    }

    for size in test_sizes:
        print(f"\n[Test] File limit: {size}...")

        result = run_analysis_on_repo(source_repo, size)

        test_key = f"limit_{size}"
        results["tests"][test_key] = result

        if result["status"] == "success":
            print(f"  ✓ Completed in {result['elapsed']:.3f}s")
            print(f"    Entities: {result['entities']}, Relationships: {result['relationships']}")
        else:
            print(f"  ✗ Failed")

    # Save results
    output_file = Path(".") / "phase2i_simple_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n" + "=" * 80)
    print(f"Results saved to {output_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
