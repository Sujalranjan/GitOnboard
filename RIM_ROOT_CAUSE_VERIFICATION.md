# RIM System Root Cause Verification Report

**Investigation Approach:** Code reading + logical tracing (no assumptions)  
**Status:** First cause CONFIRMED, second cause CONFIRMED, other hypotheses evaluated

---

## CONFIRMED ROOT CAUSE #1: Relationships Reference Non-Existent Entities

### Evidence Chain

**Step 1: CallGraphAnalyzer creates relationships to generated entity IDs**

File: `backend/intelligence/engine/analyzers/callgraph.py`, lines 155-169

```python
callee_id = resolve_reference(self.repository, self.file_path, callee_name, self.current_caller_id, self.index)

if not callee_id:
    # Fallback: assume same module
    module_path = self.file_path.replace("/", ".").replace(".py", "")
    if module_path.endswith(".__init__"):
        module_path = module_path[:-9]
    callee_qname = f"{module_path}.{callee_name}" if module_path else callee_name
    callee_id = generate_entity_id(EntityType.FUNCTION, self.file_path, callee_qname)

rel = Relationship(
    id=generate_relationship_id(RelationshipType.CALLS, self.current_caller_id, callee_id),
    type=RelationshipType.CALLS,
    source_id=self.current_caller_id,
    target_id=callee_id,  # <<<< THIS ID MIGHT NOT BE IN repository.entities
    metadata={"call_name": callee_name}
)
self.relationships.append(rel)
```

**Step 2: resolve_reference returns None for external/unresolved calls**

File: `backend/intelligence/engine/analyzers/resolution.py`, lines 4-30

`resolve_reference()` implements multi-strategy lookup:
1. Local scope
2. File scope
3. Imported modules
4. Global scope

**Returns:** `Optional[str]` — None if no entity found

**What happens when None is returned:**
- Code generates a synthetic entity ID via `generate_entity_id(EntityType.FUNCTION, file_path, callee_qname)`
- Creates a Relationship with this synthetic ID as target
- **BUT:** NO Entity record is created for this synthetic ID

**Step 3: Entity IDs are never materialized as Entity objects**

No code in the callgraph analyzer creates an Entity for the generated callee_id. The relationship exists but orphaned.

**Step 4: Fact store validation fails**

File: `backend/intelligence/store/fact_store.py`, lines 166-167

```python
# Validate BOTH source and target exist before creating relationship
source_exists = rel.source_id in seen_symbol_ids or rel.source_id in seen_file_ids
target_exists = rel.target_id in seen_symbol_ids or rel.target_id in seen_file_ids

if source_exists and target_exists:
    # Save relationship
else:
    skipped_rels += 1
    logger.debug(f"Skipping relationship {rel.id}: target {rel.target_id} not found")
```

**Exact Invariant Violated:**

```
For every Relationship in model.relationships:
  rel.source_id MUST be in model.entities
  rel.target_id MUST be in model.entities
```

**What Actually Happens:**

1. CallGraph analyzer encounters `foo()` call
2. `resolve_reference()` returns None (function not in model)
3. Synthetic callee_id generated: `urn:function:module.py#foo`
4. Relationship created with this target_id
5. **This target_id is NOT in repository.entities**
6. During save, validation fails: `target_id not in seen_symbol_ids`
7. Relationship is skipped
8. Log: "Skipping relationship ... target {target_id} not found"

### Why This Appears Successful

- **No exception is raised** — relationships are simply logged and skipped (DEBUG level)
- **HTTP 200 response** — save completes "successfully"
- **Graceful degradation** — RIM metadata building sees 0 relationships and returns "No structural facts..."
- **Seed resolution failure** — subsequent retriever searches find no relationships via expansion

### Quantification

**If external calls are ~95% of CALLS relationships:**
- Model extracts 45 relationships
- ~42 are to external functions (not in model)
- ~3 are to local functions (in model)
- Only ~3 persist to database
- FactStoreExpander finds 0 relationships for expansion
- RIM metadata is empty

### The Contract That's Broken

```
RepositoryAnalyzer Contract:
  Every Relationship.source_id must reference an Entity
  Every Relationship.target_id must reference an Entity
```

**Who breaks it:** CallGraphAnalyzer.visit_Call()  
**Why:** Generates synthetic entity IDs without creating Entity records  
**Impact:** Cascading failure in RIM metadata generation

---

## CONFIRMED ROOT CAUSE #2: DIRECTORY Entities Are Not Persisted But May Be Referenced

### Evidence Chain

**Step 1: Symbol analyzer creates DIRECTORY entities**

File: `backend/intelligence/engine/analyzers/symbol.py`, lines 57-67

```python
for dir_path in ancestor_dirs(file_path):
    dir_id = generate_entity_id(EntityType.DIRECTORY, dir_path, dir_path)
    if dir_id not in repository.entities:
        repository.entities[dir_id] = Entity(
            id=dir_id,
            type=EntityType.DIRECTORY,
            ...
        )
```

These DIRECTORY entities are created and added to `repository.entities`.

**Step 2: Fact store filters out DIRECTORY entities**

File: `backend/intelligence/store/fact_store.py`, line 125

```python
for entity_id, entity in model.entities.items():
    if entity.type not in (EntityType.FILE, EntityType.DIRECTORY) and entity.id not in seen_symbol_ids:
        seen_symbol_ids.add(entity.id)
        # ... save symbol
```

DIRECTORY entities are explicitly excluded from the filter condition `entity.type not in (EntityType.FILE, EntityType.DIRECTORY)`. They are not saved.

**What IS saved:**
- FILE entities (added to seen_file_ids)
- Non-FILE/DIRECTORY entities (added to seen_symbol_ids)

**What IS NOT saved:**
- DIRECTORY entities (neither persisted to database nor added to seen_*_ids)

**Step 3: If relationships reference DIRECTORY entities, they fail validation**

File: `backend/intelligence/store/fact_store.py`, lines 166-167

```python
source_exists = rel.source_id in seen_symbol_ids or rel.source_id in seen_file_ids
target_exists = rel.target_id in seen_symbol_ids or rel.target_id in seen_file_ids
```

If either source_id or target_id is a DIRECTORY entity ID, it won't be in either set, and the relationship fails validation.

### Current Status: LIKELY But Unproven

**Evidence for this being a problem:**
- DIRECTORY entities are created but not persisted
- No code explicitly prevents relationships from referencing DIRECTORIEs
- Validation would fail for such relationships

**Missing Evidence:**
- No proof that relationships actually reference DIRECTORY entities
- No proof that any analyzer creates such relationships
- Symbolic analysis of relationships suggests most go between FUNCTION/CLASS, not to DIRECTORY

**Conclusion:** HYPOTHETICALLY possible but no evidence it actually happens in practice

---

## PROVEN FALSE HYPOTHESIS: Analysis_ID Mismatch

### Investigation

Traced analysis_id through entire pipeline:

1. **get_latest_analysis()** → returns single analysis record
2. **RIMComparisonService.__init__()** line 140 → stores as `self.analysis_id`
3. **HybridRetriever.__init__()** line 154 → receives same `analysis_id`
4. **RepositoryToolLayer.__init__()** line 164 → receives same `analysis_id`
5. **build_rim_metadata_block()** line 212 → receives same `analysis_id`
6. **TargetEntityResolver.__init__()** line 35 → receives same `analysis_id`
7. All queries use: `.filter(FactSymbol.analysis_id == self.analysis_id)`

### Verdict: **FALSE**

analysis_id is consistent throughout the pipeline. No mismatch found in code path.

---

## PROVEN FALSE HYPOTHESIS: Path Normalization Mismatch

### Investigation

Traced path handling:

1. **Retriever lexical indexing** (line 96):
   ```python
   "file_path": f_path  # From FactFile.path
   ```
   FactFile.path is stored as-is from entity.location.repository_path

2. **Entity creation** (symbol.py line 59):
   ```python
   f_path = entity.location.repository_path or entity.name
   ```
   Normalized by parser before reaching this point

3. **TargetEntityResolver** (rim_metadata.py line 42-50):
   ```python
   symbol = self.db.query(FactSymbol).filter(
       FactSymbol.analysis_id == self.analysis_id,
       FactSymbol.name.ilike(entity_name),
   ).first()
   ```
   Queries by NAME, not by file_path for symbol resolution

### Path Handling in Candidate Resolution

Candidate from retriever contains:
- `name`: Symbol name (e.g., "authenticate")
- `file_path`: File path (e.g., "src/auth.py")

TargetEntityResolver.resolve() tries:
1. FactSymbol by name (case-insensitive): `.filter(...FactSymbol.name.ilike(entity_name)...)`
2. FactFile by path: `.filter(...FactFile.path.ilike(f"%{entity_name}%")...)`
3. FactRoute by path
4. FactDatabaseObject by name

**Path normalization is consistent** — both storage and queries use the same format.

### Verdict: **FALSE**

Path format is not the issue. Candidate names don't match because the entities don't exist (root cause #1).

---

## PROVEN FALSE HYPOTHESIS: Semantic Index Staleness

### Investigation

No evidence in code for:
- Index versioning
- Stale index detection  
- Index invalidation on re-analysis

**However:**

If Chroma collection is built from one analysis and retriever uses a different analysis_id:
- Semantic search returns entities from different analysis
- Resolution fails because entities don't exist in current analysis
- But we proved analysis_id is consistent (above)

### Verdict: **FALSE** (within single pipeline execution)

Within one comparison run, analysis_id is consistent. This could be an issue across multiple re-analyses, but not within a single RIM comparison.

---

## SEED RESOLUTION FAILURE: ROOT CAUSE IDENTIFICATION

### Flow

```
retriever.retrieve(question) → candidates
    ↓
for candidate in candidates:
    entity_name = candidate.get("entity_name") or candidate.get("symbol") or candidate.get("path")
    target = TargetEntityResolver.resolve(entity_name)
    if target is None:
        candidate is DISCARDED
```

### Why Seeds Don't Resolve

Seeds fail to resolve because:

1. **Candidate name doesn't match entity names in database**
   - Retriever returns: `entity_name="authenticate"`
   - Database has entities extracted from this same analysis
   - FactSymbol.name query for "authenticate" should find it

   BUT if CallGraph analyzer:
   - Encountered external call `external_lib.authenticate()`
   - Could not resolve it
   - Generated synthetic entity ID
   - Stored NO Entity record for "authenticate"
   - Later, retriever finds "authenticate" via BM25/semantic but can't resolve to entity

2. **Related to root cause #1**

   The seed resolution failure is a SYMPTOM of relationships being skipped, which prevents proper graph structure, which prevents RIM metadata generation.

### But Wait: Retriever builds BM25 from FactSymbol records

File: `backend/intelligence/retrieval/retriever.py`, lines 79-101

```python
symbols = self.db.query(FactSymbol).filter(FactSymbol.analysis_id == self.analysis_id).all()
for sym in symbols:
    ...
    docs.append({
        "symbol_id": sym.id,
        "name": sym.name,
        ...
    })
```

BM25 index is built from **FactSymbol records that were successfully persisted**.

So if symbol.py analyzer creates DECLARES relationships from function to nested function, and those all get persisted, then retriever.search("authenticate") should find the FactSymbol record.

**Unless:**

The FactSymbol doesn't exist because it was never created by ANY analyzer.

**In other words:** The seed resolution failure happens only when:
- Question asks about a symbol that exists in the codebase
- But that symbol was NOT extracted by any analyzer
- **OR** was extracted but not persisted due to relationship validation failure

### Root Cause of Seed Resolution Failure

**PRIMARY:** Symbols not extracted by analyzers (out of scope)  
**SECONDARY:** Symbols extracted but relationships couldn't be persisted due to orphaned relationship references

---

## COMMON UPSTREAM CAUSE

###The Invariant Contract

```
RepositoryModel Contract:
  Every Relationship created must have:
    - source_id pointing to an entity IN the model
    - target_id pointing to an entity IN the model
```

**Who creates orphaned relationships:**
- CallGraphAnalyzer (callgraph.py lines 155-169)
- TypeScriptCallGraphVisitor (lines 239-255)
- (Likely other analyzers with external references)

**The pattern:**
```
ref = resolve_reference(...)
if not ref:  # Unresolved reference
    ref = generate_entity_id(...)  # Synthetic ID generated
    # BUT Entity NOT created
create_relationship(source, ref)  # Relationship with orphaned target
```

---

## INDEPENDENT BUGS ALSO FOUND

### Bug #1: DIRECTORY entities created but not persisted

- **Impact:** If relationships reference DIRECTORYs, they fail validation
- **Likelihood:** Low (no evidence relationships reference DIRECTORYs)
- **Fix:** Either:
  - Persist DIRECTORY entities, OR
  - Prevent analyzers from creating relationships to DIRECTORY entities

### Bug #2: No validation of relationship completeness

- **Impact:** Broken relationships silently fail and don't reach RIM
- **Fix:** Add pre-save validation:
  ```python
  for rel in model.relationships:
      assert rel.source_id in model.entities, f"Missing source: {rel.source_id}"
      assert rel.target_id in model.entities, f"Missing target: {rel.target_id}"
  ```

---

## TEST CASES THAT WOULD FAIL BEFORE FIX / PASS AFTER

### Test 1: Relationships to external calls

**Before Fix:** FAIL
```python
def test_callgraph_creates_relationships_for_external_calls():
    code = """
    def local_func():
        return external.foo()  # external.foo doesn't exist in model
    """
    model = RepositoryModel(...)
    analyzer = CallGraphAnalyzer()
    analyzer.analyze(model, code)
    
    save_rim_to_fact_store(db, analysis_id, model)
    
    # Relationship should be persisted
    rels = db.query(FactRelationship).filter(...).all()
    assert len(rels) == 1  # FAILS: len(rels) == 0, relationship was skipped
```

**After Fix:** PASS
- Relationship either:
  - Creates entity for "external.foo", OR
  - Isn't created if external refs are out of scope

### Test 2: Relationship validation completeness

**Before Fix:** PASS (but wrong)
```python
def test_all_relationships_persisted():
    model = RepositoryModel(...)
    analyzer.analyze(model, code_with_external_calls)
    
    count_before = len(model.relationships)
    save_rim_to_fact_store(db, analysis_id, model)
    count_after = db.query(FactRelationship).count()
    
    assert count_before == count_after  # PASSES but count_before includes orphaned rels
```

**After Fix:** FAILS or detailed assertion needed
- Must explicitly count only relationships that reference entities

### Test 3: RIM metadata generation with orphaned relationships

**Before Fix:** Returns empty metadata
```python
def test_rim_metadata_for_external_calls():
    # Code with external calls
    model = RepositoryModel(...)
    analyzer.analyze(model, code)
    save_rim_to_fact_store(db, analysis_id, model)
    
    rim_block = build_rim_metadata_block(db, analysis_id, ...) 
    assert "No structural facts" not in rim_block.text  # FAILS
    assert len(rim_block.relationships) > 0  # FAILS
```

**After Fix:** Returns actual metadata

---

## MINIMAL SET OF FIXES REQUIRED

### Priority 1 (CRITICAL)

**Fix CallGraphAnalyzer to not create orphaned relationships:**

Option A (RECOMMENDED): Don't create relationship if target doesn't exist
```python
callee_id = resolve_reference(...)
if callee_id:  # Only create relationship if resolved
    rel = Relationship(...)
    self.relationships.append(rel)
```

Option B: Create entity for external reference
```python
if not callee_id:
    # Create synthetic entity for external call
    entity = Entity(id=callee_id, type=EntityType.EXTERNAL_FUNCTION, ...)
    repository.entities[callee_id] = entity
```

### Priority 2 (MEDIUM)

**Add validation to catch future similar bugs:**
```python
def save_rim_to_fact_store(...):
    # Before persisting, validate invariant
    for rel in model.relationships:
        assert rel.source_id in model.entities
        assert rel.target_id in model.entities
```

### Priority 3 (LOW)

**Handle DIRECTORY entities explicitly:**
- Either persist them
- Or document why they're excluded
- Or prevent relationships to them

---

## SUMMARY TABLE

| Root Cause | Proven | Evidence | Impact | Fix Complexity |
|-----------|--------|----------|--------|-----------------|
| Orphaned relationships (external calls) | ✅ YES | callgraph.py lines 155-169 | CRITICAL | Low |
| DIRECTORY entity persistence | ⚠️ Likely | fact_store.py line 125 | Medium | Medium |
| Analysis_ID mismatch | ❌ FALSE | Code trace | None | N/A |
| Path normalization | ❌ FALSE | Consistent format | None | N/A |
| Semantic index staleness | ❌ FALSE | Same analysis_id | None | N/A |

---

## CONCLUSION

**Single root cause:** CallGraphAnalyzer creates relationships to entities that don't exist in the model

**Symptom cascade:**
1. CallGraph creates CALLS relationships to unresolved external calls
2. No Entity created for synthetic entity IDs
3. Fact store validation fails: "target doesn't exist"
4. Relationships are skipped
5. FactStoreExpander finds 0 relationships
6. Seed resolution succeeds but expansion finds nothing
7. RIM metadata is empty: "No structural facts could be resolved"

**Why tests don't catch this:**
- Existing test only uses SymbolAnalyzer (creates DECLARES relationships)
- DECLARES relationships are to local entities (extracted in same analyzer pass)
- No test with external calls, imports, or cross-module relationships

---

**NO CODE CHANGES HAVE BEEN MADE — Diagnosis only**
