"""
Evaluation calculation logic for GitOnboard Benchmarks.
Strictly separates:
- 100% Deterministic Metrics: Recall@K, Relevant Precision, Decoy Hit/Rate, Tool Efficiency, Citations, Cross-Repo Isolation.
- LLM Semantic Judge: Answer points hit/missed, claim-level entailment, and reasoning correctness.
"""
from __future__ import annotations
import re
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.evaluation.schemas import (
    AnswerMetrics,
    CitationMetrics,
    ClaimEntailmentResult,
    ExecutionRecord,
    FailureCategory,
    QuestionBenchmarkSpec,
    RetrievalMetrics,
    ToolEfficiencyMetrics,
    TrajectoryTurn,
    TrajectoryValidity,
)
from backend.ai.service import LLMService, get_llm_service
from backend.ai.schemas import LLMRequest, Message, MessageRole

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Deterministic Metrics
# ─────────────────────────────────────────────────────────────────────────────

def normalize_path(p: str) -> str:
    """Normalize file path for consistent cross-platform matching."""
    if not p:
        return ""
    return p.replace("\\", "/").removeprefix("./").lstrip("/").lower().strip()


def calculate_retrieval_metrics(
    retrieved_files: List[str],
    spec: QuestionBenchmarkSpec,
    repo_scope_prefix: Optional[str] = None,
) -> RetrievalMetrics:
    """
    Computes deterministic retrieval metrics:
    - 3-tier precision (Required, Supporting, Decoy)
    - Recall@1, 3, 5, 10
    - Decoy hit & decoy file rate
    - Cross-repo leakage rate
    """
    norm_retrieved = [normalize_path(f) for f in retrieved_files if f]
    # Keep ranked order while removing immediate duplicates for Recall@K
    unique_ranked: List[str] = []
    seen = set()
    for f in norm_retrieved:
        if f not in seen:
            seen.add(f)
            unique_ranked.append(f)

    norm_required = {normalize_path(f) for f in spec.required_evidence if f}
    norm_supporting = {normalize_path(f) for f in spec.supporting_evidence if f}
    norm_decoys = {normalize_path(f) for f in spec.decoy_files if f}

    found_required = [f for f in norm_required if any(f in r or r in f for r in unique_ranked)]
    missed_required = [f for f in norm_required if f not in found_required]
    found_supporting = [f for f in norm_supporting if any(f in r or r in f for r in unique_ranked)]
    used_decoys = [f for f in norm_decoys if any(f in r or r in f for r in unique_ranked)]

    # 1. Evidence Recall: |retrieved ∩ required| / |required|
    evidence_recall = len(found_required) / len(norm_required) if norm_required else 1.0

    # 2. Relevant Evidence Precision: |retrieved ∩ (required ∪ supporting)| / |retrieved|
    # Legitimate supporting files do not penalize precision
    relevant_set = norm_required | norm_supporting
    if unique_ranked:
        relevant_hits = sum(1 for r in unique_ranked if any(rel in r or r in rel for rel in relevant_set))
        relevant_precision = relevant_hits / len(unique_ranked)
    else:
        relevant_precision = 0.0

    # 3. Recall@K: |{r_1, ..., r_K} ∩ required| / |required|
    def calc_recall_at_k(k: int) -> float:
        if not norm_required:
            return 1.0
        top_k = unique_ranked[:k]
        hits = sum(1 for req in norm_required if any(req in r or r in req for r in top_k))
        return hits / len(norm_required)

    # 4. Decoy Metrics
    decoy_hit = 1 if len(used_decoys) > 0 else 0
    decoy_file_rate = len(used_decoys) / len(norm_decoys) if norm_decoys else 0.0

    # 5. Cross-Repository Isolation (Hard Metric)
    cross_repo_files: List[str] = []
    if repo_scope_prefix:
        for r in unique_ranked:
            if not r.startswith(repo_scope_prefix.lower()):
                cross_repo_files.append(r)
    cross_repo_rate = len(cross_repo_files) / len(unique_ranked) if unique_ranked else 0.0

    return RetrievalMetrics(
        retrieved_files=retrieved_files,
        required_evidence_found=found_required,
        required_evidence_missed=missed_required,
        supporting_evidence_found=found_supporting,
        decoy_evidence_used=used_decoys,
        evidence_recall=round(evidence_recall, 4),
        relevant_evidence_precision=round(relevant_precision, 4),
        recall_at_1=round(calc_recall_at_k(1), 4),
        recall_at_3=round(calc_recall_at_k(3), 4),
        recall_at_5=round(calc_recall_at_k(5), 4),
        recall_at_10=round(calc_recall_at_k(10), 4),
        decoy_hit=decoy_hit,
        decoy_file_rate=round(decoy_file_rate, 4),
        cross_repo_files=cross_repo_files,
        cross_repo_leakage_rate=round(cross_repo_rate, 4),
    )


def calculate_tool_efficiency(
    turns: List[TrajectoryTurn],
    required_evidence: List[str],
    expected_tools: Optional[List[str]] = None,
) -> ToolEfficiencyMetrics:
    """
    Computes tool efficiency, error count, and time-to-first-useful-evidence.
    Distinguishes:
    - unnecessary_tool_calls: tools called outside expected_tools that succeeded without causing failure
    - invalid_tool_calls: tools that errored, crashed, or were invalid for the task
    - failed_tool_selections: wrong tool selections that prevented productive retrieval
    """
    norm_required = {normalize_path(f) for f in required_evidence if f}
    expected_tool_set = {t.lower() for t in expected_tools} if expected_tools else None

    # Canonical registered tools in GitOnboard
    registered_tools = {
        "read_file",
        "search_repository",
        "search_code",
        "get_code_relationships",
        "ask_clarification",
    }

    tool_calls = 0
    successful = 0
    failed = 0
    redundant = 0
    unnecessary = 0
    invalid = 0
    failed_selections = 0
    unique_files: Set[str] = set()
    search_iterations = 0
    first_evidence_ms: Optional[float] = None
    elapsed_ms = 0.0

    seen_calls: Set[str] = set()

    for turn in turns:
        elapsed_ms += turn.duration_ms
        if not turn.tool_name:
            continue

        tool_calls += 1
        t_name = turn.tool_name.lower()

        # Check validity: tool not recognized or call returned error
        if t_name not in registered_tools:
            invalid += 1

        if turn.is_success:
            successful += 1
            # If expected_tools provided and tool is harmless but not strictly required
            if expected_tool_set is not None and t_name not in expected_tool_set:
                unnecessary += 1
        else:
            failed += 1
            invalid += 1

        if turn.tool_name in ("search_repository", "search_code"):
            search_iterations += 1

        if turn.tool_name == "read_file" and turn.is_success:
            path = normalize_path(turn.arguments.get("path", ""))
            if path:
                unique_files.add(path)
                if path in norm_required and first_evidence_ms is None:
                    first_evidence_ms = elapsed_ms

        call_sig = f"{turn.tool_name}:{json.dumps(turn.arguments, sort_keys=True)}"
        if call_sig in seen_calls:
            redundant += 1
        else:
            seen_calls.add(call_sig)

    # Failed tool selection: spent 3+ calls on tools with zero evidence retrieved and minimal searching
    if tool_calls >= 3 and len(unique_files) == 0 and search_iterations <= 1:
        failed_selections += 1

    success_rate = successful / tool_calls if tool_calls > 0 else 1.0
    redundancy_rate = redundant / tool_calls if tool_calls > 0 else 0.0

    # Useful evidence returned: turns where useful non-empty observation was obtained
    useful_count = 0
    for turn in turns:
        if not turn.tool_name or not turn.is_success:
            continue
        obs = turn.observation_preview.lower()
        # Non-empty observation that does not indicate 0 matches or error
        if "retrieved 0 files" in obs or "no files found" in obs or "empty" in obs or "{'error':" in obs:
            continue
        useful_count += 1

    retrieval_success_rate = useful_count / tool_calls if tool_calls > 0 else 0.0

    return ToolEfficiencyMetrics(
        tool_calls=tool_calls,
        successful_tool_calls=successful,
        failed_tool_calls=failed,
        redundant_tool_calls=redundant,
        unique_files_read=len(unique_files),
        search_iterations=search_iterations,
        tool_success_rate=round(success_rate, 4),
        useful_evidence_returned=useful_count,
        retrieval_success_rate=round(retrieval_success_rate, 4),
        tool_redundancy_rate=round(redundancy_rate, 4),
        time_to_first_useful_evidence_ms=round(first_evidence_ms, 2) if first_evidence_ms is not None else None,
        unnecessary_tool_calls=unnecessary,
        invalid_tool_calls=invalid,
        failed_tool_selections=failed_selections,
    )


def extract_citations(
    answer: str,
    spec: QuestionBenchmarkSpec,
    retrieved_files: Optional[List[str]] = None,
    known_repo_files: Optional[Set[str]] = None,
) -> CitationMetrics:
    """
    Extracts explicit file citations from the final markdown answer.
    Enforces that valid citations must:
    1. Look syntactically like a source file
    2. Actually exist in the repository (known_repo_files or spec evidence)
    3. Have actually been retrieved/read in this run (if retrieved_files provided)
    
    If no files were retrieved/read in this run (e.g. Model Prior), fabricated citations
    are marked invalid and citation_correctness evaluates to 0.0.
    """
    if not answer:
        return CitationMetrics()

    # Match file patterns like: path/to/file.ext or `path/to/file.ext`
    pattern = re.compile(r'`?([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]{1,6})`?')
    potential_files = pattern.findall(answer)

    cited_files = set()
    for f in potential_files:
        f_norm = normalize_path(f)
        # Filter out common markdown formatting or code tokens
        if "/" in f_norm or f_norm.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".md")):
            cited_files.add(f_norm)

    norm_required = {normalize_path(f) for f in spec.required_evidence}
    norm_supporting = {normalize_path(s) for s in spec.supporting_evidence}
    all_spec_evidence = norm_required | norm_supporting

    norm_retrieved = {normalize_path(rf) for rf in (retrieved_files or [])}

    valid_citations = []
    invalid_citations = []

    for f in cited_files:
        # Check 1: Must exist in repository
        exists_in_repo = False
        if known_repo_files:
            exists_in_repo = any(kf == f or kf.endswith("/" + f) or f.endswith("/" + kf) for kf in known_repo_files)
        else:
            exists_in_repo = any(ev == f or ev.endswith("/" + f) or f.endswith("/" + ev) for ev in all_spec_evidence)

        # Check 2: Must have been actually retrieved/read in this run
        was_retrieved = False
        if norm_retrieved:
            was_retrieved = any(rf == f or rf.endswith("/" + f) or f.endswith("/" + rf) for rf in norm_retrieved)
        else:
            was_retrieved = False

        if exists_in_repo and was_retrieved:
            valid_citations.append(f)
        else:
            invalid_citations.append(f)

    presence = len(cited_files) > 0
    correctness = len(valid_citations) / len(cited_files) if cited_files else 0.0
    completeness_hits = sum(1 for req in norm_required if any(req in v or v in req for v in valid_citations))
    completeness = completeness_hits / len(norm_required) if norm_required else (1.0 if not norm_required else 0.0)

    return CitationMetrics(
        citation_presence=presence,
        cited_files=list(cited_files),
        valid_citations=valid_citations,
        invalid_citations=invalid_citations,
        citation_correctness=round(correctness, 4),
        citation_completeness=round(completeness, 4),
    )


def classify_trajectory_validity(
    correctness: float,
    evidence_recall: float,
    threshold: float = 0.75,
) -> TrajectoryValidity:
    """
    Exhaustive 4-quadrant partition of trajectory validity at threshold tau = 0.75:
    - VALID: correctness >= 0.75 AND evidence_recall >= 0.75
    - LUCKY_CORRECT: correctness >= 0.75 AND evidence_recall < 0.75
    - INSUFFICIENT_EVIDENCE: correctness < 0.75 AND evidence_recall < 0.75
    - INCORRECT: correctness < 0.75 AND evidence_recall >= 0.75
    """
    if correctness >= threshold:
        if evidence_recall >= threshold:
            return TrajectoryValidity.VALID
        return TrajectoryValidity.LUCKY_CORRECT
    else:
        if evidence_recall >= threshold:
            return TrajectoryValidity.INCORRECT
        return TrajectoryValidity.INSUFFICIENT_EVIDENCE


def attribute_primary_failure(
    validity: TrajectoryValidity,
    retrieval: RetrievalMetrics,
    efficiency: ToolEfficiencyMetrics,
    answer_metrics: AnswerMetrics,
) -> FailureCategory:
    """
    Maps non-VALID runs to primary failure category using the revised taxonomy:
    - Distinguishes UNNECESSARY_TOOL_USE (harmless), INVALID_TOOL_USE (errored/unsupported),
      and FAILED_TOOL_SELECTION (wrong tool choice prevented retrieval).
    - Hard isolation safety checks take top priority.
    """
    # 1. Hard Isolation Safety Check: Cross-repository leakage immediately flags failure
    if retrieval.cross_repo_leakage_rate > 0.0:
        return FailureCategory.CROSS_REPO_LEAKAGE

    if validity == TrajectoryValidity.VALID:
        return FailureCategory.NONE

    if answer_metrics.groundedness < 0.5:
        return FailureCategory.HALLUCINATION

    if validity == TrajectoryValidity.INSUFFICIENT_EVIDENCE:
        if efficiency.invalid_tool_calls > 0 or efficiency.failed_tool_calls > 1:
            return FailureCategory.INVALID_TOOL_USE
        if efficiency.failed_tool_selections > 0 or (efficiency.search_iterations <= 1 and efficiency.tool_calls >= 4):
            return FailureCategory.FAILED_TOOL_SELECTION
        if efficiency.tool_calls <= 2:
            return FailureCategory.INSUFFICIENT_SEARCH
        return FailureCategory.RETRIEVAL_FAILURE

    if validity == TrajectoryValidity.INCORRECT:
        if answer_metrics.completeness < 0.5:
            return FailureCategory.ANSWER_INCOMPLETE
        return FailureCategory.REASONING_FAILURE

    if validity == TrajectoryValidity.LUCKY_CORRECT:
        return FailureCategory.RETRIEVAL_FAILURE

    return FailureCategory.REASONING_FAILURE


# ─────────────────────────────────────────────────────────────────────────────
# 2. LLM Semantic Judge (Answer Points & Claim Entailment)
# ─────────────────────────────────────────────────────────────────────────────

JUDGE_POINTS_PROMPT = """You are a rigorous code benchmark evaluation judge.
Evaluate whether the Candidate Answer satisfies each Expected Answer Point for the following question.

Repository: {repository}
Question: {question}

Expected Answer Points:
{expected_points_formatted}

Candidate Answer:
{candidate_answer}

Respond ONLY with a JSON object in this exact schema:
{{
  "points_evaluation": [
    {{
      "point_index": 1,
      "point_text": "...",
      "hit": true,
      "reason": "Brief justification"
    }}
  ],
  "completeness_score": 0.85,
  "confidence": 0.95,
  "overall_summary": "Summary of answer quality"
}}
"""

JUDGE_CLAIMS_ENTAILMENT_PROMPT = """You are a software factual entailment judge.
Determine whether each factual claim made by the assistant is strictly entailed by the Retrieved Code Evidence provided.

Retrieved Code Evidence:
{retrieved_code_evidence}

Candidate Answer:
{candidate_answer}

For each specific factual claim made in the answer about files, functions, routes, tables, or algorithms:
Check whether the provided Retrieved Code Evidence logically entails the claim.
If a claim mentions a component that is not mentioned in the evidence, or claims behavior contrary to the code, it is NOT entailed (hallucination).

Respond ONLY with a JSON object in this exact schema:
{{
  "claims": [
    {{
      "claim_text": "qa_loop.py uses Redis for persistence",
      "referenced_file": "backend/services/qa_loop.py",
      "is_entailed": false,
      "reason": "Evidence does not mention Redis; task persistence uses in-memory or Postgres"
    }}
  ],
  "groundedness_score": 0.8,
  "confidence": 0.9
}}
"""


async def evaluate_answer_points_with_judge(
    spec: QuestionBenchmarkSpec,
    candidate_answer: str,
    llm_service: Optional[LLMService] = None,
) -> Tuple[List[str], List[str], float, float, float, str, str, str, bool, Optional[str]]:
    """
    Invokes LLM Semantic Judge to evaluate expected_answer_points.
    Returns: (points_hit, points_missed, correctness, completeness, confidence, reason, model_name, judge_status, judge_fallback_used, judge_failure_reason)
    """
    if not candidate_answer or not candidate_answer.strip():
        return (
            [], list(spec.expected_answer_points), 0.0, 0.0, 1.0,
            "Empty answer", "empty", "EMPTY_ANSWER", False, None
        )

    service = llm_service or get_llm_service()
    model_name = getattr(service.providers[0], "default_model", "judge") if getattr(service, "providers", None) else "judge"

    formatted_points = "\n".join(f"{i+1}. {pt}" for i, pt in enumerate(spec.expected_answer_points))
    prompt = JUDGE_POINTS_PROMPT.format(
        repository=spec.repository,
        question=spec.question,
        expected_points_formatted=formatted_points,
        candidate_answer=candidate_answer,
    )

    request = LLMRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a strict, deterministic code evaluation judge. Always output valid JSON."),
            Message(role=MessageRole.USER, content=prompt),
        ],
        temperature=0.0,
        max_tokens=2048,
    )

    raw_text = ""
    try:
        response = await service.generate(request)
        raw_text = response.content.strip()
        
        # Robust JSON extraction: search for outermost JSON object
        json_match = re.search(r'(\{[\s\S]*\})', raw_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = raw_text

        data = json.loads(json_str)

        evals = data.get("points_evaluation", [])
        points_hit: List[str] = []
        points_missed: List[str] = []

        for item in evals:
            pt_text = item.get("point_text") or ""
            if item.get("hit"):
                points_hit.append(pt_text)
            else:
                points_missed.append(pt_text)

        total_pts = len(spec.expected_answer_points) or 1
        correctness = round(len(points_hit) / total_pts, 4)
        completeness = round(float(data.get("completeness_score", correctness)), 4)
        confidence = round(float(data.get("confidence", 0.9)), 2)
        reason = data.get("overall_summary", "Judged successfully")

        return points_hit, points_missed, correctness, completeness, confidence, reason, model_name, "SUCCESS", False, None

    except json.JSONDecodeError as jde:
        logger.warning(f"Judge JSON parse failed ({jde}). Raw preview: {raw_text[:200]}")
        status = "PARSE_ERROR"
        fail_reason = f"JSON parse error: {jde}"
    except Exception as e:
        logger.warning(f"Judge evaluation failed ({e}).")
        status = "MODEL_ERROR"
        fail_reason = str(e)

    # Fallback heuristic: check substring containment of expected points
    points_hit = []
    points_missed = []
    ans_lower = candidate_answer.lower()
    for pt in spec.expected_answer_points:
        words = [w.lower() for w in re.findall(r'\b[A-Za-z0-9_]{4,}\b', pt)]
        matches = sum(1 for w in words if w in ans_lower)
        if words and matches / len(words) >= 0.5:
            points_hit.append(pt)
        else:
            points_missed.append(pt)
    total_pts = len(spec.expected_answer_points) or 1
    correctness = round(len(points_hit) / total_pts, 4)
    return (
        points_hit, points_missed, correctness, correctness, 0.5,
        f"Fallback heuristic due to {status}: {fail_reason}", "fallback",
        status, True, fail_reason
    )



async def evaluate_claim_entailment_with_judge(
    retrieved_evidence_text: str,
    candidate_answer: str,
    llm_service: Optional[LLMService] = None,
) -> Tuple[List[ClaimEntailmentResult], float, float]:
    """
    Evaluates semantic claim-level groundedness by checking entailment of generated claims
    against retrieved code text.
    """
    if not candidate_answer or not candidate_answer.strip():
        return [], 1.0, 1.0

    if not retrieved_evidence_text or not retrieved_evidence_text.strip():
        # If no evidence was retrieved, any specific factual claim is ungrounded
        return [
            ClaimEntailmentResult(
                claim_text="Answer generated without evidence",
                is_entailed=False,
                entailment_reason="No code evidence was retrieved in this run.",
            )
        ], 0.0, 1.0

    service = llm_service or get_llm_service()
    prompt = JUDGE_CLAIMS_ENTAILMENT_PROMPT.format(
        retrieved_code_evidence=retrieved_evidence_text[:8000],  # Clamp to fit context safely
        candidate_answer=candidate_answer,
    )

    request = LLMRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a strict code entailment verifier. Always output valid JSON."),
            Message(role=MessageRole.USER, content=prompt),
        ],
        temperature=0.0,
        max_tokens=2048,
    )

    raw_text = ""
    try:
        response = await service.generate(request)
        raw_text = response.content.strip()
        json_match = re.search(r'(\{[\s\S]*\})', raw_text)
        json_str = json_match.group(1) if json_match else raw_text
        data = json.loads(json_str)

        raw_claims = data.get("claims", [])

        claims_out = [
            ClaimEntailmentResult(
                claim_text=c.get("claim_text", ""),
                referenced_file=c.get("referenced_file"),
                is_entailed=bool(c.get("is_entailed", True)),
                entailment_reason=c.get("reason", ""),
            )
            for c in raw_claims
        ]

        if claims_out:
            entailed_count = sum(1 for c in claims_out if c.is_entailed)
            groundedness = round(entailed_count / len(claims_out), 4)
        else:
            groundedness = 1.0

        confidence = round(float(data.get("confidence", 0.9)), 2)
        return claims_out, groundedness, confidence

    except Exception as e:
        logger.warning(f"Claim entailment check failed: {e}")
        return [], 0.8, 0.5
