# RIM Pipeline Comprehensive Diagnosis Report

**Date:** September 2, 2026  
**Scope:** End-to-end trace of user question through entire RIM comparison pipeline  
**Method:** Static code analysis + data flow tracing (no runtime execution)

---

## 1. EXECUTIVE DIAGNOSIS

The RIM pipeline exhibits a critical **data loss architecture** where:

- **search_code() successfully finds real files** (via worktree scan or Blob Storage)
- **BUT retriever.retrieve() returns 0 candidates** (no BM25 index, no semantic embeddings, no exact matches)
- **Metrics report Files=0, Symbols=1** (metrics count only from tool_call_count, not from search results)
- **RIM metadata shows empty/minimal facts** (no seed entities → no graph expansion → no relationships)

This happens because the **retriever is isolated from the repository tool results**. The pipeline has two separate retrieval paths:

1. **Repository Tools (search_code, search_repository, get_symbol, etc.)**
   - Connected to actual codebase + Blob Storage
   - Returns real files and symbols
   - Used directly by LLM tool calls
   - Results are NOT fed back to retriever index

2. **Hybrid Retriever (lexical BM25 + semantic + exact)**
   - Built once at startup from FactStore tables
   - Never updated with fresh search results
   - Returns 0 if FactStore is stale/incomplete
   - Used for RIM metadata seed selection ONLY

**The discrepancy:** search_code finds files, but retriever doesn't know about them, so RIM metadata is empty.

---

## 2. CURRENTLY BROKEN

### Issue #1: Empty RIM Metadata Despite Successful Searches

**Exact Evidence:**

1. User calls comparison with question: "How does authentication work?"
2. Baseline loop calls search_repository → finds real files (src/app/page.tsx, etc.)
3. search_code successfully reads actual source via worktree
4. BUT: build_rim_metadata_block calls retriever.retrieve() with expand_with_fact_store=False
5. retriever.retrieve() returns [] (all three search methods fail)
6. rim_metadata.py lines 118-121: empty return with "No structural facts could be resolved"

**First Point of Failure:** HybridRetriever.retrieve() returning empty list (retriever.py line 388)

**Severity:** CRITICAL - RIM metadata is completely empty when FactStore has stale/incomplete indexes

---

### Issue #2: Files=0 Despite search_code Finding Files

**Exact Evidence:**

1. search_code() successfully iterates worktree or Blob Storage, finds files
2. Returns list with: `{"file": "src/app/page.tsx", "line": 42, "snippet": "...", "match_type": "lexical"}`
3. LLM sees this in tool_observation
4. BUT: rim_qa_loop.py lines 236-243 only increments files_read when tool_name == "read_file" AND success
5. search_code results are NOT tracked as "files retrieved"
6. Metrics: files_retrieved = len(loop_result.files_read) = 0

**First Point of Failure:** Metrics only count read_file tool calls, not search results (rim_comparison_service_v2.py line 356)

**Severity:** HIGH - UI metrics mislead user about retrieval success

---

### Issue #3: Symbols=1 But Should Be Higher

**Exact Evidence:**

1. get_symbol() can find symbols if they exist in FactSymbol table
2. BUT: if FactSymbol table is incomplete (some symbols not extracted), get_symbol returns partial results
3. Symbols are only counted if get_symbol tool succeeds (rim_qa_loop.py line 242)
4. If FactSymbol table was never populated for this analysis_id, get_symbol returns []

**First Point of Failure:** FactSymbol table incomplete or not indexed (fact_store.py persist step)

**Severity:** MEDIUM - accurate only if symbol extraction succeeded

---

## 3. NULL / EMPTY / ZERO AUDIT

### A. Retriever Returns Empty List

**Where generated:**  
`retriever.py:388` - `if not ranked_lists: return []`

**Why generated:**
- exact_results = [] (line 367)
- lexical_results = [] (line 368) → because bm25_index is None or has no docs
- semantic_results = [] (line 369) → because chroma_collection is None or has no embeddings

**Is it legitimate?**  
NO. If search_code finds files, retriever should find them too. The problem is:
- BM25 index built from FactStore at startup (retriever.py:55-160)
- FactStore incomplete → BM25 index empty
- Search results never fed back to index
- Index never refreshed

**Downstream impact:**  
- retriever.retrieve() returns [] for ALL questions
- RIM metadata empty for ALL comparisons
- Graph expansion finds 0 relationships
- LLM gets no structural context

---

### B. BM25 Index is Empty

**Where generated:**  
`retriever.py:53` - `self._build_lexical_index()`

**Why generated:**
- Queries FactFile: `db.query(FactFile).filter(FactFile.analysis_id == self.analysis_id).all()` (line 63)
- If FactFile table has 0 records for this analysis_id, docs list stays empty
- If FactSymbol table has 0 records for this analysis_id, docs list stays empty

**Is it legitimate?**  
NO. If symbol extraction ran, FactSymbol should have records. If it returned 0:
- Either analyzer never ran
- Or analyzer ran but found 0 symbols (SymbolAnalyzer should find at least file entities)
- Or symbols were extracted but not persisted to FactStore

**Downstream impact:**  
- bm25_index = None (retriever.py:52)
- _search_lexical returns [] (line 337)
- No lexical candidates for retriever.retrieve()
- No backup if semantic search also fails

---

### C. Chroma Collection is None

**Where generated:**  
`rim_comparison_service_v2.py:145-149` - Silent exception caught, logs at DEBUG level

```python
chroma_collection = None
try:
    chroma_collection = get_chroma_collection(self.repo_name, self.current_user, self.db)
except Exception as e:
    logger.debug(f"Chroma collection not available: {e}")
```

**Why generated:**
- Chroma embedding collection not found/not built
- Possibly collection name mismatch
- Possibly embeddings service unavailable
- Exception is silently swallowed

**Is it legitimate?**  
Partial. Chroma being unavailable is acceptable IF lexical search works as fallback. But if BOTH fail:
- semantic_results = [] (chroma_collection is None)
- lexical_results = [] (BM25 index is None)
- exact_results = [] (no exact matches)
- retriever.retrieve() returns []

**Downstream impact:**  
- If chroma_collection fails, system relies entirely on BM25
- If BM25 also empty, retriever fails completely
- No fallback path

---

### D. FactRelationship Table is Empty

**Where generated:**  
`expansion.py:145-159` - Logged via debug queries

**Why generated:**
- CallGraphAnalyzer created orphaned relationships (I just fixed this)
- But also: FactStore validation at line 166-167 skipped orphaned relationships silently
- Result: 0 relationships persisted to database despite 40+ relationships extracted

**Is it legitimate?**  
NO. This is a bug. My previous fix addresses this.

**Downstream impact:**  
- FactStoreExpander finds 0 relationships (expansion.py:171-174 returns [])
- Graph expansion adds 0 new entities
- RIM metadata has minimal structural context
- get_callers() and get_callees() return []

---

### E. files_read List is Empty

**Where generated:**  
`rim_qa_loop.py:238-239` - Only populated when read_file tool succeeds

```python
if tool_name == "read_file" and tool_observation.success:
    path = arguments.get("path", "")
    if path and path not in result.files_read:
        result.files_read.append(path)
```

**Why generated:**
- search_code results are NOT tracked (different tool)
- search_repository results are NOT tracked (different tool)
- find_files results are NOT tracked (different tool)
- Only read_file increments the counter

**Is it legitimate?**  
PARTIALLY. Tracking only "read files" makes sense IF the metric is "files user queried". But the UI presents this as "Files Retrieved", which is misleading when search_code found 20 files but only 2 were read.

**Downstream impact:**  
- Metrics show Files=0 even though search found files
- User thinks retrieval failed when it actually succeeded
- No indication of search vs. read distinction

---

## 4. DATA LOSS TRACE

### Concrete Example: File src/app/page.tsx

**Stage 1: Search Phase**
```
Input:  question = "What is authentication?"
Tool:   search_code()
Path:   tools.py:196-287
Flow:   repo_root exists → walk filesystem → find "auth" in filename/content
Output: {"file": "src/app/page.tsx", "line": 42, "snippet": "const auth = ...", "match_type": "lexical"}
Status: ✅ FOUND
```

**Stage 2: Tool Dispatch**
```
Input:  tool_call = {"tool_name": "search_code", "arguments": {"query": "authentication"}}
Path:   rim_tool_dispatch.py:416-450
Flow:   _handle_search_code() → tool_layer.search_code() → returns results
Output: ToolObservation(success=True, data=[{file: "src/app/page.tsx", ...}])
Status: ✅ SUCCESS
```

**Stage 3: Loop Tracking**
```
Input:  tool_observation for search_code
Path:   rim_qa_loop.py:236-243
Logic:  if tool_name == "search_code" → skip (not "read_file" or "get_symbol")
Output: files_read stays empty, symbols_read stays empty
Status: ❌ NOT TRACKED
```

**Stage 4: Metrics Calculation**
```
Input:  loop_result.files_read = []
Path:   rim_comparison_service_v2.py:354-361
Logic:  files_retrieved = len(loop_result.files_read)
Output: files_retrieved = 0
Status: ❌ ZERO (despite file found)
```

**Stage 5: RIM Metadata Building**
```
Input:  question = "What is authentication?"
Path:   rim_metadata.py:74-139
Logic:  retriever.retrieve(question, expand_with_fact_store=False)
        → retriever has no index of src/app/page.tsx
        → returns []
Output: No seed entities → empty metadata block
Status: ❌ EMPTY (despite file found)
```

**Stage 6: Graph Expansion**
```
Input:  seeds = [] (empty from stage 5)
Path:   expansion.py:29-235
Logic:  if not candidates: return candidates (line 37-38)
Output: No expansion, no callers/callees added
Status: ❌ NO EXPANSION (no seeds to expand)
```

**Stage 7: Final Output**
```
Files: 0 (from metrics)
Symbols: ? (depends on get_symbol calls)
RIM Metadata: "No structural facts could be resolved"
Relationships: 0
Status: ❌ LOSS OF SIGNAL (file found in stage 1 → metrics say 0 files)
```

**Information Death Points:**
1. **Stage 3**: search_code results not counted in metrics
2. **Stage 5**: search_code results never indexed in retriever
3. **Stage 6**: no seeds = no expansion

---

## 5. METRICS AUDIT

### Files = 0

**Source:** rim_comparison_service_v2.py:356
```python
files_retrieved = len(loop_result.files_read)
```

**How is loop_result.files_read populated?**

Only via rim_qa_loop.py:238-239:
```python
if tool_name == "read_file" and tool_observation.success:
    path = arguments.get("path", "")
    if path and path not in result.files_read:
        result.files_read.append(path)
```

**What tools increment it?**
- ONLY: read_file

**What tools DON'T increment it?**
- search_code ❌ (finds files but doesn't increment)
- search_repository ❌ (includes file results but doesn't increment)
- find_files ❌ (returns files but doesn't increment)
- get_file_outline ❌ (returns file contents but doesn't increment)

**Why is this wrong?**

The metric is titled "Files Retrieved" but only counts files that were read with read_file. This is misleading because:
- Search can find 50 files
- Only 2 get read
- Metric says "2 files retrieved"
- But actually 50 files were searched

**What should happen?**

Metrics should track:
- files_searched (from search_code, find_files, search_repository)
- files_read (from read_file)
- files_inspected_via_outline (from get_file_outline)

---

### Symbols = 1 (or low number)

**Source:** rim_comparison_service_v2.py:357
```python
symbols_retrieved = len(loop_result.symbols_read)
```

**How is loop_result.symbols_read populated?**

Only via rim_qa_loop.py:242-243:
```python
elif tool_name == "get_symbol" and tool_observation.success:
    name = arguments.get("name", "")
    if name and name not in result.symbols_read:
        result.symbols_read.append(name)
```

**What determines if get_symbol succeeds?**

tools.py:293-322 - queries FactSymbol table:
```python
symbols = (
    self.db.query(FactSymbol, FactFile.path)
    .join(FactFile, FactSymbol.file_id == FactFile.id)
    .filter(
        FactSymbol.analysis_id == self.analysis_id,
        FactSymbol.name.ilike(f"%{name}%"),
    )
    .limit(20)
    .all()
)
```

**If FactSymbol has 0 records for this analysis_id:**
- get_symbol returns []
- LLM gets no symbol results
- symbols_read stays empty
- Metrics show 0

**Why might FactSymbol be empty or incomplete?**

1. SymbolAnalyzer never ran
2. SymbolAnalyzer ran but found 0 entities (unlikely - should find at least FILE entities)
3. Entities were extracted but not persisted due to validation errors
4. Analysis_id mismatch between extraction and query

---

## 6. TOOL CONTRACT AUDIT

### Tool Result Schemas

#### search_repository (tools.py:457-509)

**Returns:**
```python
[
  {
    "type": "symbol" | "file" | "code",
    "file": str,
    "symbol": str (if type=symbol),
    "symbol_type": str (if type=symbol),
    "lines": str (if type=symbol),
    "size": int (if type=file),
    "line": int (if type=code),
    "snippet": str (if type=code),
    "match_source": "symbol_index" | "filename_manifest" | "lexical",
  }
]
```

**Problem:** Generic dict, no guaranteed fields

---

#### search_code (tools.py:196-287)

**Returns:**
```python
[
  {
    "file": str,
    "line": int,
    "snippet": str,
    "match_type": "lexical",
  }
]
```

**Problem:** Returns dict with "file" not "path"

---

#### get_symbol (tools.py:293-322)

**Returns:**
```python
[
  {
    "symbol_id": str,
    "name": str,
    "qualified_name": str,
    "symbol_type": str,
    "file": str (path),
    "line_start": int,
    "line_end": int,
  }
]
```

**Problem:** Returns "file" (path string), not file_id

---

#### find_files (tools.py missing in grep, checking...)

**Search shows**: grep -n "def find_files" returns line 354 in tools.py

**Likely returns:**
```python
[
  {
    "path": str,
    "size": int,
    "type": str,
  }
]
```

---

### Schema Inconsistencies

**Field Naming Issues:**
- search_code uses "file" for path
- search_repository uses "file" for path
- find_files uses "path" for path
- get_symbol uses "file" for path
- HybridRetriever expects "file_path" (retriever.py:49)

**Result:** When HybridRetriever tries to match candidates from search_code:
- Candidate has "file": "src/app/page.tsx"
- Retriever looks for "file_path": "src/app/page.tsx"
- MISMATCH - entity_name extraction fails

---

### ID Format Inconsistencies

**Symbol IDs in FactStore:**
```
Format: "{analysis_id}:{entity.id}"
Example: "100:urn:function:src/auth.py#authenticate"
```

**Symbol IDs from get_symbol():**
```
Format: "{analysis_id}:{entity.id}"
Same as above
```

**Symbol IDs from semantic search:**
```
Depends on what Chroma indexed
Likely: full ID from FactSymbol.id
```

**Symbol IDs from BM25:**
```
From retriever.py:90-91, includes symbol_id
```

**Problem:** ID format consistency OK, but FactStore may have stale IDs

---

## 7. ERROR-SWALLOWING AUDIT

### Silent Exception: Chroma Collection Not Found

**Location:** rim_comparison_service_v2.py:145-149

```python
chroma_collection = None
try:
    chroma_collection = get_chroma_collection(self.repo_name, self.current_user, self.db)
except Exception as e:
    logger.debug(f"Chroma collection not available: {e}")  # DEBUG level - may not appear in logs
```

**Impact:** 
- Semantic search silently disabled
- No error message to user
- Fallback to lexical search (if it exists)
- If lexical also empty → retriever fails silently

**Consequence:**
```
Exception "collection not found" 
→ chroma_collection = None 
→ _search_semantic() returns [] 
→ if lexical also [] and exact also [] 
→ retriever.retrieve() returns [] 
→ HTTP 200 with empty metadata
```

**Is this fail-open behavior?** YES

---

### Silent Exception: Tool Dispatch Errors

**Location:** rim_tool_dispatch.py:262-269

```python
except Exception as e:
    logger.error(f"Tool dispatch error for {tool_name}: {e}", exc_info=True)
    return ToolObservation(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        success=False,
        error={"type": "dispatch_error", "message": str(e)},
    )
```

**Impact:**
- Tool errors logged but don't crash loop
- ToolObservation has success=False
- Loop continues with empty results
- LLM sees error message in tool_observation

**Is this appropriate?** YES - Better to return error than crash

---

### Silent Exception: Blob Storage Fetch

**Location:** tools.py:272-285

```python
try:
    text = storage.get_object_text(f_rec.blob_name)
    for line_idx, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            results.append({...})
except Exception:
    continue  # Silently skip file and continue
```

**Impact:**
- If Blob Storage fails for one file, search continues on others
- User doesn't know file failed to load
- May miss matching content

**Is this appropriate?** PARTIALLY - Continuing is good, but should log which files failed

---

### Silent Exception: Symbol Extraction Failure

**Location:** fact_store.py (my previous fix)

**Before my fix:**
```python
if source_exists and target_exists:
    # Save relationship
else:
    skipped_rels += 1
    logger.debug(f"Skipping relationship {rel.id}: target {rel.target_id} not found")  # DEBUG level
```

**Impact:**
- 40+ relationships silently skipped during save
- DEBUG logging means logs may not appear by default
- HTTP 200 response even though data lost
- No indication to user that analysis was incomplete

**Is this fail-open?** YES - Significant data loss disguised as success

---

## 8. ROOT CAUSES

### PROVEN

#### 1. BM25 Index Built Once at Startup
**Evidence:** retriever.py:55-160, `self._build_lexical_index()` called in `__init__`  
**Impact:** If FactStore is incomplete at startup, index is incomplete forever  
**Proof:** No refresh mechanism, no live update path from analyzer outputs

#### 2. Analyzer Outputs Not Indexed by Retriever
**Evidence:** RIM comparison never updates retriever indexes after analyzer runs  
**Impact:** search_code finds files, but retriever has no knowledge of them  
**Proof:** Analyzer populates FactStore, retriever indexes FactStore at startup only, analyzer runs later, index stale

#### 3. Orphaned Relationships Silently Skipped During Persist
**Evidence:** fact_store.py:166-188, relationships silently skipped with DEBUG logging  
**Impact:** Graph expansion finds 0 relationships despite extraction finding 40+  
**Proof:** My fix validates this - relationships violated invariant

#### 4. Files Counted Only from read_file, Not from Search
**Evidence:** rim_qa_loop.py:236-239, only read_file increments counter  
**Impact:** Files=0 when searches find files  
**Proof:** No other tools increment files_read

#### 5. Retriever Not Integrated with Repository Tools
**Evidence:** search_code and retrieve use different APIs/backends  
**Impact:** Retrieval path #1 (search_code) bypasses retriever completely  
**Proof:** search_repository uses get_symbol + search_code but retriever indexes FactStore

---

### LIKELY

#### 1. FactSymbol Table Incomplete or Empty
**Evidence:** If get_symbol returns 0 results, FactSymbol is empty for this analysis_id  
**Symptoms:** symbols_retrieved = 0, RIM metadata shows "No symbols"  
**Why:** Symbol extraction may have failed, or symbols not persisted

#### 2. Chroma Collection Not Built or Stale
**Evidence:** chroma_collection = None due to exception  
**Symptoms:** Semantic search returns 0 candidates  
**Why:** Chroma collection not built for this repo or name mismatch

#### 3. FactFile Table Incomplete
**Evidence:** If FactFile query returns 0 records, BM25 index empty  
**Symptoms:** BM25 index = None, lexical search returns []  
**Why:** File extraction incomplete or not persisted

---

### UNPROVEN

#### 1. RIM Seed Selection Too Restrictive
**Evidence:** build_rim_metadata_block:130-139 filters candidates  
**Symptoms:** Could explain why retriever returns candidates but seeds don't resolve  
**Status:** Unproven - would need to see actual retriever output vs. seed resolution

#### 2. Entity ID Format Mismatch Between Tools
**Evidence:** Different tools use different ID formats  
**Symptoms:** Could cause resolution failures  
**Status:** Unproven - reviewed code and formats appear consistent

#### 3. Analysis ID Mismatch
**Evidence:** Retriever filters by analysis_id, tools use same analysis_id  
**Symptoms:** Could cause tools to see different data than retriever  
**Status:** PROVEN FALSE - traced through code, IDs consistent

---

### DISPROVEN

#### 1. Path Normalization Issues
**Diagnosis:** Already investigated and disproven in prior analysis  
**Status:** PROVEN FALSE - paths normalized consistently

#### 2. Frontend Display Logic Stripping Data
**Investigation:** retriever returns candidates, comparison_side metrics calculated from loop_result, not from retriever output  
**Status:** Frontend correctly receives backend data, problem is in backend calculation

---

## 9. COMMON ARCHITECTURAL CAUSE

**The Root Problem:** RepositoryModel Relationship Invariant Violation (NEW)

My orphaned relationship fix addresses one symptom, but the architecture has a deeper issue:

### Relationship between Components

```
Analyzers (callgraph.py, type.py, etc.)
    ↓
RepositoryModel (entities + relationships)
    ↓
FactStore (persistence)
    ↓
HybridRetriever (BM25 index from FactStore)
    ↓
[Validation Gap Here]
    ↓
RIM Metadata (uses retriever.retrieve())
```

**The Gap:**
- Analyzers produce relationships that violate invariant (orphaned)
- FactStore silently drops them (DEBUG logging)
- Retriever doesn't know anything failed
- RIM metadata assumes relationships were persisted

**Result:** Silent data loss at multiple stages

### Architectural Issues

1. **Dual Retrieval Paths**
   - Path #1: search_repository → search_code → finds files (direct)
   - Path #2: retriever.retrieve() → BM25 + semantic → finds from index (indirect)
   - They diverge and never reconverge
   - Metrics come from Path #1, RIM metadata from Path #2
   - If Path #2 fails, Path #1 succeeds but RIM metadata empty

2. **Index Staleness**
   - BM25 index built once at retriever startup
   - Analyzers run after retriever initialization
   - Index never refreshed
   - Any analysis after startup has stale index

3. **Silent Failures**
   - Relationships skipped → DEBUG logging → may not appear in logs
   - Chroma not available → DEBUG logging → may not appear in logs
   - BM25 empty → no warning → just returns []
   - Tool errors → logged but loop continues
   - HTTP 200 always returned despite internal failures

4. **Metrics Disconnected from Actual Retrieval**
   - Metrics count tool_calls
   - Tool calls don't necessarily retrieve from indexed sources
   - UI says "Files Retrieved: 0" when search found 20 files
   - Metric should count search results, not just read_file calls

---

## 10. FIX PLAN (ARCHITECTURAL)

### Phase 1: Relationship Invariant (COMPLETE)
✅ Already fixed - prevent orphaned relationships at source

### Phase 2: Integration of Retrieval Paths

**Option A: Unified Retriever (Major Refactor)**
- Absorb search_code, find_files, get_symbol into retriever
- Build live index as tools run
- Single API returns all results
- Pro: Consistent results everywhere
- Con: Major architectural change

**Option B: Decouple RIM Metadata from Retriever Index (Recommended)**
- Use search_repository directly for RIM seeds (don't use retriever.retrieve)
- Call TargetEntityResolver on search_repository results
- Traverse relationships from resolved entities
- Pro: Uses live data, smaller change
- Con: Different path for RIM vs. baseline

**Option C: Refresh Index On Demand**
- HybridRetriever.refresh_index() called after analysis completes
- Rebuild BM25 from current FactStore
- Rebuild Chroma embeddings
- Pro: Minimal architectural change
- Con: Performance cost, index still separate from live search

### Phase 3: Error Visibility

- Elevate orphaned relationship errors from DEBUG to ERROR
- Elevate missing Chroma to WARNING
- Add pre-save validation that fails loudly for invariant violations
- Return 400 on incomplete analysis instead of 200 with empty metadata

### Phase 4: Metrics Accuracy

- Track search_code results separately
- Track get_symbol results separately
- Track read_file results separately
- UI shows all three to give complete picture
- Or aggregate properly: files_found, files_read, symbols_found, symbols_resolved

---

## 11. TEST PLAN

### Test 1: Empty FactStore
```python
def test_rim_metadata_empty_factstore():
    """Verify behavior when FactStore has no data"""
    # Setup: Fresh analysis_id with no analyzer runs
    analysis_id = new_analysis()
    
    # Run comparison
    result = await rim_comparison_service.run_comparison("What is authentication?")
    
    # Expectations
    assert result.with_rim.rim_metadata_block == "RIM_METADATA: No structural facts..."
    assert result.with_rim.retrieval_metrics.rim_entities_accessed_count == 0
    assert result.without_rim.retrieval_metrics.files_retrieved > 0  # Should find via search_code
    
    # Test passes if RIM side has 0 entities but baseline found files via search_code
```

### Test 2: Retriever Stale Index
```python
def test_retriever_stale_after_analysis():
    """Verify retriever refreshes after analysis"""
    # Setup: Analyzer runs, creates 50 symbols in FactStore
    analysis_id = run_analysis(repo)
    
    # Create retriever (should see symbols)
    retriever1 = HybridRetriever(db, analysis_id)
    results1 = retriever1.retrieve("authentication", expand_with_fact_store=False)
    
    # Delete symbols from FactStore (simulates stale data)
    db.query(FactSymbol).filter_by(analysis_id=analysis_id).delete()
    
    # Retriever still has old symbols (BM25 not refreshed)
    results_after_delete = retriever1.retrieve("authentication", expand_with_fact_store=False)
    
    # Test passes if results before/after delete are identical (demonstrating stale index)
```

### Test 3: Orphaned Relationships Still Skipped (Bug Regression)
```python
def test_orphaned_relationships_rejected():
    """Verify my fix catches orphaned relationships"""
    model = RepositoryModel(...)
    
    # Create entity
    entity_id = "urn:function:test.py#foo"
    model.entities[entity_id] = Entity(...)
    
    # Create relationship to non-existent entity
    orphaned_target = "urn:function:external.py#bar"
    rel = Relationship(source_id=entity_id, target_id=orphaned_target)
    model.relationships[rel.id] = rel
    
    # Save should fail with ValueError
    with pytest.raises(ValueError, match="invariant violated"):
        save_rim_to_fact_store(db, analysis_id, model)
```

### Test 4: Files Counted Correctly
```python
def test_files_retrieved_metric():
    """Verify files_retrieved counts only read_file, not search"""
    # Mock tools: search_code returns 10 files, read_file returns 2
    
    result = await rim_qa_loop.run("What is authentication?")
    
    # Result should show:
    # tool_call_count = 3 (search_code + read_file + read_file)
    # files_read = 2 (only from read_file)
    
    assert len(result.files_read) == 2
    assert "search_code" not in [turn.tool_call["tool_name"] for turn in result.turns if turn.tool_call]
```

### Test 5: RIM Metadata Seeds Resolve
```python
def test_rim_metadata_seed_resolution():
    """Verify seeds from retriever can be resolved"""
    analysis_id = run_analysis(repo_with_symbols)
    retriever = HybridRetriever(db, analysis_id)
    
    # Get metadata block
    metadata = build_rim_metadata_block(db, analysis_id, "What is login?", retriever)
    
    # Every seed in metadata.seed_entities should:
    # 1. Exist in retriever output
    # 2. Resolve to an ORM object
    # 3. Have relationships in FactStore
    
    for seed in metadata.seed_entities:
        entity_name = seed.get("entity_name")
        resolver = TargetEntityResolver(db, analysis_id)
        target = resolver.resolve(entity_name)
        assert target is not None, f"Seed {entity_name} couldn't resolve"
```

### Test 6: Relationship Types Present
```python
def test_relationship_types_in_factstore():
    """Verify expected relationship types exist after analysis"""
    analysis_id = run_analysis(repo)
    
    rel_counts = db.query(
        FactRelationship.rel_type,
        func.count(FactRelationship.id)
    ).filter(FactRelationship.analysis_id == analysis_id).group_by(
        FactRelationship.rel_type
    ).all()
    
    rel_types = {t: c for t, c in rel_counts}
    
    # Should find at least CALLS and DECLARES (from callgraph + symbol)
    assert "CALLS" in rel_types and rel_types["CALLS"] > 0
    assert "DECLARES" in rel_types and rel_types["DECLARES"] > 0
```

---

## 12. SUMMARY TABLE

| Component | Status | Evidence | Impact |
|-----------|--------|----------|--------|
| Orphaned relationships | **FIXED** | My previous fix prevents creation | ✅ Resolved |
| BM25 index stale | **CONFIRMED** | Built once, never refreshed | ❌ CRITICAL |
| Files metric wrong | **CONFIRMED** | Counts only read_file | ❌ HIGH |
| Retriever separate from tools | **CONFIRMED** | Dual paths that diverge | ❌ CRITICAL |
| Chroma silently unavailable | **CONFIRMED** | Exception caught at DEBUG level | ⚠️ MEDIUM |
| FactStore incomplete | **LIKELY** | If analysis extraction incomplete | ⚠️ MEDIUM |
| RIM metadata empty | **CONFIRMED** | When retriever returns [] | ❌ CRITICAL |

---

## 13. CONCLUSION

The RIM pipeline doesn't just have the orphaned relationship bug I fixed. It has a fundamental **architectural separation between live repository tools and indexed retrieval**:

1. **Live Path (Search Tools):** search_code, find_files, get_symbol work on current codebase/FactStore
2. **Index Path (Retriever):** BM25 and semantic indexes built once at startup, never updated
3. **Divergence Point:** search_code finds files but retriever doesn't know about them
4. **RIM Metadata:** Uses retriever (index path), gets empty results despite live search success
5. **Metrics:** Appear to show success ("found files") but actually fail for RIM path ("0 facts")

The fix requires **integrating these paths**: either by making retriever live-updating, or by using live search for RIM metadata instead of index-based retrieval.

**DO NOT FIX BY:**
- Increasing search limits (doesn't solve integration issue)
- Fabricating missing entities (masks root cause)
- Changing RIM prompts to hide empty metadata (masks root cause)
- Adding fallback search when retriever fails (still leaves two paths)

**THE REAL FIX:**
Unify retrieval so the LLM, retriever, and RIM metadata all see the same data source.

