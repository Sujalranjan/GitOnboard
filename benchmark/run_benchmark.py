"""
Repository Intent Benchmark Evaluation Runner
Runs the 139-case repository intent benchmark dataset against IntentRouter.
Generates metrics by intent, difficulty, and case type.
Saves detailed JSON and Markdown results.
"""
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

# Force UTF-8 on stdout if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure reasonable timeout for LLM calls during benchmark
os.environ["OLLAMA_TIMEOUT"] = "30.0"

from backend.agent.intent.router import IntentRouter
from backend.agent.intent.contracts import Intent


def run_benchmark(csv_path: Path, output_dir: Path):
    if not csv_path.exists():
        print(f"Error: Dataset not found at {csv_path}", flush=True)
        return

    router = IntentRouter()

    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    total_cases = len(records)
    print(f"Loaded {total_cases} benchmark cases from {csv_path.name}", flush=True)
    print("Executing intent classification benchmark...\n", flush=True)

    results = []
    correct_count = 0
    start_time = time.time()

    intent_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    difficulty_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    case_type_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    method_stats = defaultdict(int)
    mismatches = []

    for idx, row in enumerate(records, 1):
        case_id = row["id"]
        question = row["question"]
        expected_intent = row["intent"].strip().lower()
        difficulty = row.get("difficulty", "unknown").strip().lower()
        case_type = row.get("case_type", "unknown").strip().lower()

        # Run classification
        t0 = time.time()
        res = router.classify(question)
        elapsed_ms = (time.time() - t0) * 1000

        predicted_intent = res.intent.value.lower()
        is_correct = predicted_intent == expected_intent

        status_sym = "[OK]  " if is_correct else "[FAIL]"
        print(f"[{idx:03d}/{total_cases:03d}] {status_sym} ID:{case_id} [{difficulty.upper():<6}] Exp:{expected_intent:<9} Pred:{predicted_intent:<9} ({res.classification_method:<13} {elapsed_ms:>6.1f}ms) | {question[:45]}", flush=True)

        if is_correct:
            correct_count += 1
        else:
            mismatches.append({
                "id": case_id,
                "question": question,
                "expected": expected_intent,
                "predicted": predicted_intent,
                "confidence": res.confidence,
                "method": res.classification_method,
                "reason": res.reason,
                "difficulty": difficulty,
                "case_type": case_type,
            })

        intent_stats[expected_intent]["total"] += 1
        if is_correct:
            intent_stats[expected_intent]["correct"] += 1

        difficulty_stats[difficulty]["total"] += 1
        if is_correct:
            difficulty_stats[difficulty]["correct"] += 1

        case_type_stats[case_type]["total"] += 1
        if is_correct:
            case_type_stats[case_type]["correct"] += 1

        method_stats[res.classification_method] += 1

        results.append({
            "id": case_id,
            "question": question,
            "expected_intent": expected_intent,
            "predicted_intent": predicted_intent,
            "confidence": res.confidence,
            "method": res.classification_method,
            "reason": res.reason,
            "difficulty": difficulty,
            "case_type": case_type,
            "is_correct": is_correct,
            "latency_ms": round(elapsed_ms, 2),
        })

    total_time = time.time() - start_time
    accuracy = (correct_count / total_cases) * 100 if total_cases > 0 else 0.0

    print(f"\n==================================================", flush=True)
    print(f"BENCHMARK RESULTS: {correct_count}/{total_cases} Correct ({accuracy:.2f}%)", flush=True)
    print(f"Total time: {total_time:.2f}s (Avg: {total_time/total_cases*1000:.1f}ms/query)", flush=True)
    print(f"==================================================", flush=True)

    print("\n--- Accuracy by Intent ---", flush=True)
    for intent, data in sorted(intent_stats.items()):
        acc = (data["correct"] / data["total"]) * 100 if data["total"] > 0 else 0.0
        print(f"  {intent.upper():<12}: {data['correct']:>2}/{data['total']:>2} ({acc:>6.2f}%)", flush=True)

    print("\n--- Accuracy by Difficulty ---", flush=True)
    for diff, data in sorted(difficulty_stats.items()):
        acc = (data["correct"] / data["total"]) * 100 if data["total"] > 0 else 0.0
        print(f"  {diff.capitalize():<12}: {data['correct']:>2}/{data['total']:>2} ({acc:>6.2f}%)", flush=True)

    print("\n--- Accuracy by Case Type ---", flush=True)
    for ct, data in sorted(case_type_stats.items()):
        acc = (data["correct"] / data["total"]) * 100 if data["total"] > 0 else 0.0
        print(f"  {ct:<22}: {data['correct']:>2}/{data['total']:>2} ({acc:>6.2f}%)", flush=True)

    print("\n--- Classification Method Distribution ---", flush=True)
    for method, count in sorted(method_stats.items()):
        pct = (count / total_cases) * 100
        print(f"  {method:<16}: {count:>3}/{total_cases} ({pct:>5.1f}%)", flush=True)

    # Output JSON summary
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_cases": total_cases,
        "correct": correct_count,
        "accuracy_pct": round(accuracy, 2),
        "total_duration_sec": round(total_time, 2),
        "intent_accuracy": {
            k: {
                "total": v["total"],
                "correct": v["correct"],
                "accuracy_pct": round((v["correct"] / v["total"]) * 100, 2) if v["total"] > 0 else 0.0,
            }
            for k, v in intent_stats.items()
        },
        "difficulty_accuracy": {
            k: {
                "total": v["total"],
                "correct": v["correct"],
                "accuracy_pct": round((v["correct"] / v["total"]) * 100, 2) if v["total"] > 0 else 0.0,
            }
            for k, v in difficulty_stats.items()
        },
        "case_type_accuracy": {
            k: {
                "total": v["total"],
                "correct": v["correct"],
                "accuracy_pct": round((v["correct"] / v["total"]) * 100, 2) if v["total"] > 0 else 0.0,
            }
            for k, v in case_type_stats.items()
        },
        "method_distribution": dict(method_stats),
        "mismatches_count": len(mismatches),
        "mismatches": mismatches,
        "detailed_results": results,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "benchmark_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Output Markdown report
    md_path = output_dir / "benchmark_results.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Repository Intent Classification Benchmark Report\n\n")
        f.write(f"- **Evaluated At**: {summary['timestamp']}\n")
        f.write(f"- **Dataset**: `{csv_path.name}` ({total_cases} cases)\n")
        f.write(f"- **Overall Accuracy**: **{accuracy:.2f}%** ({correct_count}/{total_cases})\n")
        f.write(f"- **Total Runtime**: {total_time:.2f}s\n\n")

        f.write(f"## 1. Accuracy by Intent\n\n")
        f.write(f"| Intent | Correct | Total | Accuracy |\n")
        f.write(f"| :--- | :---: | :---: | :---: |\n")
        for k, v in sorted(summary["intent_accuracy"].items()):
            f.write(f"| **{k.upper()}** | {v['correct']} | {v['total']} | **{v['accuracy_pct']}%** |\n")

        f.write(f"\n## 2. Accuracy by Difficulty\n\n")
        f.write(f"| Difficulty | Correct | Total | Accuracy |\n")
        f.write(f"| :--- | :---: | :---: | :---: |\n")
        for k, v in sorted(summary["difficulty_accuracy"].items()):
            f.write(f"| **{k.capitalize()}** | {v['correct']} | {v['total']} | **{v['accuracy_pct']}%** |\n")

        f.write(f"\n## 3. Accuracy by Case Type\n\n")
        f.write(f"| Case Type | Correct | Total | Accuracy |\n")
        f.write(f"| :--- | :---: | :---: | :---: |\n")
        for k, v in sorted(summary["case_type_accuracy"].items()):
            f.write(f"| `{k}` | {v['correct']} | {v['total']} | **{v['accuracy_pct']}%** |\n")

        f.write(f"\n## 4. Classification Method Distribution\n\n")
        f.write(f"| Method | Count | Percentage |\n")
        f.write(f"| :--- | :---: | :---: |\n")
        for k, v in sorted(summary["method_distribution"].items()):
            f.write(f"| `{k}` | {v} | {(v/total_cases)*100:.1f}% |\n")

        if mismatches:
            f.write(f"\n## 5. Mismatched Cases ({len(mismatches)})\n\n")
            f.write(f"| ID | Question | Expected | Predicted | Method | Reason |\n")
            f.write(f"| :---: | :--- | :---: | :---: | :---: | :--- |\n")
            for m in mismatches:
                f.write(f"| {m['id']} | `{m['question']}` | **{m['expected']}** | `{m['predicted']}` | {m['method']} | {m['reason']} |\n")

    print(f"\nSaved benchmark results to:", flush=True)
    print(f"  - {json_path}", flush=True)
    print(f"  - {md_path}", flush=True)


if __name__ == "__main__":
    csv_file = root_dir / "benchmark" / "repository_intent_benchmark.csv"
    out_dir = root_dir / "benchmark"
    run_benchmark(csv_file, out_dir)
