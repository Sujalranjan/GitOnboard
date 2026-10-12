"""
Benchmark Runner CLI & Orchestrator.
Executes the 60 benchmark questions across the 4 experimental arms:
- Arm 0: Model Prior
- Arm 1: Conventional RAG
- Arm 2: GitOnboard Retrieval-Only
- Arm 3: GitOnboard Agent

Computes deterministic retrieval metrics, invokes LLM semantic judge for answer points/entailment,
classifies trajectory validity and primary failures, calculates repeated-run statistics,
and exports structured JSON and CSV reports to benchmark/results/.
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.database import SessionLocal
from backend.evaluation.baselines import run_conventional_rag, run_gitonboard_rag, run_model_prior
from backend.evaluation.evaluator import (
    attribute_primary_failure,
    calculate_retrieval_metrics,
    calculate_tool_efficiency,
    classify_trajectory_validity,
    evaluate_answer_points_with_judge,
    evaluate_claim_entailment_with_judge,
    extract_citations,
    normalize_path,
)
from backend.evaluation.gitonboard_runner import run_gitonboard_agent
from backend.evaluation.schemas import (
    AnswerMetrics,
    CitationMetrics,
    ExecutionRecord,
    ExecutionStatus,
    ExperimentalArm,
    FailureCategory,
    QuestionBenchmarkSpec,
    RetrievalMetrics,
    ToolEfficiencyMetrics,
    TrajectoryValidity,
)
from backend.repository_tools.tools import RepositoryToolLayer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("BenchmarkRunner")

SUITE_FILES = {
    "gitonboard_backend": Path("benchmark/gitonboard_backend_benchmark.json"),
    "gitonboard_frontend": Path("benchmark/gitonboard_frontend_benchmark.json"),
    "deepguard_backend": Path("benchmark/deepguard_backend_benchmark.json"),
    "deepguard_frontend": Path("benchmark/deepguard_frontend_benchmark.json"),
}


def load_suite_questions(suites: Optional[List[str]] = None) -> List[QuestionBenchmarkSpec]:
    """Loads benchmark questions from the specified suite files."""
    selected = suites or list(SUITE_FILES.keys())
    questions: List[QuestionBenchmarkSpec] = []

    for name in selected:
        p = SUITE_FILES.get(name)
        if not p or not p.exists():
            logger.warning(f"Suite file not found: {p}")
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for item in data:
                questions.append(QuestionBenchmarkSpec(**item))
        except Exception as e:
            logger.error(f"Error loading suite {name}: {e}")

    return questions


def resolve_repository_context(repo_key: str, db: SessionLocal) -> Tuple[str, Optional[int], Optional[Path], Optional[str]]:
    """
    Resolves repository name, analysis_id, repo_root, and prefix for a given benchmark question repository.
    Handles the production configuration difference:
    - deepguard_backend -> Analysis 2 (Azure Blob + Supabase)
    - deepguard_frontend -> Analysis 1 (Azure Blob + Supabase)
    - gitonboard_* -> Local workspace 'f:\\GitOnboard'
    """
    repo_key_lower = repo_key.lower()

    if "deepguard_backend" in repo_key_lower or "deep_guard_backend" in repo_key_lower:
        return "Deep-Guard-Integrated-Backend", 2, None, "app/Deep-Guard-Backend"
    elif "deepguard_frontend" in repo_key_lower or "deep_guard_frontend" in repo_key_lower:
        return "Deep-Guard-Frontend", 1, None, ""
    else:
        # GitOnboard working tree
        ws_root = Path("f:/GitOnboard").resolve()
        return "GitOnboard", None, ws_root, ""


async def evaluate_single_run(
    spec: QuestionBenchmarkSpec,
    arm: ExperimentalArm,
    iteration: int,
    db: Any,
    temperature: float = 0.0,
    max_turns: int = 10,
) -> ExecutionRecord:
    """Executes a single question under a specific experimental arm and evaluates the outcome."""
    repo_name, analysis_id, repo_root, prefix = resolve_repository_context(spec.repository, db)

    tool_layer = RepositoryToolLayer(
        repo_name=repo_name,
        analysis_id=analysis_id,
        db=db,
        repo_root=repo_root,
    )

    run_id = f"{spec.id}_{arm.value}_iter{iteration}_{int(time.time())}"
    timestamp = datetime.utcnow().isoformat()

    logger.info(f"[{spec.id}] Running Arm: {arm.value} (Iteration {iteration})...")

    # 1. Execute according to experimental arm
    try:
        if arm == ExperimentalArm.MODEL_PRIOR:
            answer, traj, files_retrieved, model, dur_ms, p_toks, c_toks = await run_model_prior(
                spec=spec, temperature=temperature
            )
        elif arm == ExperimentalArm.CONVENTIONAL_RAG:
            answer, traj, files_retrieved, model, dur_ms, p_toks, c_toks = await run_conventional_rag(
                spec=spec, tool_layer=tool_layer, temperature=temperature
            )
        elif arm == ExperimentalArm.GITONBOARD_RAG:
            answer, traj, files_retrieved, model, dur_ms, p_toks, c_toks = await run_gitonboard_rag(
                spec=spec, tool_layer=tool_layer, temperature=temperature
            )
        elif arm == ExperimentalArm.GITONBOARD_AGENT:
            answer, traj, files_retrieved, model, dur_ms, p_toks, c_toks = await run_gitonboard_agent(
                spec=spec, tool_layer=tool_layer, max_turns=max_turns, temperature=temperature
            )
        else:
            raise ValueError(f"Unknown arm: {arm}")
        error_msg = None
    except Exception as e:
        logger.error(f"Execution failed for {spec.id} ({arm.value}): {e}", exc_info=True)
        answer = ""
        traj = []
        files_retrieved = []
        model = "error"
        dur_ms = 0.0
        p_toks = 0
        c_toks = 0
        error_msg = str(e)

    # 2. Deterministic Metrics & Execution Failure Handling
    if error_msg is not None:
        exec_status = ExecutionStatus.EXECUTION_ERROR
        if "timeout" in error_msg.lower():
            exec_status = ExecutionStatus.TIMEOUT
        elif "model" in error_msg.lower():
            exec_status = ExecutionStatus.MODEL_ERROR
        elif "tool" in error_msg.lower():
            exec_status = ExecutionStatus.TOOL_ERROR

        return ExecutionRecord(
            run_id=run_id,
            question_id=spec.id,
            repository=spec.repository,
            repository_commit=spec.repository_commit,
            arm=arm,
            model=model,
            temperature=temperature,
            iteration=iteration,
            timestamp=timestamp,
            final_answer="",
            trajectory=traj,
            retrieval_metrics=RetrievalMetrics(),
            tool_efficiency=ToolEfficiencyMetrics(tool_calls=len(traj)),
            citation_metrics=CitationMetrics(),
            answer_metrics=AnswerMetrics(judge_reason=f"Execution error: {error_msg}"),
            execution_status=exec_status,
            trajectory_validity=TrajectoryValidity.EXECUTION_FAILURE,
            primary_failure=FailureCategory.EXECUTION_FAILURE,
            total_duration_ms=dur_ms,
            total_prompt_tokens=p_toks,
            total_completion_tokens=c_toks,
            total_tokens=p_toks + c_toks,
            error=error_msg,
        )

    # Normal execution evaluation
    retrieval_m = calculate_retrieval_metrics(
        retrieved_files=files_retrieved,
        spec=spec,
        repo_scope_prefix=prefix,
    )
    efficiency_m = calculate_tool_efficiency(
        turns=traj,
        required_evidence=spec.required_evidence,
        expected_tools=spec.expected_tool_capabilities,
    )
    # Collect known files from repository manifest if available
    try:
        manifest_files = tool_layer.find_files(pattern="*")
        known_files_set = {normalize_path(f["path"]) for f in manifest_files if "path" in f}
    except Exception:
        known_files_set = None

    citation_m = extract_citations(
        answer=answer,
        spec=spec,
        retrieved_files=files_retrieved,
        known_repo_files=known_files_set,
    )

    # 3. LLM Semantic Judge Evaluation
    (
        points_hit, points_missed, correctness, completeness,
        conf, reason, judge_m, judge_stat, judge_fallback, judge_fail_r
    ) = await evaluate_answer_points_with_judge(
        spec=spec,
        candidate_answer=answer,
    )

    # Aggregate retrieved file contents for claim entailment verification
    retrieved_content_snippets: List[str] = []
    for f in files_retrieved[:5]:
        try:
            read_res = tool_layer.read_file(f, start_line=1, end_line=80)
            c = read_res.get("content") or read_res.get("raw_text") or ""
            if c:
                retrieved_content_snippets.append(f"--- File: {f} ---\n{c[:1500]}")
        except Exception:
            pass

    combined_evidence_text = "\n\n".join(retrieved_content_snippets)
    claims_eval, groundedness, claim_conf = await evaluate_claim_entailment_with_judge(
        retrieved_evidence_text=combined_evidence_text,
        candidate_answer=answer,
    )

    answer_m = AnswerMetrics(
        answer_points_hit=points_hit,
        answer_points_missed=points_missed,
        correctness=correctness,
        completeness=completeness,
        claims_evaluated=claims_eval,
        groundedness=groundedness,
        hallucination_rate=round(1.0 - groundedness, 4),
        judge_score=correctness,
        judge_confidence=conf,
        judge_reason=reason,
        judge_model=judge_m,
        judge_prompt_version="v1",
        judge_status=judge_stat,
        judge_fallback_used=judge_fallback,
        judge_failure_reason=judge_fail_r,
    )


    # 4. Trajectory Validity & Primary Failure Classification
    validity = classify_trajectory_validity(
        correctness=correctness,
        evidence_recall=retrieval_m.evidence_recall,
        threshold=0.75,
    )

    failure_cat = attribute_primary_failure(
        validity=validity,
        retrieval=retrieval_m,
        efficiency=efficiency_m,
        answer_metrics=answer_m,
    )

    return ExecutionRecord(
        run_id=run_id,
        question_id=spec.id,
        repository=spec.repository,
        repository_commit=spec.repository_commit,
        arm=arm,
        model=model,
        temperature=temperature,
        iteration=iteration,
        timestamp=timestamp,
        final_answer=answer,
        trajectory=traj,
        retrieval_metrics=retrieval_m,
        tool_efficiency=efficiency_m,
        citation_metrics=citation_m,
        answer_metrics=answer_m,
        execution_status=ExecutionStatus.SUCCESS,
        trajectory_validity=validity,
        primary_failure=failure_cat,
        total_duration_ms=dur_ms,
        total_prompt_tokens=p_toks,
        total_completion_tokens=c_toks,
        total_tokens=p_toks + c_toks,
        error=None,
    )


def export_results(records: List[ExecutionRecord], output_prefix: Optional[str] = None):
    """Exports records to timestamped JSON and summary comparison CSV files."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    prefix = output_prefix or f"benchmark/results/run_{ts}"
    json_path = Path(f"{prefix}.json")
    csv_path = Path(f"{prefix}_summary.csv")

    # 1. Export Detailed JSON
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_data = [r.model_dump() for r in records]
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    logger.info(f"Wrote detailed JSON results to: {json_path}")

    # 2. Export Summary Comparison CSV
    headers = [
        "run_id", "question_id", "repository", "arm", "iteration", "execution_status",
        "correctness", "completeness", "groundedness", "hallucination_rate",
        "evidence_recall", "relevant_precision", "recall_at_1", "recall_at_3", "recall_at_5", "recall_at_10",
        "decoy_hit", "cross_repo_leakage_rate",
        "trajectory_validity", "primary_failure",
        "tool_calls", "useful_evidence_returned", "retrieval_success_rate", "unique_files_read", "tool_success_rate", "time_to_first_useful_evidence_ms",
        "judge_status", "judge_fallback_used",
        "duration_ms", "total_tokens", "error"
    ]

    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in records:
            writer.writerow([
                r.run_id, r.question_id, r.repository, r.arm.value, r.iteration, r.execution_status.value,
                r.answer_metrics.correctness, r.answer_metrics.completeness,
                r.answer_metrics.groundedness, r.answer_metrics.hallucination_rate,
                r.retrieval_metrics.evidence_recall, r.retrieval_metrics.relevant_evidence_precision,
                r.retrieval_metrics.recall_at_1, r.retrieval_metrics.recall_at_3,
                r.retrieval_metrics.recall_at_5, r.retrieval_metrics.recall_at_10,
                r.retrieval_metrics.decoy_hit, r.retrieval_metrics.cross_repo_leakage_rate,
                r.trajectory_validity.value, r.primary_failure.value,
                r.tool_efficiency.tool_calls, r.tool_efficiency.useful_evidence_returned, r.tool_efficiency.retrieval_success_rate,
                r.tool_efficiency.unique_files_read, r.tool_efficiency.tool_success_rate,
                r.tool_efficiency.time_to_first_useful_evidence_ms or "",
                r.answer_metrics.judge_status, r.answer_metrics.judge_fallback_used,
                r.total_duration_ms, r.total_tokens, r.error or ""
            ])


    logger.info(f"Wrote summary comparison CSV to: {csv_path}")


async def main():
    parser = argparse.ArgumentParser(description="GitOnboard Deterministic Benchmark Evaluation Runner")
    parser.add_argument("--suite", type=str, help="Specific suite (e.g. gitonboard_backend, deepguard_frontend)")
    parser.add_argument("--question", type=str, help="Run single question ID (e.g. GB01, DGF01)")
    parser.add_argument("--arms", type=str, default="model_prior,conventional_rag,gitonboard_rag,gitonboard_agent",
                        help="Comma-separated arms to run: model_prior, conventional_rag, gitonboard_rag, gitonboard_agent")
    parser.add_argument("--runs", type=int, default=1, help="Repetitions per question (default 1)")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM sampling temperature")
    parser.add_argument("--max-turns", type=int, default=10, help="Max tool-calling turns for agent")
    parser.add_argument("--output-prefix", type=str, help="Prefix path for results output")
    args = parser.parse_args()

    suites = [args.suite] if args.suite else None
    all_questions = load_suite_questions(suites)

    if args.question:
        q_target = args.question.strip().upper()
        all_questions = [q for q in all_questions if q.id.upper() == q_target]

    if not all_questions:
        logger.error("No benchmark questions matched selection criteria.")
        sys.exit(1)

    requested_arms = []
    for a in args.arms.split(","):
        a_clean = a.strip().lower()
        if a_clean:
            requested_arms.append(ExperimentalArm(a_clean))

    logger.info(f"Loaded {len(all_questions)} questions. Arms: {[a.value for a in requested_arms]}. Repetitions: {args.runs}.")

    db = SessionLocal()
    records: List[ExecutionRecord] = []

    try:
        for q in all_questions:
            for arm in requested_arms:
                for iter_num in range(1, args.runs + 1):
                    rec = await evaluate_single_run(
                        spec=q,
                        arm=arm,
                        iteration=iter_num,
                        db=db,
                        temperature=args.temperature,
                        max_turns=args.max_turns,
                    )
                    records.append(rec)
    finally:
        db.close()

    export_results(records, output_prefix=args.output_prefix)
    logger.info("Benchmark evaluation run completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
