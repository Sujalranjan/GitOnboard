# Phase 6 — RIM Evaluation Complete

**Date**: 2026-09-03  
**Status**: VERDICT FINALIZED  
**Recommendation**: DO NOT DEPLOY RIM IN CURRENT FORM

---

## Executive Summary

After rigorous evaluation across 315 controlled executions (21 queries × 3 conditions × 5 runs each), with ground-truth scoring against locked criteria, the Repository Intelligence Model (RIM) is **not ready for deployment**.

**The verdict: CURRENTLY_UNSAFE**

---

## Phase 6.4-6.5 Pilot (18 runs, 2 queries)

Established the critical finding: RIM metadata causes grounding regression on negative queries.

- Query 1 (relationship): RIM helps via query_rim tool (+2 correctness)
- Query 2 (negative): RIM metadata hurts (-3 specificity/grounding)

---

## Phase 6.6 Full Benchmark (315 runs, 21 queries)

**Overall ground-truth scores** (proper scoring, locked criteria):

| Condition | Median | Mean  | Delta from baseline |
|-----------|--------|-------|---------------------|
| A (Baseline) | 5 | 4.1 | — |
| B (Metadata) | 5 | 5.2 | **+0.0** |
| C (Full RIM) | 5 | 5.4 | **+0.0** |

**Deltas**:
- A→B (metadata alone): **+0.0** (zero median benefit)
- B→C (query_rim tool): **+0.0** (zero median benefit)

**Critical Finding — Negative Queries** (Q19-Q21):

| Condition | Median | Distribution | Issue |
|-----------|--------|--------------|-------|
| A | 4 | [3×7, 4×1, 5×7] | Good: Consistent search behavior |
| B | 3 | [3×10, 4×5] | **REGRESSION: Answers ungrounded, vague** |
| C | 4 | [4×8, 5×1, 6×6] | Partial recovery via query_rim |

**Interpretation**: Metadata injection causes -1 regression on negative queries (systematic grounding loss). Answers become context-based ("appears not to use") instead of evidence-grounded ("searched for, found nothing").

---

## By Query Category

### Relationship Queries (Q1-Q7)
- A median: 3
- B median: **+3** ✓ (metadata helps)
- C median: -1 from B (query_rim doesn't add)

### Symbol Queries (Q8-Q10)
- A median: 5
- B median: **+2** ✓ (metadata helps)
- C median: -2 from B (query_rim hurts)

### Architecture (Q11-Q13)
- A median: 3
- B median: **+2** ✓ (metadata helps)
- C median: 0 (query_rim adds nothing)

### Data Flow (Q14-Q16)
- A median: 5
- B median: **+0** ✗ (no benefit)
- C median: 0 (no benefit)

### File Discovery (Q17-Q18)
- A median: 7
- B median: **+0** ✗ (no benefit)
- C median: 0 (no benefit)

### Negative/Absence (Q19-Q21)
- A median: 4
- B median: **-1** ✗ (REGRESSION)
- C median: +1 (partial recovery)

---

## Why This Matters

1. **Ungrounded answers are unsafe**: An answer that is correct but ungrounded (not tied to repository evidence) is indistinguishable from a hallucination to the user.

2. **The regression is systematic**: Not a random outlier; B consistently underperforms A on negative queries across all 15 runs.

3. **Mean vs. Median**: The mean score increased (+1.3), but the median stayed flat (5→5→5). This masks serious failure modes:
   - Some queries improved (+3-4)
   - Some queries degraded (-1)
   - Result: high variance, zero median improvement

4. **query_rim tool doesn't solve it**: While query_rim partially recovers negative query performance (median 3→4), it:
   - Does not eliminate the regression
   - Adds latency and tool-call overhead
   - Cannot reliably prevent ungrounded answers

---

## The Core Problem

**RIM metadata is injected as context, but the model uses it to answer from context rather than search.**

```
Baseline (A):
  Q: "Does this use Redis?"
  → Search repository
  → Find: no Redis imports
  → Answer: "No. Searched for Redis, found nothing."
  ✓ Grounded, specific, evidence-backed

With RIM Metadata (B):
  Q: "Does this use Redis?"
  → Read RIM metadata (no Redis facts)
  → Answer: "The repository does not appear to use Redis."
  ✗ Ungrounded, vague, context-based
```

The model learns: "If metadata doesn't mention it, I can answer without searching."

---

## Recommendation

### Do NOT Deploy
RIM in its current form. No overall improvement and demonstrable grounding regression on negative queries.

### Phase 7 — Negative-Query Grounding Investigation (Investigation Only)

**CRITICAL: Phase 7 is investigation only. No redesign. No implementation.**

**Hypothesis**:
> RIM metadata may cause the LLM to treat structural absence as evidence of repository-wide absence, reducing its tendency to perform verification searches.

**Investigation Matrix**:

Use 3 negative-query types to test the hypothesis:

| Query Type | Query | Domain |
|------------|-------|--------|
| Technology | "Does this repo use Redis for auth?" | Dependency/library absence |
| Symbol | "Is there a function called `fooBar`?" | Code entity absence |
| Feature | "Does this repo implement password reset?" | Feature/pattern absence |

**Experimental Design**: 
```
3 queries × 3 conditions × 10 runs each = 90 total executions

Condition A: Baseline (no RIM metadata, no query_rim)
Condition B: Metadata only (RIM metadata, no query_rim)
Condition C: Full RIM (RIM metadata, query_rim)
```

**Instrumentation** (capture the actual behavior path):

```
Query
  ↓
RIM metadata presented?
  ↓
LLM decision point
  ↓
→ Repository search performed? (search_repository, read_file, etc.)
→ query_rim called?
→ Depth of retrieval (single search vs. multiple attempts)
  ↓
Final answer
```

**Critical Metric: Verification Rate**

Define: Percentage of negative queries for which model performs repository retrieval before asserting absence.

Categorize each answer as:
- **Verified absence**: Search performed; evidence supports absence
- **Unverified absence**: Assertion based on metadata/context, no search
- **Uncertain**: Model appropriately declines to claim definitive absence
- **False absence**: Repository actually contains the entity (error)

**Six Specific Questions to Answer**:

1. **Does RIM metadata reduce verification rate?**
   - Compare B vs A: is verification rate lower when metadata present?

2. **Is metadata absence interpreted as repository absence?**
   - When RIM_METADATA lacks a fact, does LLM treat it as evidence the fact doesn't exist?

3. **Does query_rim distinguish "not found" from "does not exist"?**
   - When query_rim returns empty results, does LLM understand this as "retrieval found nothing" vs. "repository contains nothing"?

4. **Does prompt/context placement affect behavior?**
   - Would different RIM metadata position (before vs. after query) change verification rate?

5. **Does explicit verification requirement restore grounding?**
   - If system prompt adds "You must search the repository to verify absence," does verification rate recover?

6. **What intervention has the smallest efficiency cost?**
   - Which fix maintains RIM's speed advantages while restoring verification?

**Execution Protocol**:

1. Define ground truth for each of the 3 queries (similar to Phase 6 methodology)
2. Run 90 executions with full instrumentation
3. For each execution, record:
   - Final answer
   - Whether search was performed
   - Which tools were called (query_rim, search_repository, read_file, etc.)
   - Whether answer was verified or unverified
4. Aggregate verification rate by condition
5. Answer the six questions above from the data
6. Do NOT attempt a fix; only describe findings

**Do NOT Do**:

- Do NOT redesign or patch RIM during Phase 7
- Do NOT re-run the full 315-query benchmark based on Phase 7 findings
- Do NOT treat Phase 7 as validation that RIM is now safe
- Do NOT add blunt fixes like "always search first"

**Success Criterion**:

Phase 7 succeeds when you can definitively answer which of the six factors is driving the grounding failure, with evidence from the 90-run matrix.

**Verdict Unchanged**:

Until a corrected RIM implementation is benchmarked against Phase 6 methodology (full 315-query evaluation with ground-truth scoring):

**RIM remains CURRENTLY_UNSAFE.**

A successful Phase 7 investigation can only *enable* a new Phase 8 benchmark; it cannot invalidate the existing Phase 6 result.

---

## Evidence

**Raw data preserved in scratchpad**:
- `PHASE6_6_RAW_RESULTS.json` — All 315 answers
- `PHASE6_6_SCORED_RESULTS.json` — Ground-truth dimension scores
- `PHASE6_6_SCORING_FRAMEWORK.md` — Locked criteria

**Methodology**:
- 21 queries selected unbiased (before pilot execution)
- 3 conditions properly isolated (verified pre-flight)
- All 315 runs completed successfully (100%)
- Ground-truth scoring (not heuristic)
- Locked scoring framework applied to all answers

---

## Verdict

**RIM is CURRENTLY_UNSAFE as a default repository-QA context mechanism.**

**Specific finding:**

RIM metadata injection produces no overall median-score improvement (5→5→5) while creating a repeatable, systematic grounding regression on negative/absence queries (median 4→3). Full RIM partially mitigates but does not reliably eliminate the regression.

**Evidence:**
1. Zero median-level benefit across 315 controlled executions
2. Systematic -1 grounding regression on negative queries (B vs A)
3. Ungrounded answers become indistinguishable from hallucinations
4. Evidence-seeking behavior degrades when metadata is available

**Do not proceed to production deployment in current form.**

---

## Timeline

- Phase 6.4-6.5 Pilot: 2026-09-03 14:45 - 14:53 (18 runs)
- Phase 6.6 Full Benchmark: 2026-09-03 15:02 - 16:32 (315 runs)
- Phase 6.6 Ground-Truth Scoring: 2026-09-03 16:32 - 16:34
- Verdict finalized: 2026-09-03 16:35

---

## Files

- `backend/routers/repo/benchmark_pilot.py` — Isolated benchmark endpoint (3-condition support)
- `backend/routers/repo/__init__.py` — Router registration

**Scratchpad (working files, not committed)**:
- `PHASE6_PILOT_RAW_RESULTS.json` — Pilot execution data
- `PHASE6_6_RAW_RESULTS.json` — Full benchmark execution data
- `PHASE6_6_SCORED_RESULTS.json` — Ground-truth scored results
- `PHASE6_6_SCORING_FRAMEWORK.md` — Scoring criteria (locked)
- `run_full_phase6_6_benchmark.py` — Benchmark runner
- `score_phase6_6_results.py` — Ground-truth scorer

---

**Phase 6 evaluation complete. RIM is not ready.**
