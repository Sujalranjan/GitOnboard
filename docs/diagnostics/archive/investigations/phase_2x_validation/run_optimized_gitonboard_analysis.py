#!/usr/bin/env python3
"""
Phase 2J Task 11: Run full GitOnboard (2,421 files) analysis with optimized symbol resolution.

This is the critical test: does the 100x+ optimization of symbol resolution
allow the analysis to complete within reasonable time?
"""
import json
import time
from pathlib import Path
from datetime import datetime

def main():
    print("\n" + "="*80)
    print("PHASE 2J TASK 11: FULL GITONBOARD ANALYSIS WITH OPTIMIZED SYMBOL RESOLUTION")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Repository: /home/dheeraj/repository_intelligence_platform")
    print(f"Expected files: ~2,421")
    print(f"Expected symbols: ~25,920")
    print(f"Optimization: imports_by_file + symbols_by_module indices (100x+ theoretical speedup)")
    print("="*80 + "\n")

    from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
    from backend.intelligence.engine.analyzers import get_default_registry

    source_repo = "/home/dheeraj/repository_intelligence_platform"

    engine = AnalysisEngine(source_repo, get_default_registry())

    print(f"Starting analysis...")
    start_time = time.time()

    try:
        model = engine.run(
            repo_name="GitOnboard-Optimized-Analysis",
            skip_validation=True
        )
        elapsed = time.time() - start_time

        timings = getattr(model, '_analyzer_timings', {})

        # Extract timing details
        details = {}
        for analyzer_name, timing_dict in timings.items():
            if isinstance(timing_dict, dict):
                details[analyzer_name] = {
                    "duration_seconds": timing_dict.get('duration_seconds', 0),
                    "entities_added": timing_dict.get('entities_added', 0),
                    "relationships_added": timing_dict.get('relationships_added', 0)
                }

        result = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "entities": len(model.entities),
            "relationships": len(model.relationships),
            "analyzer_timings": details
        }

        print(f"\n✓ ANALYSIS COMPLETED SUCCESSFULLY!")
        print(f"\nResults:")
        print(f"  Total time: {elapsed:.2f} seconds ({elapsed/60:.1f} minutes)")
        print(f"  Entities extracted: {len(model.entities):,}")
        print(f"  Relationships created: {len(model.relationships):,}")

        print(f"\nAnalyzer Breakdown:")
        callgraph_time = 0
        uses_time = 0
        for name, timing in sorted(details.items(), key=lambda x: x[1]['duration_seconds'], reverse=True):
            dur = timing['duration_seconds']
            ents = timing['entities_added']
            rels = timing['relationships_added']
            pct = (dur / elapsed * 100) if elapsed > 0 else 0

            if 'CallGraphAnalyzer' in name:
                callgraph_time = dur
            if 'UsesAnalyzer' in name:
                uses_time = dur

            print(f"  {name:25s}: {dur:7.2f}s ({pct:5.1f}%) | +{ents:6d} ents, +{rels:6d} rels")

        print(f"\nKey Optimizations:")
        print(f"  CallGraphAnalyzer: {callgraph_time:.2f}s ({callgraph_time/elapsed*100:.1f}%)")
        print(f"  UsesAnalyzer: {uses_time:.2f}s ({uses_time/elapsed*100:.1f}%)")
        print(f"  Combined: {callgraph_time + uses_time:.2f}s ({(callgraph_time+uses_time)/elapsed*100:.1f}%)")

        # Save results
        output_file = Path("phase2j_gitonboard_optimized_results.json")
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2, default=str)

        print(f"\n✓ Results saved to {output_file}")

        # Comparison with Phase 2H prediction
        print(f"\n" + "="*80)
        print(f"COMPARISON WITH PHASE 2H")
        print(f"="*80)
        print(f"Phase 2H prediction: 18+ minutes (never completed)")
        print(f"Phase 2J result: {elapsed/60:.1f} minutes")

        if elapsed < 600:  # Less than 10 minutes
            print(f"\n✓ DRAMATIC IMPROVEMENT: Optimization successful!")
            print(f"  Speedup factor: {18*60 / elapsed:.1f}x")
            return True
        elif elapsed < 1200:  # Less than 20 minutes
            print(f"\n⚠ MODEST IMPROVEMENT: Analysis completes but still slow")
            print(f"  May need deeper optimization")
            return True
        else:
            print(f"\n✗ NO IMPROVEMENT: Analysis still takes too long")
            return False

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n✗ ANALYSIS FAILED after {elapsed:.1f}s")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

        result = {
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "error": str(e)
        }

        output_file = Path("phase2j_gitonboard_optimized_results.json")
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2, default=str)

        return False

if __name__ == "__main__":
    success = main()

    print(f"\n" + "="*80)
    if success:
        print(f"PHASE 2J TASK 11: SUCCESS")
        print(f"Full GitOnboard analysis completed with optimized symbol resolution.")
        print(f"Proceeding to Phase 2J Task 12 (E2E validation)...")
    else:
        print(f"PHASE 2J TASK 11: FAILED")
        print(f"Optimization did not resolve the performance blocker.")
        print(f"Falling back to smaller-repository E2E validation...")
    print(f"="*80 + "\n")
