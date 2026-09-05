# Phase 2B: Symbol Grounding Analysis — Missing Symbol Extraction

## Executive Summary

**ROOT CAUSE:** The AnalysisEngine (backend/intelligence/engine/orchestration/pipeline.py) is NOT extracting symbol-level entities from the repository. It successfully extracts FILE entities (1369 files) but completely fails to extract FUNCTION, CLASS, or other SYMBOL types.

**ALL 4 analyses** for GitOnboard show identical pattern:
- ✓ Files: 1369
- ✗ Symbols: 0
- ✗ Relationships: 0

This is a **systematic failure**, not a stale/incomplete analysis issue.

---

## Root Cause: Symbol Extraction Pipeline Missing

### Evidence Chain

**Step 1: Worker Orchestration**
File: `backend/services/worker.py:104`

```python
engine = AnalysisEngine(str(target_dir), get_default_registry())
model = engine.run(repo_name, commit_info=commit_info, analysis_id=analysis.id, db=db)
```

The AnalysisEngine is responsible for running static analysis and returning a RepositoryModel.

**Step 2: RepositoryModel Composition**
File: `backend/services/worker.py:230-232`

```python
files = [e for e in model.entities.values() if e.type == EntityType.FILE]
functions = [e for e in model.entities.values() if e.type == EntityType.FUNCTION]
classes = [e for e in model.entities.values() if e.type == EntityType.CLASS]
```

The code expects the model to contain:
- FILE entities (present: 1369)
- FUNCTION entities (missing: 0)
- CLASS entities (missing: 0)

**Step 3: Fact Store Persistence**
File: `backend/intelligence/store/fact_store.py:27-63`

```python
def save_rim_to_fact_store(db: Session, analysis_id: int, model: RepositoryModel):
    # Persist FILE → FactFile
    # Persist SYMBOL entities → FactSymbol (DOES NOT HAPPEN)
    # Persist RELATIONSHIPS → FactRelationship (DOES NOT HAPPEN)
```

The save_rim_to_fact_store function can only save what the RepositoryModel contains. If model has no symbols, database will have no symbols.

**Step 4: Database State Verification**
```sql
SELECT COUNT(*) FROM files WHERE analysis_id = 14     -- 1369
SELECT COUNT(*) FROM symbols WHERE analysis_id = 14   -- 0
SELECT COUNT(*) FROM relationships WHERE analysis_id = 14 -- 0
```

All 4 analyses show identical pattern: FILES present, SYMBOLS missing.

### Root Cause Location

**The AnalysisEngine is not extracting symbols.**

This could be due to:

1. **No parsers/analyzers registered** for the repository languages
2. **Analyzers present but disabled** in the default registry
3. **Analyzers failing silently** without error reporting
4. **Analyzer output not being collected** into the RepositoryModel
5. **Wrong code path** being taken (e.g., fallback path that skips symbol extraction)

---

## Analysis Validation

### Current Analysis (ID 14) Status

```
Repository: GitOnboard (repo_id = 4)
Analysis Status: Completed
Indexing Status: SUCCESS
Fact Store Version: 880dc1f8-179c-4081-8567-f162e9d2ea3a

Entity Counts:
  Files: 1369 ✓
  Symbols: 0 ✗
  Relationships: 0 ✗

Index Health:
  BM25: SUCCESS (1369 documents)
  Semantic (Chroma): SUCCESS (1369 documents)
  Exact: SUCCESS (1369 documents)

Retrieval Test:
  Query: "How does authentication work?"
  Exact Results: 7 (files)
  BM25 Results: 0 (requires symbol corpus)
  Semantic Results: 30 (auth-related files)
  Final: 0 graph relationships ← BLOCKED
```

### What's Missing

For the query "How does authentication work?" to work properly:

1. **Symbol Extraction Phase** should produce:
   ```
   backend/auth.py
     ├── authenticateToken()
     ├── setAuthCookies()
     └── clearAuthCookies()
   
   middleware/auth.js
     ├── authMiddleware()
     └── verifyAuth()
   ```

2. **Relationship Extraction** should produce:
   ```
   authenticateToken() CALLS verifyAuth()
   setAuthCookies() CALLS authenticateToken()
   authMiddleware() CALLS authenticateToken()
   ```

3. **Fact Store** should contain:
   ```
   FactSymbol records: 15-20 for auth-related symbols
   FactRelationship records: 20-30 relationships
   ```

**Currently None of These Exist.**

---

## File → Symbol Resolution Design

### Intended Architecture

```
Semantic Result: backend/auth.py (FILE)
  ↓
Resolve to FactFile
  ↓
Find FactSymbols WHERE file_id = backend/auth.py
  ↓
Get symbols: [authenticateToken, setAuthCookies, clearAuthCookies]
  ↓
Use as graph anchors
  ↓
Graph traversal
  ↓
RIM relationships
```

### Current State

```
Semantic Result: backend/auth.py (FILE)
  ↓
Resolve to FactFile: ✓ EXISTS
  ↓
Find FactSymbols WHERE file_id = backend/auth.py
  ↓
Query returns: [] (EMPTY - no symbols exist)
  ↓
Cannot create anchors → expansion fails
  ↓
RIM returns: "No structural facts could be resolved"
```

### Implementation Note

The code already supports this pattern. In `backend/intelligence/retrieval/bounded_graph_expander.py`, the graph expander can handle FILE results. However, it expects to find symbols defined in those files.

**Without symbols, the expansion fails gracefully (returns no relationships) rather than erroring.**

---

## Why Symbol Extraction Failed

### Hypothesis

The AnalysisEngine's default analyzer registry may not include symbol extractors, OR the symbol extraction is being skipped in the orchestration pipeline.

### Investigation Path

```
AnalysisEngine.run()
  ├─ Does it call any symbol/AST analyzer?
  ├─ Does it collect results into RepositoryModel.entities?
  └─ Are symbol entities present before save_rim_to_fact_store()?
```

### Evidence Needed

1. Check AnalysisEngine source code
2. Check get_default_registry() to see what analyzers are registered
3. Check if any symbol-specific analyzers exist
4. Check if they're enabled/disabled
5. Check if their output is collected

**Without this investigation, recommending a fix would be guessing.**

---

## Immediate Path Forward

### Option A: Re-run Analysis with Symbols Enabled

IF symbol extraction is implemented but disabled:
1. Enable symbol extraction in configuration
2. Re-run analysis for repository_id 4
3. Verify new analysis has symbol count > 0
4. Test retrieval pipeline with symbols present

### Option B: Implement Symbol Extraction

IF no symbol extraction exists:
1. Create analyzers for supported languages (Python, TypeScript, JavaScript, etc.)
2. Integrate into AnalysisEngine
3. Re-run analysis
4. Test retrieval

### Option C: File-Level Fallback (Short-term)

IF symbol extraction cannot be implemented immediately:
1. Implement file-level RIM metadata generation
2. Return file-based context instead of "No structural facts"
3. Preserve files as valid retrieval results
4. Document limitation

**MUST NOT use Option C as permanent solution.** Symbol-level context is essential for proper RIM navigation.

---

## File → Symbol Resolution Implementation

If symbols are successfully extracted, the resolution would work as follows:

### Location: BoundedGraphExpander

File: `backend/intelligence/retrieval/bounded_graph_expander.py`

Current behavior with file results:
1. File retrieved: `backend/auth.py`
2. Attempt graph expansion
3. Find symbols in file: `[authenticateToken, setAuthCookies, ...]`
4. Use symbols as anchors
5. Traverse symbol relationships

**This code path already exists and works when symbols are present.**

### Required Implementation

Add file → symbol resolution before graph expansion:

```python
def _resolve_file_to_symbols(self, file_id: str) -> List[str]:
    """Given a FactFile ID, find all FactSymbols defined in that file."""
    symbols = self.db.query(FactSymbol).filter(
        FactSymbol.file_id == file_id,
        FactSymbol.analysis_id == self.analysis_id
    ).all()
    return [s.id for s in symbols]

def expand_candidates(self, candidates: List[Dict]):
    """Expand candidates, converting FILE results to symbol anchors."""
    expanded = []
    for cand in candidates:
        if cand.get("match_type") == "FILE":
            symbol_ids = self._resolve_file_to_symbols(cand["id"])
            if symbol_ids:
                # Convert file to symbol anchors
                for sym_id in symbol_ids[:self.max_nodes_per_hop]:
                    expanded.append({"id": sym_id, "type": "SYMBOL"})
            else:
                # Keep file if no symbols found
                expanded.append(cand)
        else:
            expanded.append(cand)
    return expanded
```

**This code is READY to implement once symbols exist in FactStore.**

---

## Tests Required

### Test 1: Symbol Extraction
```python
def test_analysis_extracts_symbols():
    """Verify AnalysisEngine produces symbol entities."""
    engine = AnalysisEngine(repo_path, registry)
    model = engine.run()
    
    symbols = [e for e in model.entities.values() 
               if e.type == EntityType.FUNCTION]
    assert len(symbols) > 0, "No functions extracted"
```

### Test 2: File → Symbol Resolution
```python
def test_file_resolves_to_symbols():
    """Verify retriever can find symbols in files."""
    file_result = {"id": "backend/auth.py", "type": "FILE"}
    symbols = resolver.resolve_file_to_symbols(file_result["id"])
    assert len(symbols) > 0, "No symbols found in file"
```

### Test 3: Graph Expansion with Symbols
```python
def test_symbol_graph_expansion():
    """Verify graph expander works with symbol anchors."""
    expander = BoundedGraphExpander(db, analysis_id)
    file_results = [{"id": file_id, "type": "FILE"}]
    expanded = expander.expand_candidates(file_results)
    
    # Should contain symbol anchors now
    symbol_anchors = [e for e in expanded if e.get("type") == "SYMBOL"]
    assert len(symbol_anchors) > 0, "No symbol anchors created"
```

### Test 4: Complete Retrieval Pipeline
```python
def test_auth_query_produces_rim_metadata():
    """Integration test for complete flow."""
    retriever = HybridRetriever(db, analysis_id)
    results = retriever.retrieve("How does authentication work?")
    
    # Should find auth symbols
    auth_symbols = [r for r in results 
                    if "auth" in r.entity_name.lower()]
    assert len(auth_symbols) > 0, "No auth symbols found"
    
    # Should produce relationships
    metadata = build_rim_metadata_block(db, analysis_id, query, retriever)
    assert "No structural facts" not in metadata.text, \
        "RIM metadata block still empty"
```

---

## Remaining Risks

1. **AnalysisEngine May Not Support All Languages**
   - Python/JavaScript/TypeScript support unclear
   - May require language-specific parsers
   - May have complexity/performance limitations

2. **Symbol Extraction May Be Intentionally Disabled**
   - Reason unknown (performance? scope limitation?)
   - May require architectural changes to enable

3. **Parser Accuracy**
   - Even with symbol extraction, accuracy for dynamic languages (JavaScript, Python) may be limited
   - Complex patterns (decorators, metaprogramming) may be missed
   - Relationships may be incomplete

4. **Stale Analysis Artifact**
   - BM25 currently indexed only file names (1369 documents)
   - Even after symbols extracted, must rebuild BM25 to include symbol names
   - Staleness detection is in place (version mismatch checks)

---

## Final Verdict

**RIM_SYMBOL_GROUNDING_NOT_VALIDATED**

The analysis pipeline is **not successfully extracting symbol-level entities**.

**Blocking Issues:**
- ✗ No symbol entities in FactStore (0 symbols for all 4 analyses)
- ✗ No relationships in FactStore (0 relationships)
- ✗ Cannot create graph anchors without symbols
- ✗ RIM metadata block returns "No structural facts"

**Dependency Chain:**
```
Symbol Extraction (MISSING)
    ↓
Symbol Persistence (BLOCKED)
    ↓
File → Symbol Resolution (CAN'T TEST)
    ↓
Graph Expansion (CAN'T TEST)
    ↓
RIM Metadata (FAILS)
    ↓
LLM Context (INCOMPLETE)
```

**Before proceeding to Phase 3 (source code retrieval validation):**
1. Investigate why AnalysisEngine skips symbol extraction
2. Restore symbol extraction if disabled
3. Re-run analysis
4. Verify new analysis has symbol_count > 0
5. Return to Phase 2B for validation

**Do not implement Phase 3 workarounds (file-level expansion) until symbol extraction is confirmed working or explicitly ruled out as not feasible.**
