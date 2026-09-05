# Phase 2A: Root Cause Analysis — RIM Retrieval Failure

## Diagnostic Executed

Ran `run_phase2a_retrieval_trace.py` to trace "How does authentication work?" query through HybridRetriever at each stage.

---

## EXACT ROOT CAUSE

**BM25 (Lexical) Retrieval is Non-Functional for Natural Language Queries.**

```
Query: "How does authentication work?"

Exact Search:     7 candidates (routes with exact path match)
BM25 Search:      0 candidates ← FAILURE
Semantic Search: 30 candidates ← WORKING (Chroma)
RRF Fusion:      30 candidates (from semantic alone)
Final Results:   10 candidates (files, no symbols)
```

**Evidence:**
- BM25 index IS loaded (`✓ Loaded`)
- BM25 index HAS content (`corpus_size: 1369 documents`)
- BM25 search returns ZERO results for the query
- Chroma semantic search returns 30 results for the same query
- Query contains relevant terms ("authentication") but BM25 finds nothing

---

## Retrieval Trace Table

| Stage               | Input Query                      | Candidates | Status  |
| ------------------- | -------------------------------- | ----------: | ------- |
| FactStore Baseline  | All auth-related symbols         |           0 | ✗ Empty |
| Exact Facts         | Query term matching              |           7 | ✓       |
| BM25 (Lexical)      | "How does authentication work?"  |           0 | ✗ FAIL  |
| Semantic (Chroma)   | "How does authentication work?"  |          30 | ✓       |
| Reciprocal Rank Fus | Ranked lists                     |          30 | ✓       |
| Fact Store Expansion| 20 candidates → relationships    |           0 | ✗       |
| Final Results       | After conversion to schema       |          10 | ⚠ Partial |

---

## Index Status

### BM25 Index
- **Status:** ✓ Loaded
- **Corpus Size:** 1369 documents
- **Document Count:** 1369
- **Average Doc Length:** 12.2 tokens (very short)
- **Issue:** Query matching returns 0 results despite loaded corpus

**Interpretation:** The BM25 corpus contains only short documents (likely file paths or file names), averaging 12.2 tokens each. A natural language query "How does authentication work?" (7 tokens, semantic query) cannot be matched against this corpus effectively.

### Chroma (Semantic Search)
- **Status:** ✓ Available and Working
- **Results for Query:** 30 candidates
- **Sample Results:**
  - `auth.py` (distance: 0.67)
  - `AuthContext.tsx` (distance: 0.69)
  - `test_auth_hardening.py` (distance: 0.72)

**Interpretation:** Chroma is successfully matching the semantic meaning of "How does authentication work?" to auth-related files.

---

## Critical Findings

### Finding 1: BM25 Tokenization Mismatch

**Problem:** BM25 corpus is too short (avg 12.2 tokens/doc) to match natural language queries.

**Hypothesis:** BM25 corpus contains only file names or paths, not full descriptions or content snippets.

**Example:**
- BM25 Document: `"backend/routers/auth.py"`
- Query: `"How does authentication work?"`
- Match: FAIL (no keyword overlap despite both being auth-related)

**Evidence:** Exact search finds 7 results (direct path matching), but BM25 finds 0.

### Finding 2: FactStore Symbols Are Not in BM25

**Problem:** Query for "How does authentication work?" returns 0 BM25 results.

**Analysis:** 
- FactStore query for auth symbols: 0 results
- BM25 query for auth symbols: 0 results
- Database inspection found 6 auth symbols, BUT they were in a DIFFERENT analysis_id

**Hypothesis:** The GitOnboard repository was not analyzed at the SYMBOL level. Analysis 14 contains only FILES and ROUTES, no SYMBOL entities.

**Confirmation:**
```
[FactStore Baseline]
  Total auth symbols: 0  ← Query for FactSymbol.name LIKE '%auth%' returns nothing
```

This explains why `build_rim_metadata_block()` at line 247 returns "No structural facts could be resolved."

### Finding 3: Expansion Fails on File-Level Results

**Problem:** Even though Chroma returns 30 file-level candidates, expansion produces 0 relationships.

**Evidence from Logs:**
```
[RIM EXPAND] Failed to resolve candidate: name=auth.py, file=backend/routers/auth.py, type=FILE
[RIM EXPAND] Seed[7] auth.py has no symbol_id, skipping expansion
[RIM EXPAND] Total expansion complete: 0 relationships found, 0 new entities added
```

**Root Cause:** The FactStore expansion requires SYMBOL entities to traverse relationships. File-level matches have no associated symbols, so graph traversal produces nothing.

---

## Why "No Structural Facts Could Be Resolved"

The complete failure chain:

```
1. Query: "How does authentication work?"
   ↓
2. BM25 Search: 0 results
   (corpus is filename-only, cannot match natural language)
   ↓
3. Semantic Search: 30 results (FILES, not SYMBOLS)
   (Chroma finds auth-related file names)
   ↓
4. RRF Fusion: 30 results (FILES)
   (Fused list is file-level)
   ↓
5. Expansion: 0 relationships
   (Cannot expand FILES → no symbol_id for graph traversal)
   ↓
6. build_rim_metadata_block(): "No structural facts could be resolved"
   (Cannot convert file results into relationship facts)
   ↓
7. LLM Prompt: Empty RIM metadata block
   (LLM has only file list from ContextAssembler, no relationships)
```

---

## Chroma Status

**Semantic search is WORKING.**

Chroma returned:
- 30 candidates for auth query
- Reasonable distance scores (0.67–0.72)
- Relevant results (auth-related files)

**Chroma is currently the ONLY working retrieval method** because:
- It can match semantic meaning ("authentication concepts")
- It's not hampered by tokenization of short file names
- It returns results even though FactStore lacks symbol-level analysis

---

## Fix Required

This is a **multi-part problem** that cannot be fixed by a single change:

### Part 1: FactStore Analysis Completeness
- **Issue:** GitOnboard analysis lacks SYMBOL-level extraction
- **Evidence:** `SELECT COUNT(*) FROM fact_symbols WHERE name LIKE '%auth%'` returns 0
- **Root Cause:** Analysis job may not have completed symbol extraction
- **Fix:** Re-run analysis with symbol extraction enabled

### Part 2: BM25 Corpus Quality
- **Issue:** BM25 corpus contains only filenames (12.2 avg tokens), cannot match natural queries
- **Evidence:** "How does authentication work?" finds 0 BM25 results despite relevant files existing
- **Root Cause:** BM25 index built from file metadata only, not symbol-level content
- **Fix:** If symbols are extracted (Part 1), rebuild BM25 to include symbol names and descriptions

### Part 3: Expansion Pipeline Fragility
- **Issue:** File-level matches cannot be expanded into relationship facts
- **Evidence:** 30 semantic results → 0 relationships after expansion
- **Root Cause:** Expansion designed for symbols, fails gracefully on files
- **Fix:** Hybrid expansion that can work with both symbols and files, OR ensure all queries return symbols

### Part 4: Fallback Strategy
- **Issue:** When BM25 fails and Chroma returns files-only, system cannot produce RIM metadata
- **Evidence:** RIM metadata block empty despite semantic results available
- **Root Cause:** No fallback from semantic→symbol resolution
- **Fix:** Implement fallback that can use file-level results when symbol expansion unavailable

---

## Smallest Immediate Fix

Given the constraints:

**Enable graceful degradation in `build_rim_metadata_block()`:**

When semantic search returns file-level results but symbol expansion fails:
1. Still return the file list as meaningful repository context
2. Include file path, file purpose, file size in metadata
3. Allow LLM to reason about files even without relationships

**This would make:**
```
RIM_METADATA: Auth-related files found:
  - backend/routers/auth.py (150 lines, router layer)
  - frontend/context/AuthContext.tsx (80 lines, state management)
  - backend/services/github_oauth.py (200 lines, OAuth integration)
```

Instead of:
```
RIM_METADATA: No structural facts could be resolved
```

**Impact:** LLM would have file-level auth context even without symbol relationships.

---

## Remaining Risks

1. **Symbol Analysis Missing:** If GitOnboard analysis never extracted symbols, no fix will restore them without re-analysis
2. **Stale Analysis:** If analysis_id 14 is old/incomplete, newer analyses might have better symbol coverage
3. **BM25 Tokenization:** Even if symbols exist, BM25 may still fail to match natural language unless corpus is properly preprocessed
4. **Semantic Degradation:** Chroma was unavailable earlier in user's runs (from Phase 2 findings). Without it, system has no working retrieval at all
5. **No Fallback for "No Results":** If both BM25 and semantic fail, system returns empty list with no diagnostic message

---

## Final Verdict

**RIM_RETRIEVAL_NOT_VALIDATED**

The system can retrieve repository FILES (via Chroma semantic search) but **cannot produce RIM anchors** (symbol-level entities with relationships) because:

1. ✗ BM25 is non-functional for natural language queries
2. ✗ FactStore analysis is missing symbol-level extraction
3. ✗ Expansion pipeline cannot convert file results to relationship facts

The system is **partially operational** (semantic file search works) but **not suitable for RIM-driven answering** (which requires symbol-level entities and relationships).

**Immediate Recommendation:**
1. Verify whether GitOnboard analysis is supposed to include symbol extraction
2. If yes, re-run analysis pipeline for analysis_id 14
3. If no, implement file-level expansion as fallback
4. Add diagnostics to detect when analysis is missing symbol data

---

## Tests Needed

### Regression Test 1: BM25 Fallback
When semantic search returns results, verify BM25 doesn't silently fail and lose those results.

### Regression Test 2: Symbol Retrieval
When FactStore HAS symbols, verify BM25 can find them via exact name match.

### Regression Test 3: File-Level Expansion
When BM25/semantic return files without symbols, verify system produces meaningful fallback context.

### Regression Test 4: Graph Traversal
When symbols ARE found, verify expansion can traverse relationships.

### Regression Test 5: Complete Pipeline
End-to-end: "How does authentication work?" should produce either:
- Symbol-level RIM anchors + relationships (if symbols exist), OR
- File-level context fallback (if symbols missing)

Should NOT produce: "No structural facts could be resolved"
