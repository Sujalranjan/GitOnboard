#!/usr/bin/env python3
"""
Phase 2I Task 1: Direct Subset Analysis (Fixed)

Analyzes subsets of the ORIGINAL repository directory to avoid copy/dependency issues.
Uses directory filtering instead of file copying for accurate measurements.
"""
import json
import time
import cProfile
import pstats
import io
from pathlib import Path
from datetime import datetime

def get_all_source_files(root_dir):
    """Get all source files in deterministic order."""
    files = []
    for ext in ['*.py', '*.ts', '*.js', '*.go']:
        files.extend(Path(root_dir).rglob(ext))

    # Filter out unwanted directories
    excluded = {'.venv', '.git', '__pycache__', 'node_modules', '.diagnostics', 'data/worktrees'}
    files = [f for f in files if not any(part in f.parts for part in excluded)]

    # Sort by path for determinism
    files = sorted(set(files))
    return files

def create_limited_scanner(source_dir, file_limit):
    """
    Create a custom scanner that limits files analyzed.
    Returns a wrapper that filters files to first N.
    """
    all_files = get_all_source_files(source_dir)
    limited_files = all_files[:file_limit]

    total_bytes = sum(f.stat().st_size for f in limited_files)

    return {
        "requested_count": file_limit,
        "actual_count": len(limited_files),
        "total_bytes": total_bytes,
        "files": limited_files
    }

def profile_subset_analysis(source_dir, file_limit):
    """Run analysis with function-level profiling on file subset."""
    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry
    from backend.intelligence.engine.scanner.scanner import RepositoryScanner

    # Get files to analyze
    file_info = create_limited_scanner(source_dir, file_limit)
    limited_files = file_info["files"]

    print(f"    Files to analyze: {len(limited_files)}")
    print(f"    Total bytes: {file_info['total_bytes']:,}")

    # Create custom scanner that returns only these files
    class LimitedScanner(RepositoryScanner):
        def scan(self):
            # Call parent scan first
            manifest = super().scan()

            # Filter to only our limited files
            limited_set = set(str(f) for f in limited_files)
            manifest.files = [f for f in manifest.files if str(Path(source_dir) / f.path) in limited_set]

            print(f"    Scanner found: {len(manifest.files)} files")
            return manifest

    # Run analysis
    engine = AnalysisEngine(source_dir, get_default_registry())

    # Monkey-patch the scanner
    original_scanner_class = engine.__class__.__dict__.get('scanner_class')

    pr = cProfile.Profile()
    pr.enable()

    start = time.time()

    try:
        # Manually run with our limited scanner
        scanner = LimitedScanner(source_dir)
        manifest = scanner.scan()

        # Continue with normal analysis pipeline
        from backend.intelligence.engine.parser.manager import ASTParserManager

        parser_manager = ASTParserManager(source_dir)
        asts = {}

        for file_info in manifest.files:
            try:
                ast = parser_manager.parse_file(file_info.path, file_info.language)
                if ast:
                    asts[file_info.path] = ast
            except Exception as e:
                pass

        print(f"    ASTs created: {len(asts)}")

        # Run analyzers
        from backend.intelligence.rim.repository import RepositoryModel
        from backend.intelligence.rim.metadata import RepositoryMetadata

        model = RepositoryModel(
            metadata=RepositoryMetadata(
                name="Phase2I-Subset",
                path=source_dir,
                languages=manifest.languages,
                commit="",
                branch=""
            )
        )

        analyzers = engine.registry.get_all()
        for analyzer in analyzers:
            analyzer.analyze(model, asts)

        elapsed = time.time() - start

        timings = getattr(model, '_analyzer_timings', {})

        return {
            "status": "success",
            "requested_count": file_limit,
            "actual_count": len(limited_files),
            "total_bytes": file_info["total_bytes"],
            "scanned_files": len(manifest.files),
            "parsed_asts": len(asts),
            "elapsed": elapsed,
            "entities": len(model.entities),
            "relationships": len(model.relationships),
            "analyzer_timings": timings
        }

    except Exception as e:
        pr.disable()
        elapsed = time.time() - start
        print(f"    Error: {e}")
        return {
            "status": "failed",
            "requested_count": file_limit,
            "actual_count": len(limited_files),
            "total_bytes": file_info["total_bytes"],
            "elapsed": elapsed,
            "error": str(e)
        }

    pr.disable()

def main():
    print("\n" + "=" * 80)
    print("PHASE 2I TASK 1: DIRECT SUBSET PROFILING (CORRECTED)")
    print("=" * 80)

    source_repo = "/home/dheeraj/repository_intelligence_platform"

    test_sizes = [50, 100, 250, 500]
    results = {
        "timestamp": datetime.now().isoformat(),
        "methodology": "Direct analysis of original directory with file filtering",
        "source_repository": source_repo,
        "tests": {}
    }

    for size in test_sizes:
        print(f"\n[Test] Analyzing {size} files...")

        result = profile_subset_analysis(source_repo, size)

        test_key = f"{result['actual_count']}_files"
        results["tests"][test_key] = result

        if result["status"] == "success":
            print(f"  ✓ Completed in {result['elapsed']:.3f}s")
            print(f"    Scanned: {result['scanned_files']}, Parsed: {result['parsed_asts']}")
            print(f"    Entities: {result['entities']}, Relationships: {result['relationships']}")
        else:
            print(f"  ✗ Failed: {result.get('error', 'Unknown error')}")

    # Save results
    output_file = Path(".") / "phase2i_direct_profile_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n" + "=" * 80)
    print(f"Results saved to {output_file}")
    print("=" * 80)

    # Scaling analysis
    print(f"\n[SCALING ANALYSIS - CORRECTED]")
    test_results = []
    for test_key, result in sorted(results["tests"].items()):
        if result["status"] == "success":
            files = result["actual_count"]
            elapsed = result["elapsed"]
            entities = result["entities"]
            relationships = result["relationships"]
            test_results.append((files, elapsed, entities, relationships, result))

    test_results.sort()

    print(f"\nDirect subset analysis:")
    for files, elapsed, entities, rels, result in test_results:
        print(f"  {files:4d} files ({result['total_bytes']:12,} bytes): " +
              f"{elapsed:6.3f}s | {entities:4d} entities, {rels:4d} relationships")

    if len(test_results) >= 2:
        print(f"\nScaling ratios:")
        for i in range(1, len(test_results)):
            f1, t1, e1, r1, _ = test_results[i-1]
            f2, t2, e2, r2, _ = test_results[i]

            ratio_files = f2 / f1
            ratio_time = t2 / t1
            ratio_entities = e2 / e1 if e1 > 0 else 0

            print(f"  {f1:4d} → {f2:4d} files ({ratio_files:.2f}x): " +
                  f"{t1:.3f}s → {t2:.3f}s ({ratio_time:.2f}x time), " +
                  f"{e1} → {e2} entities ({ratio_entities:.2f}x)")

if __name__ == "__main__":
    main()
