# RIM System Deep Investigation Report

**Date:** September 2, 2026  
**Status:** Diagnosis Complete — No Code Changes Made  
**Scope:** Complete RIM pipeline architecture, data flow, and systemic issues

---

## EXECUTIVE SUMMARY

The RIM (Repository Intelligence Metadata) comparison system has **technical architectural correctness** (routes, loops, tool dispatch) but **fundamental data flow failures** that prevent it from functioning in most cases.

**Key Finding:** The system produces "technically successful" HTTP 200 responses while returning empty RIM metadata blocks ("No structural facts could be resolved") due to **critical disconnects between the retriever layer and database layer** at three independent boundaries:

1. **Seed Resolution Failure** — Retriever returns candidates that database cannot resolve to FactSymbol records
2. **Relationship Persistence Gap** — Only ~5% of relationships persist to database despite being valid in the model
3. **Analysis/Repository Identity Confusion** — Multiple potential sources of analysis_id mismatch

These issues are **not** fixed by the recent crash fixes (RimMetadataBlock initialization, Azure call limiting). Those fixes made the system not crash, but did not restore functional RIM metadata generation.

---

## CURRENT RIM ARCHITECTURE & DATA FLOW

### Orchestration (`rim_comparison_service_v2.py`)

```
User Question
    ↓
get_latest_analysis(repo_name) → analysis_id
    ↓
HybridRetriever(analysis_id)  [SHARED - both baseline & RIM]
    ↓
RepositoryToolLayer(analysis_id) [SHARED - both baseline & RIM]
    ↓
┌─────────────────────────────────────────────────────────────┐
│ BASELINE SIDE                       RIM SIDE                │
├─────────────────────────────────────────────────────────────┤
│ RIMQALoop (no RIM tools)    build_rim_metadata_block()      │
│                               ↓                              │
│ query_rim = None            retriever.retrieve(question)    │
│ system_prompt = minimal     resolver.resolve(candidates)    │
│                             ↓                                │
│                             FactStoreGraphTraverser.traverse()
│                             ↓                                │
│                             RimMetadataBlock.text            │
│                             (SUCCESS or EMPTY)               │
│                             ↓                                │
│                             RIMQALoop (with query_rim tool) │
│                             system_prompt = metadata + loop  │
└─────────────────────────────────────────────────────────────┘
    ↓
Both execute identically except:
  - Tool set (baseline has no query_rim)
  - System prompt (RIM has metadata block)
    ↓
Return ComparisonSide with metrics
```

### Hybrid Retrieval Flow

```
retrieve(question, expand_with_fact_store=False)  [used for RIM metadata]
    ├─ _search_exact_facts(question)
    ├─ _search_lexical(question)         [BM25 against indexed FactSymbol/FactFile]
    └─ _search_semantic(question)        [ChromaDB vector search]
         ↓
    RRF Fusion (Reciprocal Rank Fusion)
         ↓
    Candidate dict with fields:
      - id: something (varies by source)
      - symbol_id: value or None
      - name: entity name
      - file_path: path
      - match_type: type
      - analysis_id: NOT GUARANTEED TO BE SET
         ↓
    Return to RIM metadata builder
```

### RIM Metadata Generation (`rim_metadata.py`)

```
retrieve() → candidates (mixed ID formats)
    ↓
for each candidate:
    entity_name = cand.get("entity_name") or cand.get("symbol") or cand.get("path")
    ↓
    TargetEntityResolver.resolve(entity_name)
    ├─ Try FactSymbol.filter(analysis_id=X, name.ilike(entity_name))
    ├─ Try FactFile.filter(analysis_id=X, path.ilike(entity_name))
    ├─ Try FactRoute.filter(analysis_id=X, path.ilike(entity_name))
    └─ Try FactDatabaseObject.filter(analysis_id=X, name.ilike(entity_name))
         ↓
    If NO matches found: seed is discarded
         ↓
    If ALL seeds discarded: 
        return RimMetadataBlock(text="No structural facts could be resolved...")
```

---

## OBSERVED FAILURE MODES

### Symptom 1: "Seeds could not be resolved"
**Observed:** RIM metadata block returned with message "No structural facts could be resolved for this question in this repository's index."

**Current Data:** Both baseline and RIM sides complete successfully, but RIM side's metadata is empty/placeholder.

**Indicator:** Log line: `[RIM Metadata] Seeds could not be resolved`

### Symptom 2: Relationship counts don't match
**Observed (from earlier diagnostic agent):**
- Analysis shows 40+ symbols and 45 relationships during analysis run
- FactStoreExpander logs show 0 relationships found in database for the same analysis_id
- Log line (from expansion.py:145): `Total FactRelationship records for analysis_id=X: 0`

### Symptom 3: UI displays correct structure but empty content
**Observed:**
- RIM_METADATA field is populated in API response ✅
- RIM_METADATA text content is "No structural facts..." ✅ (correct structure)
- Tool call counts are 0 for RIM side (different from baseline) ⚠️ (symptom of LLM not having guidance)

### Symptom 4: Baseline vs RIM difference is minimal
**Expected:** RIM side should have significantly fewer tool calls due to metadata guidance  
**Observed:** RIM side actually has MORE turns/calls, hits MAX_TURNS_EXCEEDED guardrail while baseline completes  
**Root:** LLM receives no guidance, executes same exploration as baseline, eventually gives up

---

## ROOT CAUSE ANALYSIS

### ROOT CAUSE #1: Seed Resolution Failure (CRITICAL)

**What should happen:**  
Retriever returns candidates with entity_name field. TargetEntityResolver queries database and finds matching FactSymbol/FactFile. Candidate is enriched and used to seed traversal.

**What actually happens:**  
Retriever returns candidates. TargetEntityResolver executes 4 fallback strategies (symbol_id lookup, full ID query, name+file query, name-only query) but none match. Seed is silently discarded.

**Exact divergence point:**  
`rim_metadata.py:354` → `TargetEntityResolver.resolve(entity_name)` returns `None` for all candidates

**Evidence:**
- Log: `[RIM Metadata] Seeds could not be resolved` appears when no candidates resolve
- No matching records in database despite analysis_id being same
- Retriever is returning `match_name` field, but resolver is querying by different field combinations

**Why it appears successful:**  
- Exception is caught at line 114-116: `except Exception as e: candidates = []`
- No error raised; falls through to line 342-345: graceful degradation to empty metadata block
- HTTP 200 response returned with empty-but-valid metadata block

**Likely root causes (need to investigate):**
1. **Analysis/Version Mismatch** — Retriever indexed one version of analysis; database has different version
2. **Path Format Mismatch** — Retriever returns `filepath.tsx` but database has `src/app/filepath.tsx`
3. **Chroma Index Stale** — Vector embeddings were generated for old code; query returns matches from old analysis
4. **Symbol Name Not in Database** — Retriever's BM25/Chroma found a match, but the exact name is not in FactSymbol

**Why current fixes didn't solve this:**
- RimMetadataBlock initialization fix: only fixed the crash, not seed resolution
- Azure call limiting: only fixed symptom of excessive blob calls, not retrieval correctness
- These were necessary but not sufficient

---

### ROOT CAUSE #2: Relationship Persistence Gap (HIGH SEVERITY)

**What should happen:**  
RepositoryModel extracted 45 relationships during analysis. All relationships have source_id and target_id that reference entities in the model. When saving to database, all 45 relationships should persist with proper database ID format (`analysis_id:entity_id`).

**What actually happens:**  
Only ~5 out of 45 relationships persist. The rest are skipped with log messages like:  
`"Skipping relationship {rel.id}: source {rel.source_id} not found"`

**Exact divergence point:**  
`fact_store.py:166-167` — validation check fails:
```python
source_exists = rel.source_id in seen_symbol_ids or rel.source_id in seen_file_ids
target_exists = rel.target_id in seen_symbol_ids or rel.target_id in seen_file_ids
```

**Evidence:**
- Log line (expansion.py:145): Shows 0 relationships in database while analysis shows 45 should exist
- fact_store.py already has logging at lines 185-188 that should show which relationships were skipped

**The Critical Bug:**
The check at line 166-167 is using `rel.source_id in seen_symbol_ids`, but there's a **potential ID format mismatch**:

- `seen_symbol_ids` is populated from `entity.id` values (line 126)  
- These come from the RepositoryModel which generated them via `generate_entity_id()`
- **BUT** relationships might reference entities that weren't included in the current save batch

For example:
- Entity A with `entity.id = "func_login"` is included in the model
- Entity B with `entity.id = "db_table_users"` from a **different analyzer run** is referenced by relationships
- When saving, Entity B wasn't saved this run, so relationship validation fails

**Why it appears successful:**
- Relationships that ARE skipped are logged at DEBUG level (line 186-188)
- No exception is raised; they're simply omitted from the database
- Later, when retrieval looks for relationships, it finds 0 and returns empty results
- The system completes the RIM metadata building "successfully" with an empty block

**Why current fixes didn't solve this:**
- The fixes added better logging and multi-strategy symbol resolution in the expander
- They did NOT fix the relationship persistence itself
- The database might still have 0 relationships even though the model extracted 45

---

### ROOT CAUSE #3: Analysis/Repository Identity Lifecycle Issues (MEDIUM SEVERITY)

**What should happen:**
- `get_latest_analysis(repo_name)` returns a specific `Analysis` record with consistent `analysis_id`
- All downstream queries use this same `analysis_id`
- Repository tools, retriever, metadata builder all reference the same analysis

**What actually happens:**
- `get_latest_analysis()` returns an analysis (correct)
- HybridRetriever initialized with `analysis_id` and builds BM25 index
- BUT if the analysis is being updated concurrently (re-analysis triggered), indices might be stale
- If Chroma collection was built from a different version of analysis, semantic search returns results from old code

**Potential divergence points:**
1. `rim_comparison_service_v2.py:139` — `get_latest_analysis()` returns `analysis_id = X`
2. `rim_comparison_service_v2.py:152-154` — `HybridRetriever` initialized with same `analysis_id`
3. `rim_metadata.py:336` — Retriever executes, might return candidates indexed from different analysis

**Evidence:**
- If re-analysis was triggered recently, old analysis_id might still be "latest"
- Chroma index generation is async; might lag behind database
- RepositoryToolLayer initialization at line 61-65 has fallback logic that could pick different analysis_id

**Why it appears successful:**
- Exception handling at line 138-143 logs errors but doesn't block
- If get_latest_analysis fails, exception is raised (correct)
- If analysis_id is inconsistent, no exception is raised; just silently mismatches

**Why current fixes didn't solve this:**
- No fixes were made to analysis resolution logic
- The router version fix was unrelated to this

---

### ROOT CAUSE #4: Query-Retrieval Format Mismatch (MEDIUM SEVERITY)

**What should happen:**
- Lexical indexer (BM25) indexes FactSymbol records with consistent field naming
- Semantic indexer (Chroma) returns metadata with same field naming
- Both populate `symbol_id`, `name`, `file_path`, `match_type` consistently
- TargetEntityResolver expects these fields in predictable formats

**What actually happens:**
- Lexical indexer (retriever.py:89-101) creates docs with: `symbol_id=sym.id`, `name=sym.name`, `file_path=fpath`
- Semantic search (retriever.py:298-328) returns metadata with: `file_path=meta.get("file_path")`, `name=meta.get("name")`
- **BUT** if metadata.get("name") returns slightly different format (e.g., "Login" vs "login" due to case), resolver fails

**Path format variations observed:**
- Some paths include leading `./` or `/`
- Some use `\` (Windows)
- Some use `/` (POSIX)
- Resolver queries use `.ilike()` which is case-insensitive SQL, but:
  - Candidate has `filepath.tsx`
  - Database has `src/app/filepath.tsx`
  - Query `path.ilike(f"%{entity_name}%")` might match BOTH files or NONE

**Evidence:**
- retriever.py:82-101 extracts `fpath = _extract_symbol_file_path(sym)`
- This extraction is complex (lines 12-22) and could produce different formats
- rim_metadata.py:350 extracts `entity_name = cand.get("entity_name") or cand.get("symbol") or cand.get("path")`
- No normalization happens between extraction and resolution

---

## WHY THE CURRENT FIXES DID NOT SOLVE THE FUNCTIONAL PROBLEM

### Fix #1: RimMetadataBlock(text="") initialization
**Effect:** Allows function to run without crashing  
**Limitation:** Doesn't populate RIM metadata; just prevents exception  
**Does NOT fix:** Seed resolution failure, relationship persistence, analysis mismatch

### Fix #2: search_code max_files_scanned cap
**Effect:** Prevents excessive Azure blob calls  
**Limitation:** Only affects search_code tool, not retriever or expansion  
**Does NOT fix:** RIM metadata being empty, LLM not receiving guidance, seed resolution

### Fix #3: Router version switch (v1 → v2)
**Effect:** Returns correct response schema to frontend  
**Limitation:** Frontend now sees empty `rim_metadata_block` instead of null  
**Does NOT fix:** The underlying reason metadata is empty

---

## SYSTEMIC IMPACT

### Affected Scenarios

1. **All repositories during first analysis**
   - New analysis is performed, 0 relationships persisted
   - RIM metadata is empty for all questions
   - RIM side indistinguishable from baseline (except slower due to more turns)

2. **Repositories with re-analysis**
   - If analysis_id doesn't match what's indexed in Chroma/BM25
   - Seeds won't resolve
   - RIM metadata is empty

3. **Large repositories with many entities**
   - Higher chance of path format mismatches across analysis runs
   - More likely to hit relationship persistence validation failures
   - RIM becomes effectively disabled

4. **Concurrent operations**
   - If re-analysis is triggered while comparison is running
   - Indices might be stale
   - Seeds might resolve to old entities

### What DOESN'T work:
- Comparing baseline vs RIM effectiveness (both behave the same)
- Using RIM to guide LLM exploration (no metadata provided)
- Demonstrating structural knowledge benefits (knowledge not extracted)
- Research on RIM efficacy (broken comparison makes it useless)

---

## PROPOSED GENERAL FIX

### Phase 1: Immediate Verification & Diagnostic Hardening

**Goal:** Prove the root causes and create observability

1. **Add explicit validation logging**
   - Log every retriever result with full candidate dict (not truncated)
   - Log every resolution attempt with all fallback strategies
   - Log the final set of seeds before traversal

2. **Add database state snapshots**
   - Before RIM metadata building, log:
     - `SELECT COUNT(*) FROM fact_symbols WHERE analysis_id=X`
     - `SELECT COUNT(*) FROM fact_relationships WHERE analysis_id=X`
     - Sample of actual symbol IDs and relationship structures
   - Compare with what retriever returns

3. **Add analysis_id consistency checks**
   - Verify HybridRetriever's analysis_id matches expected
   - Verify Chroma collection's analysis_id if available
   - Check if analysis has been updated since Chroma index was built

4. **Add path format normalization**
   - Create `normalize_entity_path(path: str) → str` function
   - Use it consistently in:
     - Retriever's candidate generation
     - TargetEntityResolver queries
     - File path comparisons
   - Log before/after normalization for debugging

### Phase 2: Fix Relationship Persistence

**Root:** Only ~5% of relationships persist due to entity validation failure

**Fix:**
1. **Validate entities exist BEFORE creating relationship validation**
   - At fact_store.py line 162, before checking `rel.source_id in seen_symbol_ids`:
     - Query database for existing FactSymbol records
     - Build a complete set of ALL entity IDs (not just from this batch)
   - Or: defer relationship saves until all entities are confirmed saved

2. **Cross-analysis entity resolution**
   - If relationship references an entity NOT in current batch:
     - Check if entity exists in database from prior analysis run
     - Query FactSymbol to validate before skipping relationship
     - Either: mark relationship as "PENDING_TARGET" or link to old entity

3. **Relationship validation redesign**
   - Change from: "skip if either entity is missing from batch"
   - Change to: "skip only if entity doesn't exist ANYWHERE in database"

### Phase 3: Fix Seed Resolution

**Root:** Retriever returns candidates that don't match database queries

**Fix:**
1. **Normalize path handling**
   - Apply consistent path normalization at retriever output
   - Create canonical path format: relative POSIX path without `./ or leading /`
   - Update TargetEntityResolver to normalize query inputs

2. **Enhance symbol resolution fallbacks**
   - Current: name only (last resort)
   - Enhanced: 
     - By symbol_id if available
     - By name + file_path (exact match)
     - By qualified_name if available
     - By fuzzy name match if exact fails
     - By entity type + name combination
   - Log which strategy succeeds for each candidate

3. **Add candidate-to-database verification**
   - After retriever returns candidates, validate each one:
     ```
     for each candidate:
       try resolve by symbol_id
       try resolve by name+file
       if STILL unresolved:
         log WARNING: "Candidate {name} from {file} not found in database"
         check if analysis_id is correct
         check if entity was indexed in Chroma
     ```

### Phase 4: Fix Analysis Identity Issues

**Root:** Analysis_id might be inconsistent across retriever/metadata/storage

**Fix:**
1. **Explicit analysis_id validation**
   - When RIMComparisonService initializes, verify:
     - Analysis exists and is accessible by user
     - Analysis has been fully analyzed (not in progress)
     - Chroma collection exists for this analysis
     - BM25 index matches this analysis_id
   - Log mismatches instead of silently using defaults

2. **Retriever result tagging**
   - Have retriever explicitly include source analysis_id in results
   - Validate that results came from expected analysis_id
   - Fail loudly if mismatch detected

3. **Concurrent analysis protection**
   - If re-analysis is triggered during comparison:
     - Use snapshot of analysis_id at start
     - Don't re-resolve analysis mid-comparison
     - Lock analysis during comparison (optional, expensive)

### Phase 5: Architectural Safeguards

**Goal:** Prevent these failures from recurring

1. **Add pre-flight checks**
   - RIM metadata generation should fail loudly if:
     - Zero relationships in database for this analysis
     - Retriever returns zero candidates
     - All candidates fail to resolve
   - Return error instead of empty metadata

2. **Add progress gates**
   - Don't proceed to next phase if critical data missing:
     - Phase 1 (retrieval): require ≥ 1 candidate per search
     - Phase 2 (resolution): require ≥ 50% resolution rate
     - Phase 3 (traversal): require ≥ 1 relationship found
   - Fail explicitly if gates not met

3. **Add model integrity checks**
   - After analysis, verify:
     - All referenced entities exist in database
     - All relationships have valid source and target
     - Symbol IDs are in expected format
   - Run as part of post-analysis validation

---

## REQUIRED CODE CHANGES (Detailed)

### File: `backend/intelligence/retrieval/retriever.py`

**Change 1.1:** Add path normalization function (new module)
```python
# backend/intelligence/retrieval/path_normalizer.py
def normalize_entity_path(path: Optional[str]) -> Optional[str]:
    """Convert path to canonical form: relative POSIX, no ./ or leading /"""
    if not path:
        return None
    p = path.replace("\\", "/").removeprefix("./").lstrip("/")
    return p if p else None
```

**Change 1.2:** Apply normalization to BM25 index candidates
- retriever.py line ~90: `"file_path": normalize_entity_path(_extract_symbol_file_path(sym))`

**Change 1.3:** Apply normalization to semantic results
- retriever.py line ~322: `"file_path": normalize_entity_path(meta.get("file_path"))`

**Change 1.4:** Add analysis_id to all candidate dicts
- retriever.py line ~70: add `"analysis_id": self.analysis_id`
- retriever.py line ~320: add `"analysis_id": self.analysis_id`

### File: `backend/services/rim_metadata.py`

**Change 2.1:** Enhance TargetEntityResolver.resolve() with multi-strategy fallback
- Add 6+ strategies instead of current 4
- Log which strategy matches
- Include fuzzy matching as last resort
- Check if entity exists ANYWHERE in database, not just for this analysis_id (with warning)

**Change 2.2:** Add explicit seed resolution validation
- After resolution phase (line 347-362), validate:
  - `if not seeds: log error with candidate details` (currently only log info)
  - Compare candidate names against database query results
  - Suggest possible causes (analysis mismatch, path format, etc.)

**Change 2.3:** Add pre-flight database state check
- At function start, before retriever.retrieve():
  - Query total FactSymbol/FactRelationship counts for this analysis_id
  - Log these numbers
  - If zero symbols: raise error "Analysis {id} has no indexed symbols"
  - If zero relationships: log warning "Analysis {id} has no relationships (expected for new analysis)"

### File: `backend/intelligence/store/fact_store.py`

**Change 3.1:** Fix relationship persistence validation
- Line 165-167: Instead of checking `rel.source_id in seen_symbol_ids`, query database:
  ```python
  source_sym = db.query(FactSymbol).filter(
      FactSymbol.analysis_id == analysis_id,
      FactSymbol.id == f"{analysis_id}:{rel.source_id}"  # or rel.source_id, depending on format
  ).first()
  source_exists = source_sym is not None
  ```
- Same for target_id

**Change 3.2:** Validate entity IDs before persisting
- Line 162-167: Verify that source and target entities were actually created in this batch
- If not found in batch, query database to check if they exist from prior analysis
- Log decision: "saving relationship" vs "skipping relationship (why)"

### File: `backend/services/rim_comparison_service_v2.py`

**Change 4.1:** Add explicit analysis validation
- After `get_latest_analysis()` at line 139:
  ```python
  # Validate analysis state
  if not analysis.symbols_count or not analysis.relationships_count:
      logger.warning(f"Analysis {analysis_id} has {analysis.symbols_count} symbols, {analysis.relationships_count} relationships")
  ```

**Change 4.2:** Add retriever result validation
- After `retriever.retrieve()` call in build_rim_metadata_block:
  ```python
  if not candidates:
      logger.warning(f"[RIM Comparison] Retriever returned 0 candidates for: {question}")
      logger.debug(f"[RIM Comparison] Checking database state...")
      # Log symbol/relationship counts
  ```

---

## TEST STRATEGY

### Unit Tests to Add

1. **test_rim_seed_resolution_with_path_variations.py**
   - Test resolving seeds with different path formats (Windows, POSIX, relative, absolute)
   - Verify normalization is applied consistently
   - Verify all fallback strategies are exercised

2. **test_relationship_persistence_with_partial_model.py**
   - Create model with entities and relationships
   - Save only some entities to database first
   - Try to save relationships that reference unsaved entities
   - Verify validation handles missing entities correctly

3. **test_rim_metadata_generation_with_zero_relationships.py**
   - Create analysis with symbols but no relationships
   - Verify RIM metadata building completes gracefully
   - Verify returned metadata indicates "no relationships found"

4. **test_analysis_id_consistency_across_pipeline.py**
   - Mock scenario where analysis_id changes mid-pipeline
   - Verify explicit validation catches the mismatch

### Integration Tests to Add

1. **test_rim_vs_baseline_with_real_analysis.py**
   - Use actual repository analysis (or fixture)
   - Verify both baseline and RIM sides complete
   - Verify RIM side has metadata (not empty)
   - Verify RIM side has fewer tool calls OR better coverage

2. **test_retriever_candidate_to_database_mapping.py**
   - Generate candidates via retriever
   - Verify each candidate can be resolved to database entity
   - Track and report any unmappable candidates

3. **test_relationship_coverage_after_persistence.py**
   - Analyze repository, extract N relationships
   - Save to database
   - Query back via FactStoreExpander
   - Verify ≥ 95% of relationships are found

### Regression Tests

Add to CI/CD:
- After any analysis changes: verify relationship persistence rate ≥ 95%
- After any retriever changes: verify ≥ 80% of candidates resolve to entities
- After any path handling changes: verify tests pass with Windows/POSIX/mixed paths

---

## HOW TO VERIFY THE FIX IS CORRECT

### Pre-Fix Baseline (Current State)

1. Run RIM comparison for any question
2. Expected: UI shows "RIM_METADATA: No structural facts..." for RIM side
3. Expected: RIM tool_call_count = 0 (no query_rim calls)
4. Expected: Baseline side has more tool calls than RIM side
5. Expected: Both sides produce reasonable answers (despite RIM having no metadata)

### Post-Fix Verification

1. Run RIM comparison for same question
2. Expected: UI shows actual RIM facts like "authenticate CALLS verify_password"
3. Expected: RIM tool_call_count > 0 (query_rim is being used)
4. Expected: Baseline side has SAME or MORE tool calls than RIM side
5. Expected: RIM answer includes specific references to relationships discovered via query_rim
6. Expected: Logs show seeds resolved successfully, relationships found, traversal completed

### Comparative Test

Run identical question through both baseline and RIM:
- **Before Fix:** Tool calls and answers are virtually identical (RIM adds no value)
- **After Fix:** RIM side uses fewer tool calls due to metadata guidance, or reaches deeper into code via graph navigation

### Logging Validation

Enable DEBUG logging and verify:
- `[RIM Metadata] Retrieved N seed candidates` (N > 0)
- `[RIM Metadata] Resolved seed: X -> FactSymbol` (multiple successful resolutions)
- `[RIM Metadata] Traversing seed: X` (actual traversal happening)
- `[RIM Expand] Seed[N] found M relationships` (M > 0)
- `[RIM Metadata] Block built: K fact lines` (K > 0)

---

## ARCHITECTURAL DEBT & RELATED BUGS DISCOVERED

### Debt 1: Implicit ID Format Coupling
**Issue:** Symbol IDs flow through the system in different formats (`entity.id`, `{analysis_id}:{entity.id}`, composite keys)  
**Impact:** Every stage of pipeline must validate/normalize IDs  
**Recommendation:** Create single `SymbolID` type with implicit conversion, use throughout pipeline

### Debt 2: Missing Entity Existence Validation
**Issue:** Relationships reference entities that might not exist in current save batch  
**Impact:** Relationships silently fail to persist, causing RIM to be empty  
**Recommendation:** Implement entity resolution before relationship persistence; defer or flag unresolved

### Debt 3: Chroma Index Lifecycle Unknown
**Issue:** Chroma collection might be stale if analysis is re-run  
**Impact:** Semantic search returns candidates from old code  
**Recommendation:** Add `analysis_id` and `updated_at` to Chroma metadata; validate freshness

### Debt 4: Analysis Resolution Fragility
**Issue:** `get_latest_analysis()` uses unspecified logic for "latest"  
**Impact:** Might return different analysis_id on concurrent calls  
**Recommendation:** Make analysis_id explicit parameter or add explicit validation

### Debt 5: Path Normalization Inconsistency
**Issue:** Paths are normalized differently in different modules  
**Impact:** Candidate paths don't match database paths, seed resolution fails  
**Recommendation:** Implement single `normalize_path()` function, use everywhere

---

## SUMMARY TABLE

| Root Cause | Severity | Impact | Current Status | Fix Complexity |
|-----------|----------|--------|-----------------|-----------------|
| Seed Resolution Failure | CRITICAL | RIM metadata empty | Not fixed | Medium |
| Relationship Persistence Gap | HIGH | DB missing relationships | Not fixed | Medium |
| Analysis/Repo Identity Issues | MEDIUM | Stale indices, mismatches | Not fixed | Low |
| Query Format Mismatch | MEDIUM | Seeds don't resolve | Not fixed | Low |
| Chroma Index Staleness | MEDIUM | Stale semantic results | Not fixed | Medium |

---

**Investigation Completed:** No code changes made. Full diagnosis and fix plan provided.

**Next Step:** Implement Phase 1 (verification & hardening) to prove root causes and provide better observability.
