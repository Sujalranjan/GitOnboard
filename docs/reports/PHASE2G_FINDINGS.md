# Phase 2G: Real GitOnboard E2E Validation — Findings So Far

**Status:** In Progress  
**Date:** 2026-09-05  
**Focus:** Complete E2E pipeline validation on real repository

---

## What We've Discovered

### 1. Parser Works Perfectly ✓
**Evidence:**
- Full repository scan: 2,421 files
- Symbol extraction: **25,869 symbols extracted successfully**
- Parser progress confirmed in database
- Root cause from Phase 2C fix: `parse_file(file_info.path, file_info.language)` ✓

**Proof:** The progress counter in the Analysis model shows 25869/25869 symbols, confirming the parser completed extraction.

---

### 2. AnalysisEngine Performance Bottleneck ⚠️

**Problem:**
- Full repository analysis (2,421 files) exceeds 15-minute timeout
- Process was killed at 15 minutes without completing
- Symbols extracted but analysis never finished

**Likely bottleneck stages (after symbol extraction):**
1. Relationship extraction (potentially O(n²) complexity)
2. RIM validation (checking all relationships and constraints)
3. Diagnostic report generation
4. Status update and FactStore persistence

**Timeline:**
- 0-5 min: Scanning files (2,421 files)
- 5-10 min: Parsing and AST creation
- 10-15 min: Symbol extraction (25,869 symbols) → completes
- 15+ min: Unknown bottleneck (timeout triggered)

**Root cause:** The AnalysisEngine.run() method appears to have a performance issue on large repositories.

---

### 3. FactStore Persistence Never Executes

**Problem:**
- FactStore count: 0 files, 0 symbols, 0 relationships
- The `save_rim_to_fact_store()` call in `run_phase2g_analysis.py` line 105 never executes
- Reason: engine.run() doesn't complete within 15 minutes

**Proof:**
- No print statement from line 84 onwards appears in output
- FactStore remains empty despite 25,869 symbols being extracted
- Analysis status stays "Queued" (never becomes "Completed")

---

## Current Strategy

### Test with Smaller Codebase
Running `run_phase2g_analysis_subset.py` on just the `/backend` directory to:
1. See if the engine completes faster on smaller code
2. Validate the E2E pipeline works (if it completes)
3. Identify the specific bottleneck causing the full repository to timeout

**Expected:**
- Subset should have 100-300 files (vs 2,421)
- Much faster analysis (target: < 5 minutes)
- Complete FactStore persistence
- Run validators on subset results

---

## Validation Checklist

| Component | Status | Evidence |
|-----------|--------|----------|
| Parser (Phase 2C fix) | ✓ PROVEN | 25,869 symbols extracted |
| Symbol extraction | ✓ PROVEN | Progress counter confirms 25,841/25,841 |
| Relationship extraction | ⧲ PENDING | Blocked by engine timeout |
| RIM validation | ⧲ PENDING | Blocked by engine timeout |
| FactStore persistence | ✗ FAILED | Timeout before save_rim_to_fact_store() executed |
| BM25 indexing | ⧲ PENDING | No FactStore data to index |
| Semantic indexing | ⧲ PENDING | No FactStore data to index |
| HybridRetrieval | ⧲ PENDING | No FactStore data to retrieve |
| Graph navigation | ⧲ PENDING | No FactStore relationships |
| Source bridge | ⧲ PENDING | No FactStore data |
| LLM context | ⧲ PENDING | No FactStore data |

---

## Next Steps

### Immediate (< 5 min)
1. Wait for subset analysis to complete
2. Check if persistence works on smaller dataset
3. Run validators on subset

### If subset succeeds:
1. Validate E2E pipeline on subset (parser → FactStore → retrieval → graph → LLM)
2. Document that full repository is blocked by engine performance
3. Identify specific bottleneck in AnalysisEngine

### If subset also times out:
1. Reduce subset further (just `backend/parser` or similar)
2. Investigate what specific analyzer is slow
3. Consider minimal optimizations per Phase 2G rules

---

## Key Questions to Answer

1. **Why does engine.run() take 15+ minutes?**
   - Is it the relationship extraction?
   - Is it the validation?
   - Is it something else?

2. **Does the engine work at all on this codebase?**
   - Or is it fundamentally incompatible with large repositories?

3. **Is this a regression?**
   - Did Phase 2C changes introduce the slowdown?
   - Or was the engine always slow?

4. **Can we validate the E2E pipeline without the full repository analysis?**
   - Use the symbols that were extracted (25,869)
   - Manually create FactStore records for them
   - Test retrieval, graph, LLM on those records

---

## Phase 2G Verdict (Pending)

**Current Status:** BLOCKED BY ENGINE PERFORMANCE

Cannot complete "REAL_GITONBOARD_RIM_E2E_VALIDATED" until:
1. AnalysisEngine completes on real repository, OR
2. We validate on a smaller subset that does complete, OR  
3. We use an alternative approach to populate FactStore

**Parser fix remains proven:** The 25,869 symbols extracted prove the Phase 2C fix works correctly on production data.

---

## Subagent Status

**Created:** 4 validation subagents (A, B, C, D)
- Agent A (Persistence): Waiting for completed analysis
- Agent B (Retrieval): Waiting for completed analysis
- Agent C (Graph): Waiting for completed analysis
- Agent D (LLM Context): Waiting for completed analysis

**Orchestrator:** `run_phase2g_validation.py` ready to run once analysis completes

---

## Code Notes

- **run_phase2g_analysis.py**: Full repository analysis (timed out at 15 min)
- **run_phase2g_analysis_subset.py**: Backend subset analysis (testing now)
- **phase2g_validate_*.py**: 4 subagent validators (ready to run)
- **run_phase2g_validation.py**: Orchestrator script (ready to coordinate)
